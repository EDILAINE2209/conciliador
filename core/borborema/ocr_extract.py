"""
Extração dos lançamentos a partir do extrato Bradesco (PDF) da Borborema.

Diferente do extrato da APAE (core.pdf_extract), esse PDF é uma imagem
escaneada — não tem camada de texto (`pdftotext` devolve vazio). Por isso
aqui usamos OCR (poppler-utils + tesseract) em vez de extração direta de
texto.

O extrato vem em duas colunas por página. OCR direto na página inteira
embaralha as linhas das duas colunas (uma linha da coluna da esquerda pode
aparecer colada com uma linha da coluna da direita). Para evitar isso,
cada página é recortada em duas metades (esquerda/direita, com uma pequena
sobreposição) e cada metade é OCRizada separadamente — isso preserva a
ordem de leitura de cada coluna.

IMPORTANTE — este é um extrator "melhor esforço": OCR em documento
escaneado erra (dígito trocado, "RECEBIDO" lido como "RECEBTDO", etc.), e
uma via física rasgada/cortada no scan pode perder dígitos de forma
irrecuperável (já aconteceu com o extrato de abril/2026 real). Por isso
o módulo de geração (core.borborema.generate) faz a conferência
automática do saldo de cada dia contra o "SALDO EM dd/mm" impresso no
extrato, e a página do app SEMPRE mostra a tabela de lançamentos extraída
para revisão/edição manual antes de gerar o .txt final — o app nunca
manda pro contador um lançamento que o OCR não conseguiu confirmar contra
o saldo do dia sem avisar.
"""
import re
import subprocess
import tempfile
import os
import unicodedata
from dataclasses import dataclass, field

from PIL import Image

DPI = 400
COL_OVERLAP = 0.01  # sobreposição entre as duas metades, pra não cortar um valor no meio


def strip_accents(s: str) -> str:
    if not s:
        return s
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


@dataclass
class RawLine:
    """Uma linha "candidata" de lançamento, ainda não classificada."""
    date: str            # dd/mm
    keyword_text: str    # trecho com o tipo do movimento (ex.: "PIX RECEBIDO")
    doc: str              # número do documento/NSU, se encontrado
    valor: float
    saida: bool           # True = débito (saiu da conta), False = crédito (entrou)
    complemento_lines: list = field(default_factory=list)  # linhas REM:/DES: seguintes
    raw: str = ""          # linha original (auditoria/debug)


def pdf_to_page_images(pdf_path: str, out_dir: str, dpi: int = DPI):
    """Roda `pdftoppm -png` e devolve a lista de caminhos das páginas, em ordem."""
    prefix = os.path.join(out_dir, "pg")
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-png", pdf_path, prefix],
        check=True, capture_output=True,
    )
    pages = sorted(
        (f for f in os.listdir(out_dir) if f.startswith("pg-") and f.endswith(".png")),
        key=lambda f: int(re.search(r"pg-(\d+)\.png", f).group(1)),
    )
    return [os.path.join(out_dir, f) for f in pages]


