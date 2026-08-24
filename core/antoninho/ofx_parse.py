"""
Leitor genérico de extratos OFX para a Antoninho (Sicoob, Itaú e Banco do
Brasil). Ao contrário do OFX da APAE (só PIX recebido), aqui precisamos de
TODAS as transações do período, porque cada uma vira uma linha classificada
por uma das 12 regras (ver core/antoninho/classify.py).
"""
import re
from dataclasses import dataclass


@dataclass
class Txn:
    banco: str          # código contábil do banco: "551" Sicoob, "552" Itaú, "8" BB
    trntype: str
    date: str            # AAAAMMDD
    amt: float            # positivo = crédito (entrou), negativo = débito (saiu)
    fitid: str
    memo: str
    name: str


_STMTTRN_RE = re.compile(r'<STMTTRN>(.*?)</STMTTRN>', re.S)


def _tag(block: str, tag: str) -> str:
    m = re.search(rf'<{tag}>([^<\n\r]*)', block)
    return m.group(1).strip() if m else ''


def parse_ofx_text(text: str, banco: str) -> list[Txn]:
    out = []
    for block in _STMTTRN_RE.findall(text):
        date = _tag(block, 'DTPOSTED')[:8]
        amt_raw = _tag(block, 'TRNAMT')
        if not date or not amt_raw:
            continue
        out.append(Txn(
            banco=banco,
            trntype=_tag(block, 'TRNTYPE'),
            date=date,
            amt=float(amt_raw),
            fitid=_tag(block, 'FITID'),
            memo=_tag(block, 'MEMO'),
            name=_tag(block, 'NAME'),
        ))
    return out


def parse_ofx_file(path: str, banco: str) -> list[Txn]:
    # Os extratos observados vêm com CHARSET:1252 no cabeçalho, mas às vezes
    # o conteúdo real é utf-8; tentamos cp1252 (o padrão OFX) e recorremos a
    # utf-8 se aquele falhar. Qualquer mojibake residual em acentos não
    # atrapalha a classificação, que usa principalmente prefixos sem acento.
    for enc in ('cp1252', 'utf-8'):
        try:
            with open(path, encoding=enc, errors='strict') as f:
                text = f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        with open(path, encoding='cp1252', errors='replace') as f:
            text = f.read()
    return parse_ofx_text(text, banco)
