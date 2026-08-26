"""
Orquestra a conciliação bancária completa da Haroke Supermercado LTDA: lê os
2 extratos OFX (Banco do Brasil e Sicoob) + o Contas a Pagar + o Plano de
Contas, resolve a conta de cada fornecedor, classifica cada transação
(core.haroke.classify) e gera o único arquivo de saída no layout do mês
(diferente da Antoninho, aqui não há um segundo arquivo de "pendências" —
ver Regras_Conciliacao_Haroke.md).

As linhas do txt saem ordenadas por data e, dentro da mesma data, pela
mesma ordem de prioridade de categoria do script original já validado
contra o fechamento de julho/2026 — importante para o arquivo gerado ficar
byte-a-byte comparável ao de referência.
"""
from collections import defaultdict

from core.antoninho.ofx_parse import parse_ofx_file
from core.antoninho.payables import parse_payables_excel
from core.haroke.plano_de_contas import load_fornecedores
from core.haroke.classify import preparar_fornecedores, classify_all, BUCKETS, PRIORITY, NOMES_REGRA


def _value_str(v: float) -> str:
    return f"{v:.2f}".replace('.', ',')


def processar(bb_path: str, sicoob_path: str, contas_a_pagar_path: str, plano_de_contas_path: str,
              overrides: dict, ano_mes: str):
    """Devolve um dict com: entries (dict bucket -> [Lancamento]), unclassified
    (lançamentos de banco sem regra — não deveria acontecer em uso normal),
    baixa_confianca (parcelas do Contas a Pagar cujo fornecedor foi achado
    por similaridade de nome com score < 0.95, para revisão manual antes de
    gerar o txt definitivo), e resumo (contagem/valor por categoria)."""
    payables = parse_payables_excel(contas_a_pagar_path)
    accounts = load_fornecedores(plano_de_contas_path)
    baixa_confianca = preparar_fornecedores(payables, accounts, overrides)

    bb_txns = parse_ofx_file(bb_path, '8')
    sicoob_txns = parse_ofx_file(sicoob_path, '551')

    entries, unclassified = classify_all(bb_txns, sicoob_txns, payables, ano_mes)

    resumo = {}
    for bucket in BUCKETS:
        itens = entries[bucket]
        total = sum(abs(l.valor) for l in itens)
        resumo[bucket] = (len(itens), total)

    return dict(entries=entries, unclassified=unclassified, baixa_confianca=baixa_confianca,
                resumo=resumo, payables=payables)


def gerar_txt(entries: dict, cnpj: str) -> str:
    all_rows = []
    for bucket, itens in entries.items():
        prio = PRIORITY[bucket]
        for l in itens:
            all_rows.append((l.date, prio, l))
    # l.date está em DD/MM/AAAA; para ordenar corretamente por data
    # convertemos para AAAAMMDD só como chave de ordenação.
    all_rows.sort(key=lambda x: (x[0][6:10] + x[0][3:5] + x[0][0:2], x[1]))

    lines = [f"|0000|{cnpj}|"]
    for _, _, l in all_rows:
        # o layout limita o complemento a 80 caracteres (mesmo corte do
        # script original já validado contra o fechamento de julho/2026).
        comp = (l.complemento or '')[:80]
        lines.append('|6000|X||||')
        lines.append(f"|6100|{l.date}|{l.debito}|{l.credito}|{_value_str(l.valor)}|{l.historico}|{comp}||||")
    return '\r\n'.join(lines) + '\r\n'