def split_columns(image_path: str, out_dir: str, tag: str):
    """Recorta a página em metade esquerda e metade direita (com sobreposição)
    e devolve os dois caminhos (esquerda, direita)."""
    img = Image.open(image_path)
    w, h = img.size
    overlap = int(w * COL_OVERLAP)
    left = img.crop((0, 0, w // 2 + overlap, h))
    right = img.crop((w // 2 - overlap, 0, w, h))
    left_path = os.path.join(out_dir, f"{tag}_L.png")
    right_path = os.path.join(out_dir, f"{tag}_R.png")
    left.save(left_path)
    right.save(right_path)
    return left_path, right_path


def ocr_image(image_path: str, psm: int = 6, lang: str = "eng") -> str:
    result = subprocess.run(
        ["tesseract", image_path, "stdout", "--psm", str(psm), "-l", lang],
        capture_output=True, text=True,
    )
    return result.stdout


def ocr_pdf_columns(pdf_path: str) -> str:
    """Devolve o texto OCR do documento inteiro, coluna por coluna (todas as
    colunas esquerdas de todas as páginas, na ordem, seguidas de todas as
    direitas) — a ordem de leitura de cada coluna fica preservada."""
    with tempfile.TemporaryDirectory() as tmp:
        pages = pdf_to_page_images(pdf_path, tmp)
        texts = []
        for i, page_path in enumerate(pages, start=1):
            left_path, right_path = split_columns(page_path, tmp, f"p{i}")
            texts.append(ocr_image(left_path))
            texts.append(ocr_image(right_path))
        return "\n".join(texts)


# --- Parsing das linhas OCR ---------------------------------------------

DATE_RE = re.compile(r'(\d{2}/\d{2})')
DOC_TOKEN_RE = re.compile(r'^\d{6,7}$')
# "SALDO" sai torto do OCR de formas variadas (SALBO, SALBDO, SAL80...) — o
# radical "SAL" seguido de "EM"/"ANTER" é bem mais estável que a palavra inteira.
SALDO_EM_STEM_RE = re.compile(r'\bSAL\w*\s+EM\b', re.I)
SALDO_ANTERIOR_RE = re.compile(r'\bSAL\w*\s+ANTER', re.I)
VALOR_ABSURDO = 200_000.0  # nenhum lançamento real deste extrato passa disso — acima é erro de parsing

# Linhas de continuação com o nome da contraparte
CONTRAPARTE_RE = re.compile(r'\b(?:REM|DES)\s*[:;.]?\s*(.+)$', re.I)

# Palavras-chave (radicais curtos, tolerantes a erro de OCR) que indicam que a
# linha é uma linha de lançamento (data + descrição + doc + valor), e não uma
# linha de cabeçalho/rodapé/continuação.
KEYWORD_STEMS = (
    'RECEB', 'ENVI', 'COBRAN', 'QRCODE', 'TARIFA', 'RENT', 'FACIL',
    'TELEFON', 'INTERNET', 'LUZ', 'ENERGIA', 'AGUA', 'ESGOTO',
    'SIMPLES', 'FEDERAL', 'SEFAZ', 'DAE', 'TRIB', 'DEBITO', 'AUTOMAT',
    'EXTRATO', 'VISA', 'COMPRA',
)


def _looks_like_txn_line(line_upper: str) -> bool:
    return any(k in line_upper for k in KEYWORD_STEMS)


def _parse_value_tokens(tokens):
    """tokens: os tokens da linha que vêm DEPOIS do número do documento (ou,
    se não achou documento, os últimos tokens da linha). Junta até 3 tokens
    a partir do fim tentando montar "<inteiro>,<centavos>" — o extrato às
    vezes imprime a vírgula/ponto com espaço em volta ("328 , 60") ou
    confunde o separador de milhar com vírgula ("1,526 ,23" = 1.526,23), daí
    juntar mais de um token quando o último isolado não fecha um valor
    válido. Devolve (valor, saida) ou (None, None)."""
    if not tokens:
        return None, None
    # tenta a maior sequência final de tokens "numéricos" primeiro (dígitos,
    # vírgula, ponto, menos) — senão "2, 664 , 26" (== 2.664,26) acaba lido
    # como só "664,26" porque um agrupamento menor já "fecha" um valor válido.
    numeric_tok_re = re.compile(r"^[\d,.\-']+$")
    max_n = 0
    for tok in reversed(tokens):
        if numeric_tok_re.match(tok):
            max_n += 1
        else:
            break
    max_n = max(max_n, 1)
    for n in range(min(max_n, 5), 0, -1):
        if n > len(tokens):
            continue
        joined_raw = ''.join(tokens[-n:])
        saida = joined_raw.rstrip().endswith('-')
        # remove qualquer lixo de OCR que não seja dígito/vírgula/ponto/menos
        # (aspas, barras, pontuação solta) antes de tentar interpretar
        cleaned = re.sub(r'[^0-9,.\-]', '', joined_raw).rstrip('-')
        if ',' not in cleaned:
            continue
        head, cents = cleaned.rsplit(',', 1)
        if not re.fullmatch(r'\d{2}', cents):
            continue
        digits = re.sub(r'\D', '', head)
        if not digits:
            continue
        try:
            valor = float(digits + '.' + cents)
        except ValueError:
            continue
        if valor >= VALOR_ABSURDO:
            continue
        return valor, saida
    # fallback raro: a vírgula decimal saiu como espaço e nada mais
    # ("5 94" em vez de "5,94") — só aceita se os 2 últimos tokens forem
    # dígitos puros, o último com exatamente 2 dígitos.
    if len(tokens) >= 2 and re.fullmatch(r'\d{2}-?', tokens[-1]) and re.fullmatch(r'\d{1,4}', tokens[-2]):
        saida = tokens[-1].endswith('-')
        try:
            valor = float(tokens[-2] + '.' + tokens[-1].rstrip('-'))
            if valor < VALOR_ABSURDO:
                return valor, saida
        except ValueError:
            pass
    return None, None


def parse_column_text(text: str):
    """Varre o texto OCR de uma coluna e devolve (raw_lines, checkpoints,
    saldo_anterior). checkpoints: {'dd/mm': saldo_impresso}."""
    raw_lines = []
    checkpoints = {}
    saldo_anterior = None
    current_date = None
    pending = None  # RawLine em construção, à espera de linhas REM:/DES:

    def flush():
        nonlocal pending
        if pending is not None:
            raw_lines.append(pending)
        pending = None

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        tokens = line.split()

        if SALDO_EM_STEM_RE.search(upper):
            m_date = DATE_RE.search(line)
            if m_date:
                idx = None
                for i, tok in enumerate(tokens):
                    if m_date.group(1) in tok:
                        idx = i
                        break
                valor, _ = _parse_value_tokens(tokens[idx + 1:] if idx is not None else [])
                if valor is not None:
                    flush()
                    checkpoints[m_date.group(1)] = valor
                    current_date = m_date.group(1)
                    continue

        if SALDO_ANTERIOR_RE.search(upper):
            valor, _ = _parse_value_tokens(tokens)
            if valor is not None and saldo_anterior is None:
                saldo_anterior = valor
            continue

        m_date = DATE_RE.match(tokens[0]) if tokens else None
        if m_date and _looks_like_txn_line(upper):
            doc_idx = None
            for i, tok in enumerate(tokens):
                if DOC_TOKEN_RE.match(tok):
                    doc_idx = i
                    break
            value_tokens = tokens[doc_idx + 1:] if doc_idx is not None else tokens[1:]
            valor, saida = _parse_value_tokens(value_tokens)
            if valor is not None:
                flush()
                current_date = m_date.group(1)
                pending = RawLine(
                    date=current_date,
                    keyword_text=upper,
                    doc=tokens[doc_idx] if doc_idx is not None else "",
                    valor=valor,
                    saida=bool(saida),
                    raw=line,
                )
                continue

        m_contra = CONTRAPARTE_RE.search(line)
        if m_contra and pending is not None:
            pending.complemento_lines.append(strip_accents(m_contra.group(1)).strip())
            continue

    flush()
    return raw_lines, checkpoints, saldo_anterior


def _dedup(raw_lines):
    """A faixa de sobreposição entre o recorte esquerdo e direito da coluna
    (COL_OVERLAP) às vezes cai bem em cima de uma linha de lançamento, que
    então é OCRizada (e lida) duas vezes — uma pelo recorte esquerdo, outra
    pelo direito, cada uma com um ruído de OCR levemente diferente. Aqui a
    gente deduplica pelo número do documento (o NSU é único por lançamento
    no extrato), mantendo a primeira leitura encontrada."""
    seen_docs = set()
    out = []
    for r in raw_lines:
        if r.doc:
            if r.doc in seen_docs:
                continue
            seen_docs.add(r.doc)
        out.append(r)
    return out


def extract(pdf_path: str):
    """Ponto de entrada principal. Devolve dict:
    {raw_lines, checkpoints, saldo_anterior}."""
    text = ocr_pdf_columns(pdf_path)
    raw_lines, checkpoints, saldo_anterior = parse_column_text(text)
    raw_lines = _dedup(raw_lines)
    # ordena por (data, ordem de aparição) — dd/mm sem ano, então ordenação
    # textual "dd/mm" já é cronológica dentro de um mesmo extrato mensal
    raw_lines.sort(key=lambda r: r.date)
    return {
        "raw_lines": raw_lines,
        "checkpoints": checkpoints,
        "saldo_anterior": saldo_anterior,
    }
