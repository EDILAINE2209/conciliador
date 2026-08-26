"""
Motor de classificação da conciliação bancária da Haroke Supermercado LTDA.

Portado do script `concilia_extratos_haroke.py` (construído e já validado
contra o fechamento real de julho/2026 — 945/945 lançamentos, valor exato,
zero divergência) para dentro do app, mantendo exatamente a mesma lógica.
Ver `Regras_Conciliacao_Haroke.md` (enviado junto com os arquivos da
empresa) para a tabela de regras por extenso.

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
    equivalentes (cada empresa tem seu próprio Plano de Contas).
"""
from dataclasses import dataclass

from core.haroke.matching import best_account

BANK_BB = '8'
BANK_SICOOB = '551'
ANTONINHO_ACCOUNT = '597'

SICOOB_BOLETO_MEMOS = {'DÉB.TIT.COMPE EFETIVADO', 'DÉB. PAGAMENTO DE BOLETO INTERCREDIS',
                       'DÉB.TÍTULO COBRANÇA'}
SICOOB_SIPAG_MEMOS = {'CR COMPRAS MAESTRO', 'CR COMPRAS DEB OUTRAS BANDEIRAS',
                      'CR COMPRAS VISA ELECTRON', 'CR COMPRAS CRE OUTRAS BANDEIRAS',
                      'CR ANTECIPAÇÃO VISA', 'CR ANTECIPAÇÃO MASTERCARD',
                      'CR ANTECIPAÇÃO OUTRAS BANDEIRAS'}
SICOOB_CREDLIQ_MEMOS = {'CRÉD.TRANSF.POUPANÇA INTERCREDIS', 'CRED.TRANSF.CONTAS INTERCREDIS'}
SICOOB_CONVENIO_MEMOS = {'DÉB. CONV. SEGUROS', 'DÉB.CONV.TRIBUTOS FEDERAIS - RFB',
                         'DÉB.CONV.TELECOMUNICAÇÕES', 'DÉB.CONV.ORGÃOS GOV.'}

