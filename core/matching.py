"""
Casamento (reconciliação) entre os recibos do relatório de doações e os
PIX recebidos no extrato bancário, por nome + valor.
"""
import re
import unicodedata
from dataclasses import dataclass, field


def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def norm_name(s: str) -> str:
    s = strip_accents(s).upper()
    s = re.sub(r'[^A-Z0-9]', '', s)
    return s


def to_float(s: str) -> float:
    return float(s.replace('.', '').replace(',', '.'))


@dataclass
class ReportEntry:
    index: int          # posição no relatório original (ordem de geração do txt)
    date: str            # dd/mm/aaaa do cabeçalho cinza
    tipo: str             # FISICA | JURIDICA
    donor_id: str
    donor_name: str
    donor_name_norm: str
    valor: str            # bruto, "1.234,56"
    recebido: str         # bruto, "1.234,56"
    recebido_f: float
    raw: str              # "ID - NOME" como no relatório
    matched_pix: object = None   # PixTransaction, se casado
    ambiguous_with: list = field(default_factory=list)  # outros candidatos


def build_report_entries(records) -> list:
    entries = []
    for i, r in enumerate(records):
        m = re.match(r'\s*(\d+)\s*-\s*(.*)', r.donor)
        donor_id = m.group(1) if m else ''
        donor_name = m.group(2).strip() if m else r.donor
        entries.append(ReportEntry(
            index=i,
            date=r.date,
            tipo=r.tipo,
            donor_id=donor_id,
            donor_name=donor_name,
            donor_name_norm=norm_name(donor_name),
            valor=r.valor,
            recebido=r.recebido,
            recebido_f=to_float(r.recebido),
            raw=r.donor,
        ))
    return entries


def match(report_entries, pix_list, tolerance=0.005, min_name_len=4):
    """
    Casamento guloso um-para-um: PIX recebido casa com um lançamento do
    relatório se o valor bate (tolerância de R$0,005) e o nome do doador
    do relatório começa com o nome truncado que vem do extrato.

    Retorna (matched, unmatched_pix, ambiguous) onde:
      - matched: lista de (pix, report_entry)
      - unmatched_pix: lista de PixTransaction sem candidato
      - ambiguous: lista de (pix, [candidatos]) quando há mais de 1 candidato
    """
    used = [False] * len(report_entries)
    matched = []
    unmatched_pix = []
    ambiguous = []

    for pix in pix_list:
        if not pix.name_norm or len(pix.name_norm) < min_name_len:
            candidates = []
        else:
            candidates = [
                e for i, e in enumerate(report_entries)
                if not used[i]
                and abs(e.recebido_f - pix.amt) <= tolerance
                and e.donor_name_norm.startswith(pix.name_norm)
            ]
        if len(candidates) == 1:
            e = candidates[0]
            idx = report_entries.index(e)
            used[idx] = True
            e.matched_pix = pix
            matched.append((pix, e))
        elif len(candidates) == 0:
            unmatched_pix.append(pix)
        else:
            ambiguous.append((pix, candidates))

    return matched, unmatched_pix, ambiguous
