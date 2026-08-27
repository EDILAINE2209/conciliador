"""
Classificação dos lançamentos do extrato Bradesco da Borborema.

Mapa de contas reconstruído junto com a contadora a partir dos extratos de
abril, maio e junho/2026 (ver conversa de fechamento desses 3 meses). Regra
geral: a conta 9 (Banco Bradesco C/C) é sempre o lado automático — debitada
quando o dinheiro ENTRA na conta, creditada quando SAI. Por isso o mapa
abaixo guarda só a "contrapartida" (a outra conta) e o histórico; o lado
(débito/crédito) da conta 9 é decidido pelo sinal do lançamento (RawLine.saida).

Cada entrada de ACCOUNTS é (conta_contrapartida, historico). Quando
RawLine.saida é False (entrada/crédito): debito=9, credito=conta_contrapartida.
Quando saida é True (saída/débito): debito=conta_contrapartida, credito=9.
"""
from dataclasses import dataclass, field

CONTA_BANCO = "9"
CONTA_FORNEC_PADRAO = "506"  # "Pagto Cobranca" / fornecedores sem regra própria — mesmo padrão adotado nas outras empresas do app

ACCOUNTS = {
    "CIELO":        ("618", "315"),   # PIX Recebido - Cielo S.A.
    "BORB":         ("5",   "226"),   # PIX Recebido - Borborema Borborema E (maquininha/gateway próprio)
    "OUTROS_PIX":   ("618", "315"),   # PIX Recebido de remetente avulso (mesma conta do Cielo + complemento)
    "RENT":         ("432", "317"),   # Rent.Inv.Facil
    "ENVIADO":      ("5",   "313"),   # PIX Enviado
    "FORNEC":       ("506", "370"),   # Pagto Cobranca / Pix QRCode / Compra Visa (com complemento)
    "TELEFONE":     ("356", "70"),    # Conta Telefone/Internet
    "DEBAUTO":      ("370", "233"),   # Debito Automatico Cielo / Tarifa Bancaria Pix / Tar Extrato
    "LUZ":          ("354", "454"),   # Conta de Luz
    "AGUA":         ("355", "462"),   # Conta Agua/Esgoto
    "TRIB":         ("526", "270"),   # Pgto Elet Trib - Sefaz/DAE (estadual)
    "TRIB_SIMPLES": ("490", "90"),    # Pgto Elet Trib - Simples Nacional
    "TRIB_FEDERAL": ("191", "271"),   # Pgto Elet Trib - Receita Federal
}

NOMES_CATEGORIA = {
    "CIELO": "PIX Recebido — Cielo",
    "BORB": "PIX Recebido — Borborema/maquininha",
    "OUTROS_PIX": "PIX Recebido — outros remetentes",
    "RENT": "Rendimento Rent.Invest.Fácil",
    "ENVIADO": "PIX Enviado",
    "FORNEC": "Pagamento a fornecedor (cobrança/QRCode/Visa)",
    "TELEFONE": "Conta de telefone/internet",
    "DEBAUTO": "Débito automático / tarifa Cielo",
    "LUZ": "Conta de luz",
    "AGUA": "Conta de água/esgoto",
    "TRIB": "Tributo estadual (Sefaz/DAE)",
    "TRIB_SIMPLES": "Simples Nacional",
    "TRIB_FEDERAL": "Receita Federal",
}


@dataclass
class Lancamento:
    date: str          # dd/mm (o generate.py acrescenta o /aaaa)
    debito: str
    credito: str
    historico: str
    valor: float
    complemento: str = ""
    categoria: str = ""
    origem: object = field(default=None, repr=False)  # RawLine de origem (auditoria)
    revisar: bool = False    # não foi possível classificar com confiança -> revisão manual


def _complemento(raw) -> str:
    return " ".join(l for l in raw.complemento_lines if l).strip()[:60]


def classify_raw(raw):
    """raw: core.borborema.ocr_extract.RawLine. Devolve um Lancamento —
    nunca None: um lançamento não reconhecido vira categoria "" com
    revisar=True, pra aparecer na tela de conferência do app em vez de
    ser descartado silenciosamente."""
    t = raw.keyword_text

    def lanc(categoria, complemento="", contraparte_override=None):
        conta_contra, hist = contraparte_override or ACCOUNTS[categoria]
        if raw.saida:
            deb, cred = conta_contra, CONTA_BANCO
        else:
            deb, cred = CONTA_BANCO, conta_contra
        return Lancamento(raw.date, deb, cred, hist, raw.valor, complemento, categoria, raw)

    if 'TARIFA' in t or ('DEBITO' in t and 'AUTOMAT' in t) or ('TAR' in t and 'EXTRATO' in t):
        return lanc("DEBAUTO")

    if 'RENT' in t and 'FACIL' in t:
        return lanc("RENT")

    if 'RECEB' in t:
        comp_upper = _complemento(raw).upper()
        if 'CIELO' in comp_upper:
            return lanc("CIELO")
        if 'BORBOREMA' in comp_upper:
            return lanc("BORB")
        return lanc("OUTROS_PIX", complemento=_complemento(raw))

    if 'ENVI' in t:
        return lanc("ENVIADO")

    if 'COBRAN' in t or 'QRCODE' in t or ('COMPRA' in t and 'VISA' in t):
        return lanc("FORNEC", complemento=_complemento(raw))

    if 'TELEFON' in t or 'INTERNET' in t:
        return lanc("TELEFONE")

    if 'LUZ' in t or 'ENERGIA' in t:
        return lanc("LUZ")

    if 'AGUA' in t or 'ESGOTO' in t:
        return lanc("AGUA")

    if 'SIMPLES' in t:
        return lanc("TRIB_SIMPLES")

    if 'FEDERAL' in t or 'DARF' in t:
        return lanc("TRIB_FEDERAL")

    if 'SEFAZ' in t or 'DAE' in t or 'TRIB' in t:
        return lanc("TRIB")

    # não reconhecido: manda pra revisão manual em vez de adivinhar
    deb, cred = (CONTA_FORNEC_PADRAO, CONTA_BANCO) if raw.saida else (CONTA_BANCO, CONTA_FORNEC_PADRAO)
    return Lancamento(raw.date, deb, cred, "370", raw.valor, _complemento(raw) or raw.raw[:60],
                       categoria="", origem=raw, revisar=True)
