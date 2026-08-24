"""
Geração do arquivo .txt de importação contábil no formato pipe-delimited:

  |0000|CNPJ|
  |6000|X||||
  |6100|data|conta_debito|conta_credito|valor|hist|complemento||||

Terminação de linha CRLF (\\r\\n), igual ao modelo de referência do sistema
contábil usado pela APAE.
"""
import unicodedata

from .ofx_parse import real_date_full


def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _value_str(v: float) -> str:
    return f"{v:.2f}".replace('.', ',')


def generate_txt(report_entries, unmatched_pix, pix_classification, config, year: str) -> tuple:
    """
    report_entries: lista de ReportEntry (com .matched_pix preenchido para os
        que foram confirmados pelo extrato bancário).
    unmatched_pix: lista de PixTransaction sem correspondência no relatório.
    pix_classification: dict {fitid: nome_da_regra_especial ou None}
        None (ou ausente) = tratamento padrão (debita 7, credita conta
        suspensa, histórico vazio, complemento = memo do banco).
    config: dict carregado de core.config.load_config().
    year: ano (string) usado para completar datas do extrato.

    Retorna (linhas_txt: list[str], resumo: dict).
    """
    contas = config['contas']
    hist_doacao = config['historico_doacao']
    regras = {r['nome']: r for r in config.get('regras_especiais', [])}

    out_lines = [f"|0000|{config['cnpj']}|"]

    count_confirmado = 0
    count_pendente = 0
    total_doacoes = 0.0

    for e in report_entries:
        code = contas['doacao_pf'] if e.tipo == 'FISICA' else contas['doacao_pj']
        donor_ascii = strip_accents(e.raw).upper()
        if e.matched_pix is not None:
            debit = contas['banco']
            final_date = real_date_full(e.matched_pix, year)
            count_confirmado += 1
        else:
            debit = contas['suspensa']
            final_date = e.date
            count_pendente += 1
        total_doacoes += e.recebido_f
        out_lines.append('|6000|X||||')
        out_lines.append(
            f"|6100|{final_date}|{debit}|{code}|{_value_str(e.recebido_f)}|{hist_doacao}|{donor_ascii}||||"
        )

    def sort_key(p):
        d = real_date_full(p, year)
        dd, mm, yyyy = d.split('/')
        return (yyyy, mm, dd)

    count_especial = {}
    total_especial = {}
    count_banco_pendente = 0
    total_banco_pendente = 0.0

    for p in sorted(unmatched_pix, key=sort_key):
        date = real_date_full(p, year)
        value_str = _value_str(p.amt)
        memo = strip_accents(p.memo.strip())
        regra_nome = pix_classification.get(p.fitid)
        out_lines.append('|6000|X||||')
        if regra_nome and regra_nome in regras:
            r = regras[regra_nome]
            out_lines.append(
                f"|6100|{date}|{contas['banco']}|{r['conta_credito']}|{value_str}|{r['historico']}|{memo}||||"
            )
            count_especial[regra_nome] = count_especial.get(regra_nome, 0) + 1
            total_especial[regra_nome] = total_especial.get(regra_nome, 0.0) + p.amt
        else:
            out_lines.append(
                f"|6100|{date}|{contas['banco']}|{contas['suspensa']}|{value_str}||{memo}||||"
            )
            count_banco_pendente += 1
            total_banco_pendente += p.amt

    resumo = {
        'total_doacoes': round(total_doacoes, 2),
        'count_confirmado': count_confirmado,
        'count_pendente': count_pendente,
        'count_banco_pendente': count_banco_pendente,
        'total_banco_pendente': round(total_banco_pendente, 2),
        'count_especial': count_especial,
        'total_especial': {k: round(v, 2) for k, v in total_especial.items()},
        'total_linhas': len(out_lines),
    }
    return out_lines, resumo


def write_txt(out_lines, path):
    with open(path, 'w', encoding='utf-8', newline='\r\n') as f:
        for l in out_lines:
            f.write(l + '\n')
