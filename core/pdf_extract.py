"""
Extração dos recibos de doação a partir do PDF "Relatório de Faturamento".

Usa `pdftotext -layout` (poppler-utils) em vez de OCR/visão, porque o texto
completo dos nomes dos doadores está presente na camada de texto do PDF
mesmo quando a renderização visual corta o nome na tabela.
"""
import re
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass


DATE_HEADER_RE = re.compile(r'^\s*(\d{2}/\d{2}/\d{4})\s*$')
RS_RE = re.compile(r'R\$\s*([\d.]+,\d{2})')
TIPO_RE = re.compile(r'(FISICA|JURIDICA)')
SECTION_RE = re.compile(r'^\s*(FISICA|JURIDICA)\s*$')

TOTAL_FISICA_RE = re.compile(
    r'Total Pessoa FISICA\s+(\d+)\s+recibos\s+Recebido R\$\s*([\d.]+,\d{2})', re.I)
TOTAL_JURIDICA_RE = re.compile(
    r'Total Pessoa JURIDICA\s+(\d+)\s+recibos\s+Recebido R\$\s*([\d.]+,\d{2})', re.I)
TOTAL_GERAL_RE = re.compile(r'Total Geral\s+(\d+)\s+recibos', re.I)
TOTAL_RECEBIDO_RE = re.compile(r'Total Recebido R\$\s*([\d.]+,\d{2})', re.I)


@dataclass
class Record:
    date: str        # dd/mm/aaaa (data do cabeçalho cinza no relatório)
    tipo: str         # FISICA | JURIDICA
    donor: str        # "ID - NOME" tal como aparece no relatório
    valor: str        # valor bruto, formato "1.234,56"
    recebido: str     # valor recebido, formato "1.234,56"


@dataclass
class ExtractionResult:
    records: list
    totals: dict       # {'fisica_count', 'fisica_total', 'juridica_count',
                        #  'juridica_total', 'geral_count', 'geral_total'}
    warnings: list      # inconsistências encontradas (contagem/soma não bate)


def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def to_float(s: str) -> float:
    return float(s.replace('.', '').replace(',', '.'))


def pdf_to_text(pdf_path: str) -> str:
    """Roda `pdftotext -layout` e devolve o texto extraído."""
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ['pdftotext', '-layout', pdf_path, tmp_path],
            check=True, capture_output=True,
        )
        with open(tmp_path, encoding='utf-8', errors='replace') as f:
            return f.read()
    finally:
        import os
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _next_nonblank(lines, idx):
    j = idx + 1
    while j < len(lines) and lines[j].strip() == '':
        j += 1
    return lines[j].strip() if j < len(lines) else ''


def _is_date_line(s):
    return bool(DATE_HEADER_RE.match(s))


def _flush_buffer(buf):
    combined = ' '.join(s.strip() for s in buf if s.strip())
    m = TIPO_RE.search(combined)
    if not m:
        return None
    tipo = m.group(1)
    donor_part = combined[:m.start()].strip()
    rest = combined[m.end():].strip()
    amounts = RS_RE.findall(rest)
    if len(amounts) != 2:
        return None
    valor, recebido = amounts
    donor_clean = re.sub(r'\s+', ' ', donor_part).strip()
    donor_clean = re.sub(r'\s*-\s*$', '', donor_clean).strip()
    return donor_clean, tipo, valor, recebido


def parse_report_text(text: str) -> ExtractionResult:
    """Extrai os registros de doação e os totais impressos no relatório."""
    lines = [l.rstrip('\n') for l in text.split('\n')]

    current_date = None
    records = []
    buffer = []
    warnings = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        m = DATE_HEADER_RE.match(line)
        if m:
            nb = _next_nonblank(lines, i)
            if nb.startswith('Doador'):
                current_date = m.group(1)
                continue
            # fragmento de data dentro de um nome de doador quebrado em várias linhas
            buffer.append(line)
            amounts_so_far = RS_RE.findall(' '.join(buffer))
            if len(amounts_so_far) >= 2:
                rec = _flush_buffer(buffer)
                if rec:
                    donor, tipo, valor, recebido = rec
                    records.append(Record(current_date, tipo, donor, valor, recebido))
                else:
                    warnings.append(f"Falha ao interpretar bloco: {buffer}")
                buffer = []
            continue

        if SECTION_RE.match(line):
            nb = _next_nonblank(lines, i)
            if _is_date_line(nb):
                continue

        if stripped.startswith('Total') or stripped.startswith('Data '):
            continue
        if stripped.startswith('Doador'):
            continue
        if stripped.startswith('RELATÓRIO') or stripped.startswith('RELAT') or \
           stripped.startswith('APAE') or stripped.startswith('R. GLETE') or \
           stripped.startswith('Baixa'):
            continue

        buffer.append(line)
        amounts_so_far = RS_RE.findall(' '.join(buffer))
        if len(amounts_so_far) >= 2:
            rec = _flush_buffer(buffer)
            if rec:
                donor, tipo, valor, recebido = rec
                records.append(Record(current_date, tipo, donor, valor, recebido))
            else:
                warnings.append(f"Falha ao interpretar bloco: {buffer}")
            buffer = []

    if buffer:
        warnings.append(f"Bloco não finalizado ao fim do arquivo: {buffer}")

    # Totais impressos no próprio relatório, para conferência
    totals = {
        'fisica_count': None, 'fisica_total': None,
        'juridica_count': None, 'juridica_total': None,
        'geral_count': None, 'geral_total': None,
    }
    mf = TOTAL_FISICA_RE.search(text)
    if mf:
        totals['fisica_count'] = int(mf.group(1))
        totals['fisica_total'] = to_float(mf.group(2))
    mj = TOTAL_JURIDICA_RE.search(text)
    if mj:
        totals['juridica_count'] = int(mj.group(1))
        totals['juridica_total'] = to_float(mj.group(2))
    mg = TOTAL_GERAL_RE.search(text)
    if mg:
        totals['geral_count'] = int(mg.group(1))
    mr = TOTAL_RECEBIDO_RE.search(text)
    if mr:
        totals['geral_total'] = to_float(mr.group(1))

    # Conferência automática contra os totais impressos
    if totals['geral_count'] is not None and len(records) != totals['geral_count']:
        warnings.append(
            f"Quantidade de recibos extraídos ({len(records)}) difere do "
            f"'Total Geral' impresso no relatório ({totals['geral_count']})."
        )
    soma = round(sum(to_float(r.recebido) for r in records), 2)
    if totals['geral_total'] is not None and abs(soma - totals['geral_total']) > 0.01:
        warnings.append(
            f"Soma dos valores extraídos (R$ {soma:.2f}) difere do "
            f"'Total Recebido' impresso no relatório (R$ {totals['geral_total']:.2f})."
        )

    return ExtractionResult(records=records, totals=totals, warnings=warnings)


def extract_from_pdf(pdf_path: str) -> ExtractionResult:
    text = pdf_to_text(pdf_path)
    return parse_report_text(text)