BUCKETS = [
    'A_conciliados', 'B_nao_conciliados', 'C_pix_recebidos', 'D_cred_liq_cobranca',
    'E_sipag_cielo', 'F_tarifas', 'H_rendefacil_entra', 'I_rendefacil_sai',
    'J_iof', 'K_antoninho', 'L_demais', 'M_juros',
]
# Ordem de saída no txt final (igual ao script original: por data e, dentro da
# mesma data, nesta ordem de prioridade — não é a mesma ordem de BUCKETS acima).
PRIORITY = {
    'A_conciliados': 0, 'K_antoninho': 1, 'B_nao_conciliados': 2,
    'C_pix_recebidos': 3, 'D_cred_liq_cobranca': 4, 'E_sipag_cielo': 5,
    'F_tarifas': 6, 'H_rendefacil_entra': 7, 'I_rendefacil_sai': 8,
    'J_iof': 9, 'M_juros': 10, 'L_demais': 11,
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


def classify_all(bb_txns, sicoob_txns, payables, ano_mes: str):
    """payables já deve ter passado por `preparar_fornecedores`. Devolve um
    dict {bucket: [Lancamento, ...]}."""
    pool = {}
    for p in payables:
        pool[(round(p.valor, 2), p.vencimento)] = p
    matched_keys = set()

    entries = {b: [] for b in BUCKETS}

    def add(bucket, date, debito, credito, valor, historico, complemento='', fornecedor_novo=False, score=1.0):
        # Ao contrário da Antoninho, aqui o complemento NÃO passa por
        # strip_accents: o arquivo de referência de julho/2026 mantém
        # acentos (ex. "TARIFA COBRANÇA", "DÉB.IOF", "BB RENDE FÁCIL").
        entries[bucket].append(Lancamento(_ddmmaaaa(date), str(debito), str(credito), historico,
                                           round(valor, 2), complemento, bucket,
                                           fornecedor_novo, score))

    def tenta_conciliar(bucket_ok, bucket_fallback, date, amt, bank, fallback_debito, fallback_credito):
        key = (round(-amt, 2), date)
        p = pool.get(key)
        if p is not None and key not in matched_keys:
            matched_keys.add(key)
            comp = f"{p.documento} {p.nome}"
            add(bucket_ok, date, p.conta_fornecedor, bank, -amt, '429', comp,
                fornecedor_novo=(p.match_score < 0.95), score=p.match_score)
        else:
            add(bucket_fallback, date, fallback_debito, fallback_credito, -amt, '429')

    unclassified = []

    # ---- BB ----
    for t in bb_txns:
        if t.date[:6] != ano_mes:
            continue
        date, amt, memo, name = t.date, t.amt, t.memo.strip(), t.name.strip()
        bank = BANK_BB

        if memo.startswith('PAGAMENTO DE BOLETO'):
            tenta_conciliar('A_conciliados', 'B_nao_conciliados', date, amt, bank, '506', '5')
        elif memo.startswith('PIX - ENVIADO') and 'ANTONINHO' in memo.upper():
            add('K_antoninho', date, ANTONINHO_ACCOUNT, bank, -amt, '370', memo)
        elif memo.startswith('PIX - ENVIADO'):
            key = (round(-amt, 2), date)
            p = pool.get(key)
            if p is not None and key not in matched_keys:
                matched_keys.add(key)
                add('A_conciliados', date, p.conta_fornecedor, bank, -amt, '429', f"{p.documento} {p.nome}",
                    fornecedor_novo=(p.match_score < 0.95), score=p.match_score)
            else:
                add('L_demais', date, '506', bank, -amt, '429', memo)
        elif memo.startswith('PIX - RECEBIDO') and 'CIELO' in memo.upper():
            add('E_sipag_cielo', date, bank, '504', amt, '371', memo)
        elif memo.startswith('PIX - RECEBIDO'):
            add('C_pix_recebidos', date, bank, '744', amt, '314', memo)
        elif memo.startswith('REDE VENDAS') or memo.startswith('REDECARD'):
            add('E_sipag_cielo', date, bank, '504', amt, '371', memo)
        elif memo in ('BB RENDE FÁCIL - RENDE FACIL', 'BB RENDE FÁCIL'):
            if amt > 0:
                add('H_rendefacil_entra', date, bank, '731', amt, '318', memo)
            else:
                add('I_rendefacil_sai', date, '731', bank, -amt, '204', memo)
        elif memo.startswith('TARIFA PACOTE DE SERVIÇOS'):
            add('F_tarifas', date, '698', bank, -amt, '233', memo)
        else:
            unclassified.append(dict(banco='BB', date=date, amt=amt, memo=memo))

    # ---- SICOOB ----
    for t in sicoob_txns:
        if t.date[:6] != ano_mes:
            continue
        date, amt, memo, name = t.date, t.amt, t.memo.strip(), t.name.strip()
        bank = BANK_SICOOB

        if memo in SICOOB_BOLETO_MEMOS:
            tenta_conciliar('A_conciliados', 'B_nao_conciliados', date, amt, bank, '506', '5')
        elif memo == 'TRANSF.REALIZADA PIX SICOOB' and 'ANTONINHO' in name.upper():
            add('K_antoninho', date, ANTONINHO_ACCOUNT, bank, -amt, '370', f"{memo} {name}")
        elif memo == 'TRANSF.REALIZADA PIX SICOOB':
            key = (round(-amt, 2), date)
            p = pool.get(key)
            if p is not None and key not in matched_keys:
                matched_keys.add(key)
                add('A_conciliados', date, p.conta_fornecedor, bank, -amt, '429', f"{p.documento} {p.nome}",
                    fornecedor_novo=(p.match_score < 0.95), score=p.match_score)
            else:
                add('L_demais', date, '506', bank, -amt, '429', f"{memo} {name}")
        elif memo == 'PIX EMITIDO OUTRA IF':
            key = (round(-amt, 2), date)
            p = pool.get(key)
            if p is not None and key not in matched_keys:
                matched_keys.add(key)
                add('A_conciliados', date, p.conta_fornecedor, bank, -amt, '429', f"{p.documento} {p.nome}",
                    fornecedor_novo=(p.match_score < 0.95), score=p.match_score)
            else:
                add('L_demais', date, '506', bank, -amt, '429', f"{memo} {name}")
        elif memo in ('PIX RECEBIDO - OUTRA IF', 'TRANSF.RECEBIDA - PIX SICOOB'):
            add('C_pix_recebidos', date, bank, '744', amt, '314', f"{memo} {name}")
        elif memo in SICOOB_CREDLIQ_MEMOS:
            add('D_cred_liq_cobranca', date, bank, '744', amt, '314', f"{memo} {name}")
        elif memo in SICOOB_SIPAG_MEMOS:
            add('E_sipag_cielo', date, bank, '504', amt, '371', memo)
        elif memo == 'TARIFA COBRANÇA':
            add('F_tarifas', date, '698', bank, -amt, '233', memo)
        elif memo == 'DÉB.IOF':
            add('J_iof', date, '718', bank, -amt, '252', memo)
        elif memo in SICOOB_CONVENIO_MEMOS:
            add('L_demais', date, '506', bank, -amt, '429', memo)
        elif memo == 'JUROS CONTA GARANTIDA':
            add('M_juros', date, '374', bank, -amt, '255', memo)
        else:
            unclassified.append(dict(banco='SICOOB', date=date, amt=amt, memo=memo))

    return entries, unclassified
