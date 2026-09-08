"""
Orquestra a conciliação bancária completa da Haroke Supermercado LTDA: lê os
2 extratos OFX (Banco do Brasil e Sicoob) + o Contas a Pagar + o Plano de
Contas, resolve a conta de cada fornecedor, classifica cada transação
(core.haroke.classify) e gera DOIS arquivos de saída (fixado em ago/2026,
mesmo padrão já usado pela Antoninho):

  * conciliação bancária: uma linha |6100| por transação de banco já
    identificada;
  * títulos sem pagamento localizado: uma linha |6100| por parcela do
    Contas a Pagar que não foi encontrada em nenhum dos 2 extratos (nem com
    a tolerância de 3 dias) — debito=conta do próprio fornecedor,
    credito=5 (conta transitória), historico=429. A Antoninho Atacado e
    Varejo (fornecedor, não a empresa-cliente) é EXCLUÍDA de propósito
    dessa lista: ela é paga por PIX em lote que raramente bate com um
    título isolado, então seus títulos em aberto não geram lançamento
    nenhum (ver Regras_Conciliacao_Haroke.md).

As linhas do txt de conciliação saem ordenadas por data e, dentro da mesma
data, pela mesma ordem de prioridade de categoria do script original já
validado contra o fechamento de julho/2026 — importante para o arquivo
gerado ficar byte-a-byte comparável ao de referência.
"""
from core.antoninho.ofx_parse import parse_ofx_file
from core.antoninho.payables import parse_payables_excel
from core.haroke.plano_de_contas import load_fornecedores
from core.haroke.classify import preparar_fornecedores, classify_all, BUCKETS, PRIORITY, NOMES_REGRA

NOME_FORNECEDOR_EXCLUIDO_PENDENCIAS = "ANTONINHO"  # substring, case-insensitive — ver docstring acima


def _value_str(v: float) -> str:
    return f"{v:.2f}".replace('.', ',')


def _ddmmaaaa(yyyymmdd: str) -> str:
    return f"{yyyymmdd[6:8]}/{yyyymmdd[4:6]}/{yyyymmdd[0:4]}"


def processar(bb_path: str, sicoob_path: str, contas_a_pagar_path: str, plano_de_contas_path: str,
              overrides: dict, ano_mes: str, regras_customizadas: list | None = None):
    """Devolve um dict com: entries (dict bucket -> [Lancamento]), unclassified
    (lançamentos de banco sem regra fixa nem regra personalizada — não
    deveria acontecer em uso normal), baixa_confianca (parcelas do Contas a
    Pagar cujo fornecedor foi achado por similaridade de nome com score <
    0.95, para revisão manual antes de gerar o txt definitivo), resumo
    (contagem/valor por categoria), titulos_sem_pagamento (parcelas do
    Contas a Pagar do período sem pagamento localizado, exceto Antoninho) e
    titulos_antoninho_ignorados (só para exibir na tela — não vira
    lançamento)."""
    payables = parse_payables_excel(contas_a_pagar_path)
    accounts = load_fornecedores(plano_de_contas_path)
    baixa_confianca = preparar_fornecedores(payables, accounts, overrides)

    bb_txns = parse_ofx_file(bb_path, '8')
    sicoob_txns = parse_ofx_file(sicoob_path, '551')

    entries, unclassified = classify_all(bb_txns, sicoob_txns, payables, ano_mes, regras_customizadas)

    resumo = {}
    for bucket in BUCKETS:
        itens = entries[bucket]
        total = sum(abs(l.valor) for l in itens)
        resumo[bucket] = (len(itens), total)

    titulos_sem_pagamento = []
    titulos_antoninho_ignorados = []
    for p in payables:
        if p.usado or p.vencimento[:6] != ano_mes:
            continue
        if NOME_FORNECEDOR_EXCLUIDO_PENDENCIAS in p.nome.upper():
            titulos_antoninho_ignorados.append(p)
            continue
        titulos_sem_pagamento.append(dict(
            date=_ddmmaaaa(p.vencimento), debito=p.conta_fornecedor, credito='5',
            valor=p.valor, complemento=f"{p.documento} {p.nome}",
        ))

    return dict(entries=entries, unclassified=unclassified, baixa_confianca=baixa_confianca,
                resumo=resumo, payables=payables, titulos_sem_pagamento=titulos_sem_pagamento,
                titulos_antoninho_ignorados=titulos_antoninho_ignorados)


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


def gerar_txt_titulos_sem_pagamento(titulos_sem_pagamento: list, cnpj: str) -> str:
    rows = sorted(titulos_sem_pagamento, key=lambda t: t['date'][6:10] + t['date'][3:5] + t['date'][0:2])
    lines = [f"|0000|{cnpj}|"]
    for t in rows:
        comp = (t['complemento'] or '')[:80]
        lines.append('|6000|X||||')
        lines.append(f"|6100|{t['date']}|{t['debito']}|{t['credito']}|{_value_str(t['valor'])}|429|{comp}||||")
    return '\r\n'.join(lines) + '\r\n'
