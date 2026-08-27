"""
Orquestra a geração do .txt de lançamentos contábeis da Borborema a partir
do extrato Bradesco em PDF: OCR (core.borborema.ocr_extract) + classificação
(core.borborema.classify) + conferência automática do saldo diário.

A conferência do saldo é o principal mecanismo de segurança contra erro de
OCR: pra cada dia com um "SALDO EM dd/mm" impresso no extrato, o saldo
calculado (saldo anterior + entradas − saídas) tem que bater exatamente.
Se não bater, TODOS os lançamentos daquele dia são marcados para revisão —
mesma lógica usada (manualmente) para fechar abril, maio e junho/2026 antes
deste módulo existir.
"""
from collections import defaultdict

from core.borborema.ocr_extract import extract
from core.borborema.classify import classify_raw, NOMES_CATEGORIA, CONTA_BANCO


def _value_str(v: float) -> str:
    return f"{v:.2f}".replace('.', ',')


def _dia_saldo_delta(lanc):
    if lanc.debito == CONTA_BANCO:
        return lanc.valor
    if lanc.credito == CONTA_BANCO:
        return -lanc.valor
    return 0.0


def processar(pdf_path: str):
    """Devolve um dict com:
      lancamentos       - lista de Lancamento (todos, inclusive os marcados p/ revisão)
      resumo            - {categoria: [qtd, soma]}
      saldo_anterior    - saldo impresso no extrato antes do 1º dia (ou None se não achou)
      checkpoints       - {'dd/mm': saldo impresso}
      dias_divergentes  - {'dd/mm': (saldo_calculado, saldo_impresso)}
      total_revisar     - quantos lançamentos vieram sem classificação confiável
    """
    extraido = extract(pdf_path)
    raw_lines = extraido["raw_lines"]
    checkpoints = extraido["checkpoints"]
    saldo_anterior = extraido["saldo_anterior"]

    lancamentos = [classify_raw(r) for r in raw_lines]

    por_dia = defaultdict(list)
    for l in lancamentos:
        por_dia[l.date].append(l)

    dias_ordenados = sorted(por_dia.keys(), key=lambda d: int(d.split('/')[0]))

    dias_divergentes = {}
    if saldo_anterior is not None:
        saldo = saldo_anterior
        for dia in dias_ordenados:
            for l in por_dia[dia]:
                saldo += _dia_saldo_delta(l)
            esperado = checkpoints.get(dia)
            if esperado is not None:
                if abs(saldo - esperado) >= 0.005:
                    dias_divergentes[dia] = (saldo, esperado)
                    for l in por_dia[dia]:
                        l.revisar = True
                    saldo = esperado  # realinha pro próximo dia não propagar o mesmo erro

    resumo = defaultdict(lambda: [0, 0.0])
    for l in lancamentos:
        chave = l.categoria or "NAO_CLASSIFICADO"
        resumo[chave][0] += 1
        resumo[chave][1] += l.valor

    return dict(
        lancamentos=lancamentos,
        resumo=dict(resumo),
        saldo_anterior=saldo_anterior,
        checkpoints=checkpoints,
        dias_divergentes=dias_divergentes,
        total_revisar=sum(1 for l in lancamentos if l.revisar),
    )


def gerar_txt(lancamentos, cnpj: str, ano: str) -> str:
    lines = [f"|0000|{cnpj}|"]
    for l in lancamentos:
        lines.append('|6000|X||||')
        data_completa = f"{l.date}/{ano}"
        if l.complemento:
            lines.append(f"|6100|{data_completa}|{l.debito}|{l.credito}|{_value_str(l.valor)}|{l.historico}|{l.complemento}||||")
        else:
            lines.append(f"|6100|{data_completa}|{l.debito}|{l.credito}|{_value_str(l.valor)}|{l.historico}|||||")
    return '\r\n'.join(lines) + '\r\n'
