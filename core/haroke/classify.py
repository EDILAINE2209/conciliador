"""
Motor de classificação da conciliação bancária da Haroke Supermercado LTDA.

Portado do script `concilia_extratos_haroke.py` e atualizado ao longo de
jul/ago 2026 conforme cada mês real revelou tipos de lançamento novos (ver
Regras_Conciliacao_Haroke.md, enviado junto com os arquivos da empresa, para
a tabela de regras por extenso e o histórico de cada mudança).

Diferenças em relação à Antoninho, que justificam ser um módulo próprio em
vez de reaproveitar `core.antoninho.classify`:
  - a conta do fornecedor é achada por similaridade de nome contra o Plano
    de Contas (com uma lista de correções manuais), não por um cadastro de
    IDs aprendido mês a mês;
  - existe uma regra extra específica da Haroke: PIX grande para a
    Antoninho Atacado e Varejo (uma outra empresa da carteira) tem conta
    própria (597) e não entra no fluxo normal de conciliação de boleto;
  - os códigos de conta contábil (744, 504, 698, 731, 718, 374, 506) são os
    da Haroke, diferentes dos códigos da Antoninho mesmo para categorias
    equivalentes (cada empresa tem seu próprio Plano de Contas);
  - gera um SEGUNDO arquivo de pendências do Contas a Pagar (títulos sem
    pagamento localizado no extrato — ver `gerar_titulos_sem_pagamento` em
    core/haroke/generate.py), fixado em ago/2026 no mesmo padrão já usado
    pela Antoninho.

Mudanças fixadas em ago/2026 (ver Regras_Conciliacao_Haroke.md):
  - cruzamento valor+data com tolerância de até 3 dias de diferença na data
    (valor continua tendo que ser exatamente igual) — `PayableIndex` abaixo;
  - "CRÉD.LIQUIDAÇÃO COBRANÇA" (Sicoob) reconhecida como Créd. Liq. Cobrança;
  - variações de bandeira/nome dentro de uma categoria já validada (REDE,
    CR COMPRAS/CR ANTECIPAÇÃO, DÉB.CONV., TARIFA) passaram a usar
    reconhecimento por prefixo em vez de lista fechada de textos exatos;
  - 3 tipos de lançamento novos com regra própria: "CRÉD.TED-STR" (banco/
    504/314), TED entre titularidades diferentes (506/banco/370), "TED
    INTERNET" (698/banco/233, mesma natureza de tarifa);
  - liberação de depósito bloqueado (banco/5/226) — o bloqueio em si
    continua ignorado;
  - regras personalizadas cadastráveis pela tela (core.common.regras_customizadas),
    para tipos de lançamento novos que ainda não viraram regra fixa — só
    entram em jogo quando NENHUMA regra fixa acima reconhece o memo.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as _date

from core.haroke.matching import best_account
from core.common.regras_customizadas import encontrar_regra, resolver_conta

BANK_BB = '8'
BANK_SICOOB = '551'
ANTONINHO_ACCOUNT = '597'
MATCH_TOLERANCE_DAYS = 3  # fixado ago/2026

SICOOB_BOLETO_MEMOS = {'DÉB.TIT.COMPE EFETIVADO', 'DÉB. PAGAMENTO DE BOLETO INTERCREDIS',
                       'DÉB.TÍTULO COBRANÇA'}
SICOOB_SIPAG_MEMOS = {'CR COMPRAS MAESTRO', 'CR COMPRAS DEB OUTRAS BANDEIRAS',
                      'CR COMPRAS VISA ELECTRON', 'CR COMPRAS CRE OUTRAS BANDEIRAS',
                      'CR ANTECIPAÇÃO VISA', 'CR ANTECIPAÇÃO MASTERCARD',
                      'CR ANTECIPAÇÃO OUTRAS BANDEIRAS'}
SICOOB_CREDLIQ_MEMOS = {'CRÉD.TRANSF.POUPANÇA INTERCREDIS', 'CRED.TRANSF.CONTAS INTERCREDIS',
                        'CRÉD.LIQUIDAÇÃO COBRANÇA'}
SICOOB_CONVENIO_MEMOS = {'DÉB. CONV. SEGUROS', 'DÉB.CONV.TRIBUTOS FEDERAIS - RFB',
                         'DÉB.CONV.TELECOMUNICAÇÕES', 'DÉB.CONV.ORGÃOS GOV.'}
SICOOB_TED_TITULARIDADE_MEMOS = {'DÉB.TRANSF.CONTAS DIF.TIT. INTERCREDIS',
                                 'DEBITO EMISSÃO TED DIF.TITULARIDADE'}
# Prefixos genéricos (cobrem variações de bandeira/nome que mudam mês a mês
# sem precisar listar cada texto exato — fixado ago/2026):
SICOOB_CONVENIO_PREFIXES = ('DÉB.CONV.', 'DÉB.SEGURO')
SICOOB_SIPAG_PREFIXES = ('CR COMPRAS', 'CR ANTECIPAÇÃO')
TARIFA_PREFIXES = ('TARIFA',)
REDE_PREFIXES = ('REDE', 'REDECARD')

BUCKETS = [
    'A_conciliados', 'B_nao_conciliados', 'C_pix_recebidos', 'D_cred_liq_cobranca',
    'E_sipag_cielo', 'F_tarifas', 'H_rendefacil_entra', 'I_rendefacil_sai',
    'J_iof', 'K_antoninho', 'L_demais', 'M_juros', 'N_deposito_liberado',
    'O_ted_str', 'P_ted_titularidade', 'Z_customizada',
]
# Ordem de saída no txt final (igual ao script original: por data e, dentro da
# mesma data, nesta ordem de prioridade — não é a mesma ordem de BUCKETS acima).
PRIORITY = {
    'A_conciliados': 0, 'K_antoninho': 1, 'B_nao_conciliados': 2,
    'C_pix_recebidos': 3, 'D_cred_liq_cobranca': 4, 'E_sipag_cielo': 5,
    'F_tarifas': 6, 'H_rendefacil_entra': 7, 'I_rendefacil_sai': 8,
    'J_iof': 9, 'M_juros': 10, 'L_demais': 11, 'N_deposito_liberado': 12,
    'O_ted_str': 13, 'P_ted_titularidade': 14, 'Z_customizada': 15,
}
NOMES_REGRA = {
    'A_conciliados': 'Fornecedores conciliados',
    'B_nao_conciliados': 'Pagamentos não conciliados',
    'C_pix_recebidos': 'PIX recebidos',
    'D_cred_liq_cobranca': 'Créd. Liq. Cobrança (Intercredis)',
    'E_sipag_cielo': 'SIPAG / Cielo / Rede (cartão)',
    'F_tarifas': 'Tarifas bancárias',
    'H_rendefacil_entra': 'BB Rende Fácil (aplicação)',
    'I_rendefacil_sai': 'BB Rende Fácil (resgate)',
    'J_iof': 'IOF',
    'K_antoninho': 'PIX para Antoninho Atacado e Varejo',
    'L_demais': 'Demais movimentos',
    'M_juros': 'Juros',
    'N_deposito_liberado': 'Depósito bloqueado liberado',
    'O_ted_str': 'CRÉD.TED-STR',
    'P_ted_titularidade': 'TED entre titularidades diferentes',
    'Z_customizada': 'Regra personalizada (cadastrada na tela)',
}


@dataclass
class Lancamento:
    date: str
    debito: str
    credito: str
    historico: str
    valor: float
    complemento: str
    bucket: str
    fornecedor_novo: bool = False
    match_score: float = 1.0


def _ddmmaaaa(yyyymmdd: str) -> str:
    return f"{yyyymmdd[6:8]}/{yyyymmdd[4:6]}/{yyyymmdd[0:4]}"


def _parse_yyyymmdd(yyyymmdd: str) -> _date:
    return _date(int(yyyymmdd[0:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))


class PayableIndex:
    """Casa um pagamento do extrato (valor + data) com uma parcela do Contas
    a Pagar. Valor tem que ser EXATAMENTE igual; a data aceita até
    MATCH_TOLERANCE_DAYS dias de diferença em relação ao vencimento (fixado
    em ago/2026 — antes disso o cruzamento era só na data exata). Entre
    candidatos empatados (mesmo valor, mais de uma parcela dentro da
    tolerância), prefere a de data mais próxima. Marca `p.usado = True` no
    Payable casado, para a lista de pendências (core.haroke.generate) saber
    o que sobrou."""

    def __init__(self, payables, tolerance_days: int = MATCH_TOLERANCE_DAYS):
        self.tolerance_days = tolerance_days
        self.by_value = defaultdict(list)
        for p in payables:
            self.by_value[round(p.valor, 2)].append(p)

    def find(self, date: str, valor_abs: float):
        cands = [p for p in self.by_value.get(round(valor_abs, 2), []) if not p.usado]
        if not cands:
            return None
        txn_date = _parse_yyyymmdd(date)
        best, best_diff = None, None
        for p in cands:
            diff = abs((txn_date - _parse_yyyymmdd(p.vencimento)).days)
            if diff <= self.tolerance_days and (best is None or diff < best_diff):
                best, best_diff = p, diff
        if best is not None:
            best.usado = True
        return best


def preparar_fornecedores(payables, accounts, overrides):
    """Resolve, para cada parcela do Contas a Pagar, a conta do fornecedor
    (por override ou por similaridade com o Plano de Contas). Devolve
    também a lista de matches de baixa confiança (score < 0.95) para a
    tela de revisão do app."""
    baixa_confianca = []
    for p in payables:
        conta, nome_conta, score = best_account(p.nome, accounts, overrides)
        p.conta_fornecedor = conta or "506"
        p.conta_fornecedor_nome = nome_conta
        p.match_score = score
        if score < 0.95:
            baixa_confianca.append(p)
    return baixa_confianca


def classify_all(bb_txns, sicoob_txns, payables, ano_mes: str, regras_customizadas: list | None = None):
    """payables já deve ter passado por `preparar_fornecedores`. Devolve um
    dict {bucket: [Lancamento, ...]} e a lista de lançamentos ainda sem
    regra (unclassified). `regras_customizadas`: lista opcional cadastrada
    pela tela (core.common.regras_customizadas) — só é consultada para um
    memo que nenhuma regra fixa abaixo reconheceu."""
    regras_customizadas = regras_customizadas or []
    idx = PayableIndex(payables)

    entries = {b: [] for b in BUCKETS}

    def add(bucket, date, debito, credito, valor, historico, complemento='', fornecedor_novo=False, score=1.0):
        # Ao contrário da Antoninho, aqui o complemento NÃO passa por
        # strip_accents: o arquivo de referência de julho/2026 mantém
        # acentos (ex. "TARIFA COBRANÇA", "DÉB.IOF", "BB RENDE FÁCIL").
        entries[bucket].append(Lancamento(_ddmmaaaa(date), str(debito), str(credito), historico,
                                           round(valor, 2), complemento, bucket,
                                           fornecedor_novo, score))

    def tenta_conciliar(bucket_ok, bucket_fallback, date, amt, bank, fallback_debito, fallback_credito):
        p = idx.find(date, -amt)
        if p is not None:
            comp = f"{p.documento} {p.nome}"
            add(bucket_ok, date, p.conta_fornecedor, bank, -amt, '429', comp,
                fornecedor_novo=(p.match_score < 0.95), score=p.match_score)
        else:
            add(bucket_fallback, date, fallback_debito, fallback_credito, -amt, '429')

    def tenta_pix_ou_demais(date, amt, bank, memo, name=''):
        p = idx.find(date, -amt)
        if p is not None:
            add('A_conciliados', date, p.conta_fornecedor, bank, -amt, '429', f"{p.documento} {p.nome}",
                fornecedor_novo=(p.match_score < 0.95), score=p.match_score)
        else:
            add('L_demais', date, '506', bank, -amt, '429', f"{memo} {name}".strip())

    def tenta_regra_customizada(date, banco, memo, amt):
        regra = encontrar_regra(memo, banco, regras_customizadas)
        if regra is None:
            return False
        debito = resolver_conta(regra.get('debito', 'BANCO'), banco)
        credito = resolver_conta(regra.get('credito', 'BANCO'), banco)
        add('Z_customizada', date, debito, credito, abs(amt), regra.get('historico', '429'), memo)
        return True

    unclassified = []

    # ---- BB ----
    for t in bb_txns:
        if t.date[:6] != ano_mes:
            continue
        date, amt, memo, name = t.date, t.amt, t.memo.strip(), t.name.strip()
        bank = BANK_BB
        memo_up = memo.upper()

        if 'BLOQ' in memo_up and 'LIBERA' in memo_up:
            add('N_deposito_liberado', date, bank, '5', amt, '226', memo)
        elif 'BLOQ' in memo_up:
            pass  # depósito bloqueado (ainda indisponível): ignorar totalmente
        elif memo.startswith('PAGAMENTO DE BOLETO'):
            tenta_conciliar('A_conciliados', 'B_nao_conciliados', date, amt, bank, '506', '5')
        elif memo.startswith('PIX - ENVIADO') and 'ANTONINHO' in memo_up:
            add('K_antoninho', date, ANTONINHO_ACCOUNT, bank, -amt, '370', memo)
        elif memo.startswith('PIX - ENVIADO'):
            tenta_pix_ou_demais(date, amt, bank, memo)
        elif memo.startswith('PIX - RECEBIDO') and 'CIELO' in memo_up:
            add('E_sipag_cielo', date, bank, '504', amt, '371', memo)
        elif memo.startswith('PIX - RECEBIDO'):
            add('C_pix_recebidos', date, bank, '744', amt, '314', memo)
        elif memo.startswith(REDE_PREFIXES):
            add('E_sipag_cielo', date, bank, '504', amt, '371', memo)
        elif memo in ('BB RENDE FÁCIL - RENDE FACIL', 'BB RENDE FÁCIL'):
            if amt > 0:
                add('H_rendefacil_entra', date, bank, '731', amt, '318', memo)
            else:
                add('I_rendefacil_sai', date, '731', bank, -amt, '204', memo)
        elif memo.startswith(TARIFA_PREFIXES):
            add('F_tarifas', date, '698', bank, -amt, '233', memo)
        elif tenta_regra_customizada(date, bank, memo, amt):
            pass
        else:
            unclassified.append(dict(banco='BB', date=date, amt=amt, memo=memo))

    # ---- SICOOB ----
    for t in sicoob_txns:
        if t.date[:6] != ano_mes:
            continue
        date, amt, memo, name = t.date, t.amt, t.memo.strip(), t.name.strip()
        bank = BANK_SICOOB
        memo_up = memo.upper()

        if 'BLOQ' in memo_up and 'LIBERA' in memo_up:
            add('N_deposito_liberado', date, bank, '5', amt, '226', memo)
        elif 'BLOQ' in memo_up:
            pass  # depósito bloqueado (ainda indisponível): ignorar totalmente
        elif memo in SICOOB_BOLETO_MEMOS:
            tenta_conciliar('A_conciliados', 'B_nao_conciliados', date, amt, bank, '506', '5')
        elif memo == 'TRANSF.REALIZADA PIX SICOOB' and 'ANTONINHO' in name.upper():
            add('K_antoninho', date, ANTONINHO_ACCOUNT, bank, -amt, '370', f"{memo} {name}")
        elif memo == 'TRANSF.REALIZADA PIX SICOOB':
            tenta_pix_ou_demais(date, amt, bank, memo, name)
        elif memo == 'PIX EMITIDO OUTRA IF':
            tenta_pix_ou_demais(date, amt, bank, memo, name)
        elif memo in ('PIX RECEBIDO - OUTRA IF', 'TRANSF.RECEBIDA - PIX SICOOB'):
            add('C_pix_recebidos', date, bank, '744', amt, '314', f"{memo} {name}")
        elif memo in SICOOB_CREDLIQ_MEMOS or memo.startswith('CRÉD.LIQUIDAÇÃO'):
            add('D_cred_liq_cobranca', date, bank, '744', amt, '314', f"{memo} {name}")
        elif memo in SICOOB_SIPAG_MEMOS or memo.startswith(SICOOB_SIPAG_PREFIXES):
            add('E_sipag_cielo', date, bank, '504', amt, '371', memo)
        elif memo.startswith(TARIFA_PREFIXES):
            add('F_tarifas', date, '698', bank, -amt, '233', memo)
        elif memo == 'DÉB.IOF':
            add('J_iof', date, '718', bank, -amt, '252', memo)
        elif memo in SICOOB_CONVENIO_MEMOS or memo.startswith(SICOOB_CONVENIO_PREFIXES):
            add('L_demais', date, '506', bank, -amt, '429', memo)
        elif memo == 'JUROS CONTA GARANTIDA':
            add('M_juros', date, '374', bank, -amt, '255', memo)
        elif memo == 'CRÉD.TED-STR':
            add('O_ted_str', date, bank, '504', amt, '314', memo)
        elif memo in SICOOB_TED_TITULARIDADE_MEMOS:
            add('P_ted_titularidade', date, '506', bank, -amt, '370', memo)
        elif memo == 'TED INTERNET':
            add('F_tarifas', date, '698', bank, -amt, '233', memo)
        elif tenta_regra_customizada(date, bank, memo, amt):
            pass
        else:
            unclassified.append(dict(banco='SICOOB', date=date, amt=amt, memo=memo))

    return entries, unclassified
