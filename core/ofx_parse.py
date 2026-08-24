"""
Extração das transações PIX recebidas a partir do extrato OFX do banco.
"""
import re
import unicodedata
from dataclasses import dataclass


MEMO_RE = re.compile(
    r'PIX\s*-?\s*RECEBIDO(?:\s*QR CODE)?\s*-\s*(\d{2}/\d{2})\s+(\d{2}:\d{2})\s+(\S+)\s+(.*)',
    re.I,
)


def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def norm_name(s: str) -> str:
    s = strip_accents(s).upper()
    s = re.sub(r'[^A-Z0-9]', '', s)
    return s


@dataclass
class PixTransaction:
    dtposted: str
    amt: float
    memo: str
    fitid: str
    real_date: str   # dd/mm, extraído do MEMO (mais confiável que DTPOSTED)
    real_time: str
    doc: str
    name_raw: str
    name_norm: str


def _field(block: str, tag: str):
    m = re.search(rf'<{tag}>([^\n<]*)', block)
    return m.group(1).strip() if m else None


def parse_ofx_text(content: str, year: str) -> list:
    """
    Extrai as transações PIX recebidas (TRNTYPE=DEP + memo contendo
    'PIX' e 'RECEBID'). `year` é usado para completar a data (o extrato
    só traz dd/mm no memo).
    """
    blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', content, re.S)
    pix_list = []
    for b in blocks:
        trntype = _field(b, 'TRNTYPE')
        amt = _field(b, 'TRNAMT')
        memo = _field(b, 'MEMO')
        dtposted = _field(b, 'DTPOSTED')
        fitid = _field(b, 'FITID')
        if trntype != 'DEP' or not memo:
            continue
        if 'PIX' not in memo.upper() or 'RECEBID' not in memo.upper():
            continue
        m = MEMO_RE.search(memo)
        if m:
            real_date, real_time, doc, name = m.groups()
        else:
            real_date, real_time, doc, name = None, None, None, memo
        name = name.strip()
        pix_list.append(PixTransaction(
            dtposted=dtposted,
            amt=float(amt),
            memo=memo,
            fitid=fitid,
            real_date=real_date,
            real_time=real_time,
            doc=doc,
            name_raw=name,
            name_norm=norm_name(name),
        ))
    return pix_list


def parse_ofx_file(path: str, year: str) -> list:
    with open(path, encoding='latin-1', errors='replace') as f:
        content = f.read()
    return parse_ofx_text(content, year)


def real_date_full(pix: PixTransaction, year: str) -> str:
    """Converte 'dd/mm' (do memo) em 'dd/mm/aaaa'."""
    if pix.real_date:
        dd, mm = pix.real_date.split('/')
        return f"{dd}/{mm}/{year}"
    # fallback: usa DTPOSTED (formato yyyymmdd...) se o memo não tiver data
    if pix.dtposted and len(pix.dtposted) >= 8:
        yyyy, mm, dd = pix.dtposted[0:4], pix.dtposted[4:6], pix.dtposted[6:8]
        return f"{dd}/{mm}/{yyyy}"
    return f"01/01/{year}"
