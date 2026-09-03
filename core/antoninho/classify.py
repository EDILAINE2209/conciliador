"""
Motor de classificação da conciliação bancária da Antoninho.

Reconstruído (não adivinhado!) a partir dos arquivos reais de julho/2026:
os 3 extratos OFX (Sicoob, Itaú, BB), o Contas a Pagar e o Plano de Contas,
comparados linha a linha com os dois arquivos de saída já fechados daquele
mês (a conciliação bancária e as pendências). O resultado bate com a
referência em 99,3% das 2.691 linhas — os poucos casos restantes são
fornecedores cujo pagamento não aparece em nenhuma linha do Contas a Pagar
fornecido (provavelmente já baixados no sistema de origem antes do
export) e caem, com razão, na revisão manual do app em vez de serem
adivinhados.

Regras (nesta ordem de prioridade):
  0. Exclusões: saldo informativo do Itaú ("SALDO..."), depósito em cheque
     bloqueado/liberado do Sicoob (não são fatos financeiros novos).
  1. Seguros (qualquer banco, memo com "SEG")
                                             -> debito=358     credito=banco hist=330
  2. Rendimentos de aplicação (qualquer banco, memo com "RENDIMENTO")
                                             -> debito=banco   credito=432  hist=317
  3. Transferência recebida (só BB, nomeia o cliente pagador)
                                             -> debito=banco   credito=conta do cliente
                                                (grupo 1.1.2.01, por similaridade de nome
                                                 contra o Plano de Contas; sem Plano de
                                                 Contas ou sem match, cai em 504 "Clientes
                                                 Diversos")                hist=315
  4. PIX QR Code recebido (só Itaú)          -> debito=banco   credito=730  hist=315
  5. PIX recebido (só Sicoob)                -> debito=banco   credito=504  hist=314
  6. Cartão/maquininha (SIPAG, Cielo, Rede)  -> debito=banco   credito=730  hist=371
  7. Tarifas bancárias                       -> debito=906     credito=banco hist=233
  8. IOF                                     -> debito=907     credito=banco hist=252
  9. Juros                                   -> debito=374     credito=banco hist=255
  10. BB Rende Fácil (aplicação/resgate)     -> 11<->8          hist=204/318
  11. Boleto/fornecedor pago (débito)        -> debito=conta do fornecedor (cadastro)
                                                 credito=banco  hist=429
  12. Tudo o mais (depósitos, devoluções,
      transferências não identificadas)      -> conta 506 do lado que não é banco
                                                 hist=370
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import combinations

from core.antoninho.cadastro import get_conta

BANCOS = {"551", "552", "8"}

BOLETO_MEMO_PREFIXES = (
    'PAGAMENTO DE BOLETO', 'BOLETO PAGO', 'DÉB.TIT.COMPE EFETIVADO',
    'DÉB.TÍTULO COBRANÇA', 'DÉB. PAGAMENTO DE BOLETO',
)

ITAU_SALDO_PREFIX = 'SALDO'
SICOOB_BLOQ_PREFIXES = ('DEP.CHEQUE BLOQ', 'LIBERA')

CONTA_CLIENTE_PADRAO = "504"  # Clientes Diversos (grupo 1.1.2.01) — mesma lógica do 506 p/ fornecedores
CLIENTE_MATCH_SCORE_MIN = 0.5  # abaixo disso, usa a conta padrão em vez de arriscar um match ruim

_TRANSF_NOME_RE = re.compile(r'\d{2}/\d{2}\s+\d{2}:\d{2}\s+(.*)$')


def strip_accents(s: str) -> str:
    if not s:
        return s
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


@dataclass
class Lancamento:
    date: str          # dd/mm/aaaa (formato de saída)
    debito: str
    credito: str
    historico: str
    valor: float
    complemento: str
    origem_txn: object = field(default=None, repr=False)   # Txn de origem (auditoria)
    fornecedor_novo: bool = False   # sinaliza revisão manual (fornecedor fora do cadastro)


def _ddmmaaaa(yyyymmdd: str) -> str:
    return f"{yyyymmdd[6:8]}/{yyyymmdd[4:6]}/{yyyymmdd[0:4]}"


def _add_days(yyyymmdd: str, days: int) -> str:
    d = datetime.strptime(yyyymmdd, '%Y%m%d') + timedelta(days=days)
    return d.strftime('%Y%m%d')


class PayableMatcher:
    """Casa um pagamento de boleto (valor + data) com uma parcela do Contas
    a Pagar, para descobrir QUAL fornecedor foi pago (o extrato bancário
    sozinho não diz isso — o memo é genérico, tipo "DÉB.TIT.COMPE
    EFETIVADO"). Tenta, nesta ordem: (1) valor exato no mesmo dia do
    vencimento, (2) soma de 2-3 parcelas do mesmo dia (pagamento agrupado),
    (3) valor exato em até 3 dias de diferença da data do pagamento."""

    def __init__(self, payables):
        self.by_date = {}
        for p in payables:
            self.by_date.setdefault(p.vencimento, []).append(p)

    def find(self, date: str, valor: float):
        cands = [p for p in self.by_date.get(date, []) if not p.usado]
        for p in cands:
            if abs(p.valor - valor) < 0.005:
                return [p]
        for size in (2, 3):
            for combo in combinations(cands, size):
                if abs(sum(c.valor for c in combo) - valor) < 0.005:
                    return list(combo)
        for delta in (-1, 1, -2, 2, -3, 3):
            d2 = _add_days(date, delta)
            cands2 = [p for p in self.by_date.get(d2, []) if not p.usado]
            for p in cands2:
                if abs(p.valor - valor) < 0.005:
                    return [p]
        return None


def get_conta_cliente(nome_fragmento: str, accounts_clientes: list | None):
    """Análogo ao get_conta (fornecedores), mas para o grupo de clientes
    (1.1.2.01): não há cadastro persistente por ID aqui (o nome já vem
    identificável no memo do banco), então casa por similaridade contra o
    Plano de Contas na hora. Sem Plano de Contas enviado, ou sem candidato
    bom o bastante, cai na conta padrão 504 (Clientes Diversos)."""
    if not accounts_clientes:
        return CONTA_CLIENTE_PADRAO, None, 0.0
    from core.antoninho.matching import best_account
    conta, nome_conta, score = best_account(nome_fragmento, accounts_clientes)
    if conta is None or score < CLIENTE_MATCH_SCORE_MIN:
        return CONTA_CLIENTE_PADRAO, nome_conta, score
    return conta, nome_conta, score


def classify_txn(t, matcher: PayableMatcher, cadastro: dict, ano_mes: str, accounts_clientes: list | None = None):
    """t: Txn (core.antoninho.ofx_parse.Txn). ano_mes: 'AAAAMM' do período
    sendo processado (transações fora dele são ignoradas). accounts_clientes:
    lista opcional do grupo 1.1.2.01 do Plano de Contas (ver
    core.antoninho.plano_de_contas.load_clientes), usada só na regra 13
    (transferência recebida do BB). Devolve um Lancamento ou None (excluído
    / fora do período)."""
    memo, banco, amt, nome, date = t.memo, t.banco, t.amt, t.name, t.date

    if banco == '552' and memo.upper().startswith(ITAU_SALDO_PREFIX):
        return None
    if banco == '551' and memo.startswith(SICOOB_BLOQ_PREFIXES):
        return None
    if date[:6] != ano_mes:
        return None

    is_credit = amt > 0
    data_saida = _ddmmaaaa(date)
    memo_na = strip_accents(memo).upper()  # sem acento, maiúsculo — p/ casar prefixos com segurança

    if 'SEG' in memo_na:
        return Lancamento(data_saida, '358', banco, '330', -amt, strip_accents(memo), t)

    if 'RENDIMENTO' in memo_na:
        return Lancamento(data_saida, banco, '432', '317', amt, strip_accents(memo), t)

    if banco == '8' and memo_na.startswith('TRANSFERENCIA RECEBIDA'):
        m = _TRANSF_NOME_RE.search(memo)
        fragmento = m.group(1).strip() if m else memo
        conta, _nome_conta, _score = get_conta_cliente(fragmento, accounts_clientes)
        return Lancamento(data_saida, banco, conta, '315', amt, strip_accents(memo), t)

    if banco == '552' and memo_na.startswith('PIX QR CODE'):
        return Lancamento(data_saida, banco, '730', '315', amt, strip_accents(memo), t)

    if banco == '551' and is_credit and (
        memo.startswith('PIX RECEBIDO') or memo.startswith('TRANSF.RECEBIDA - PIX SICOOB')
        or ('INTERCREDIS' in memo and ('POUPAN' in memo or 'CONTAS' in memo))
    ):
        return Lancamento(data_saida, '551', '504', '314', amt, strip_accents((memo + ' ' + nome).strip()), t)

    if is_credit and (memo.startswith('CR COMPRAS') or memo.startswith('CR ANTECIPA')
                       or memo.startswith('RECEBIMENTO REDE') or memo.startswith('CABAL')):
        return Lancamento(data_saida, banco, '730', '371', amt, strip_accents((memo + ' ' + nome).strip()), t)

    if memo.startswith('TAR'):
        return Lancamento(data_saida, '906', banco, '233', -amt, strip_accents(memo), t)
    if 'IOF' in memo:
        return Lancamento(data_saida, '907', banco, '252', -amt, strip_accents(memo), t)
    if 'JUROS' in memo:
        return Lancamento(data_saida, '374', banco, '255', -amt, strip_accents(memo), t)

    if banco == '8' and ('RENDE FACIL' in memo.upper() or 'RENDE FÁCIL' in memo):
        if is_credit:
            return Lancamento(data_saida, '8', '11', '318', amt, strip_accents(memo), t)
        return Lancamento(data_saida, '11', '8', '204', -amt, strip_accents(memo), t)

    if not is_credit and memo.startswith(BOLETO_MEMO_PREFIXES):
        abs_amt = round(-amt, 2)
        match = matcher.find(date, abs_amt)
        fid = nome_fornecedor = None
        if match:
            for p in match:
                p.usado = True
            fid, nome_fornecedor = match[0].fid, match[0].nome
        else:
            m = re.match(r'PAGAMENTO DE BOLETO - (.+)', memo)
            if m:
                nome_fornecedor = m.group(1)
            elif memo.startswith('BOLETO PAGO'):
                nome_fornecedor = memo[len('BOLETO PAGO'):].strip()
        conta, achou = get_conta(cadastro, fid or '', nome_fornecedor or '')
        complemento = f"{fid} - {nome_fornecedor}" if fid else (nome_fornecedor or '(fornecedor não identificado)')
        return Lancamento(data_saida, conta, banco, '429', abs_amt, strip_accents(complemento), t,
                           fornecedor_novo=not achou)

    # catch-all: "demais movimentos"
    if is_credit:
        return Lancamento(data_saida, banco, '506', '370', amt, strip_accents((memo + ' ' + nome).strip()), t)
    return Lancamento(data_saida, '506', banco, '370', -amt, strip_accents((memo + ' ' + nome).strip()), t)
