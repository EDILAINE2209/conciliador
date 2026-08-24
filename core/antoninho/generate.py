"""
Orquestra a conciliação bancária completa da Antoninho: lê os 3 extratos
OFX + o Contas a Pagar, classifica cada transação (core.antoninho.classify)
e gera os dois arquivos de saída no mesmo layout usado nos meses anteriores:

  * conciliação bancária: uma linha |6100| por transação de banco já
    identificada (recebimentos, pagamentos, tarifas, etc.)
  * pendências do Contas a Pagar: uma linha |6100| por parcela que venceu
    no mês e não foi encontrada em nenhum dos 3 extratos (debito=fornecedor,
    credito=5 "conta transitória" — vira o banco de verdade quando for paga
    num mês seguinte). Fornecedores sem conta própria (506) aparecem
    invertidos nessa lista (debito=5, credito=506) — mesmo padrão observado
    nos dois arquivos de pendências de julho/2026 usados como referência.
"""
from collections import Counter, defaultdict

from core.antoninho.ofx_parse import parse_ofx_file
from core.antoninho.payables import parse_payables_excel
from core.antoninho.classify import PayableMatcher, classify_txn, strip_accents

NOMES_REGRA = {
    '314': 'PIX recebidos (Sicoob)',
    '371': 'Cartão / maquininha (SIPAG, Cielo, Rede)',
    '233': 'Tarifas bancárias',
    '252': 'IOF',
    '255': 'Juros',
    '204': 'BB Rende Fácil (aplicação)',
    '318': 'BB Rende Fácil (resgate)',
    '429': 'Pagamentos a fornecedores',
    '370': 'Demais movimentos',
}


def _value_str(v: float) -> str:
    return f"{v:.2f}".replace('.', ',')


def processar(ofx_paths: dict, contas_a_pagar_path: str, cadastro: dict, ano_mes: str):
    """ofx_paths: {"551": path_sicoob, "552": path_itau, "8": path_bb}.
    Devolve um dict com: lancamentos (bancários, classificados),
    pendencias (parcelas não encontradas no banco), resumo (contagem/valor
    por regra) e novos_fornecedores (fids que caíram em 506 sem cadastro,
    para revisão manual antes de gerar o txt definitivo)."""
    payables = parse_payables_excel(contas_a_pagar_path)
    matcher = PayableMatcher(payables)

    txns = []
    for banco, path in ofx_paths.items():
        if path:
            txns.extend(parse_ofx_file(path, banco))

    lancamentos = []
    novos_fornecedores = {}
    for t in txns:
        l = classify_txn(t, matcher, cadastro, ano_mes)
        if l is None:
            continue
        lancamentos.append(l)
        if l.fornecedor_novo:
            novos_fornecedores[l.complemento] = novos_fornecedores.get(l.complemento, 0) + 1

    pendencias = []
    for p in payables:
        if p.usado or p.vencimento[:6] != ano_mes:
            continue
        from core.antoninho.cadastro import get_conta
        conta, achou = get_conta(cadastro, p.fid, p.nome)
        data = f"{p.vencimento[6:8]}/{p.vencimento[4:6]}/{p.vencimento[0:4]}"
        complemento = strip_accents(f"{p.fid} - {p.nome}")
        if achou:
            pendencias.append(dict(date=data, debito=conta, credito='5', valor=p.valor, complemento=complemento))
        else:
            # fornecedor sem conta própria: padrão observado é inverter (debito=5, credito=506)
            pendencias.append(dict(date=data, debito='5', credito=conta, valor=p.valor, complemento=complemento))
            novos_fornecedores[complemento] = novos_fornecedores.get(complemento, 0) + 1

    resumo = defaultdict(lambda: [0, 0.0])
    for l in lancamentos:
        resumo[l.historico][0] += 1
        resumo[l.historico][1] += l.valor

    return dict(lancamentos=lancamentos, pendencias=pendencias, resumo=dict(resumo),
                novos_fornecedores=novos_fornecedores)


def gerar_txt_conciliacao(lancamentos, cnpj: str) -> str:
    lines = [f"|0000|{cnpj}|"]
    for l in lancamentos:
        lines.append('|6000|X||||')
        lines.append(f"|6100|{l.date}|{l.debito}|{l.credito}|{_value_str(l.valor)}|{l.historico}|{l.complemento}||||")
    return '\r\n'.join(lines) + '\r\n'


def gerar_txt_pendencias(pendencias, cnpj: str) -> str:
    lines = [f"|0000|{cnpj}|"]
    for p in pendencias:
        lines.append('|6000|X||||')
        lines.append(f"|6100|{p['date']}|{p['debito']}|{p['credito']}|{_value_str(p['valor'])}|429|{p['complemento']}||||")
    return '\r\n'.join(lines) + '\r\n'
