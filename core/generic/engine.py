"""
Motor genérico para empresas criadas via self-service ("Nova Empresa"),
reaproveitando — sem alterar — a lógica já validada da Antoninho e da
Haroke. A ideia: rodar exatamente a mesma classificação (mesmos padrões de
memo, mesma forma de casar fornecedor), e só no final trocar os números de
conta genéricos do modelo pelos números que a empresa nova de verdade usa.

Isso mantém o motor "validado" intacto (core/antoninho/classify.py e
core/haroke/classify.py não são tocados por este arquivo) e concentra o
código novo — e o risco de bug novo — numa camada fina de remapeamento.
"""
import json
import os

from core.antoninho.ofx_parse import parse_ofx_file
from core.antoninho.payables import parse_payables_excel
from core.antoninho.cadastro import save_cadastro, CONTA_PADRAO as ANTONINHO_CONTA_PADRAO
from core.antoninho.classify import PayableMatcher, classify_txn, strip_accents
from core.antoninho.generate import gerar_txt_conciliacao, gerar_txt_pendencias

from core.haroke.cadastro import save_overrides, CONTA_PADRAO as HAROKE_CONTA_PADRAO
from core.haroke.classify import preparar_fornecedores, classify_all, BUCKETS
from core.haroke.generate import gerar_txt as gerar_txt_haroke
from core.common.plano_de_contas import load_fornecedores

from core.generic.empresas import cadastro_path, overrides_path


def _load_json_or_empty(path: str) -> dict:
    """Como core.antoninho.cadastro.load_cadastro / core.haroke.cadastro.
    load_overrides, mas SEM cair pra semente da Antoninho/Haroke se o
    arquivo não existir — cada empresa self-service começa mesmo vazia
    (o seed dessas duas funções é hardcoded pra Antoninho/Haroke de
    verdade, não faz sentido pra uma empresa nova)."""
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}

BANCOS_ANTONINHO = {"551", "552", "8"}
BANCOS_HAROKE = {"8", "551"}

_ANTONINHO_HIST_MAP = {
    '314': 'pix_recebido', '371': 'cartao', '233': 'tarifas', '252': 'iof',
    '255': 'juros', '204': 'rendefacil', '318': 'rendefacil', '370': 'demais',
}

_HAROKE_BUCKET_MAP = {
    'L_demais': 'demais', 'C_pix_recebidos': 'pix_recebidos',
    'D_cred_liq_cobranca': 'cred_liq_cobranca', 'E_sipag_cielo': 'sipag_cielo',
    'F_tarifas': 'tarifas', 'H_rendefacil_entra': 'rendefacil',
    'I_rendefacil_sai': 'rendefacil', 'J_iof': 'iof', 'M_juros': 'juros',
    # K_antoninho é uma regra específica da Haroke (PIX pra outra empresa da
    # carteira) — não remapeada aqui; na prática nunca deve disparar pra uma
    # empresa nova, já que depende do nome literal "ANTONINHO" no memo/nome.
}


def _remap_conta(l, contas, banco_set):
    """Troca o lado que NÃO é o banco pela conta configurada, se a
    categoria tiver conta definida."""
    if l.debito not in banco_set:
        l.debito = contas
    else:
        l.credito = contas


def _remap_antoninho(lancamentos, pendencias, contas):
    for l in lancamentos:
        if l.historico == '429':
            nova = contas.get('fornecedor_fallback')
            if not nova:
                continue
            if l.debito == ANTONINHO_CONTA_PADRAO and l.debito not in BANCOS_ANTONINHO:
                l.debito = nova
            elif l.credito == ANTONINHO_CONTA_PADRAO and l.credito not in BANCOS_ANTONINHO:
                l.credito = nova
            continue
        chave = _ANTONINHO_HIST_MAP.get(l.historico)
        nova = contas.get(chave) if chave else None
        if nova:
            _remap_conta(l, nova, BANCOS_ANTONINHO)

    nova_fallback = contas.get('fornecedor_fallback')
    if nova_fallback:
        for p in pendencias:
            if p['debito'] == ANTONINHO_CONTA_PADRAO and p['debito'] != '5':
                p['debito'] = nova_fallback
            elif p['credito'] == ANTONINHO_CONTA_PADRAO and p['credito'] != '5':
                p['credito'] = nova_fallback


def _remap_haroke(entries, contas):
    nova_fallback = contas.get('fornecedor_fallback')
    for bucket, itens in entries.items():
        if bucket in ('A_conciliados', 'B_nao_conciliados'):
            if not nova_fallback:
                continue
            for l in itens:
                if l.debito == HAROKE_CONTA_PADRAO and l.debito not in BANCOS_HAROKE and l.debito != '5':
                    l.debito = nova_fallback
                elif l.credito == HAROKE_CONTA_PADRAO and l.credito not in BANCOS_HAROKE and l.credito != '5':
                    l.credito = nova_fallback
            continue
        chave = _HAROKE_BUCKET_MAP.get(bucket)
        nova = contas.get(chave) if chave else None
        if nova:
            for l in itens:
                _remap_conta(l, nova, BANCOS_HAROKE)


def processar_antoninho_generico(empresa: dict, arquivos: dict, ano_mes: str):
    """arquivos: {"551": path|None, "552": path|None, "8": path|None,
    "cap": path, "pdc": path|None}. Devolve o mesmo formato que
    core.antoninho.generate.processar (lancamentos/pendencias/resumo/
    novos_fornecedores), já com as contas remapeadas pra empresa."""
    slug = empresa["slug"]
    cadastro = _load_json_or_empty(cadastro_path(slug))

    payables = parse_payables_excel(arquivos["cap"])
    matcher = PayableMatcher(payables)

    txns = []
    for banco in BANCOS_ANTONINHO:
        p = arquivos.get(banco)
        if p:
            txns.extend(parse_ofx_file(p, banco))

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
    from core.antoninho.cadastro import get_conta
    for p in payables:
        if p.usado or p.vencimento[:6] != ano_mes:
            continue
        conta, achou = get_conta(cadastro, p.fid, p.nome)
        data = f"{p.vencimento[6:8]}/{p.vencimento[4:6]}/{p.vencimento[0:4]}"
        complemento = strip_accents(f"{p.fid} - {p.nome}")
        if achou:
            pendencias.append(dict(date=data, debito=conta, credito='5', valor=p.valor, complemento=complemento))
        else:
            pendencias.append(dict(date=data, debito='5', credito=conta, valor=p.valor, complemento=complemento))
            novos_fornecedores[complemento] = novos_fornecedores.get(complemento, 0) + 1

    # sugestão por nome (Plano de Contas), se enviado — mesma ideia da
    # Antoninho de verdade, só que aqui o cadastro começa vazio
    sugestoes = {}
    if arquivos.get("pdc"):
        from core.antoninho.matching import best_account
        accounts = load_fornecedores(arquivos["pdc"])
        for complemento in novos_fornecedores:
            nome_busca = complemento.split(' - ', 1)[-1].strip()
            conta, nome_conta, score = best_account(nome_busca, accounts)
            if conta:
                sugestoes[complemento] = (conta, nome_conta, score)

    _remap_antoninho(lancamentos, pendencias, empresa["contas"])

    from collections import defaultdict
    resumo = defaultdict(lambda: [0, 0.0])
    for l in lancamentos:
        resumo[l.historico][0] += 1
        resumo[l.historico][1] += l.valor

    return dict(lancamentos=lancamentos, pendencias=pendencias, resumo=dict(resumo),
                novos_fornecedores=novos_fornecedores, sugestoes=sugestoes, cadastro=cadastro)


def processar_haroke_generico(empresa: dict, arquivos: dict, ano_mes: str):
    """arquivos: {"8": path|None, "551": path|None, "cap": path, "pdc": path}."""
    slug = empresa["slug"]
    overrides = _load_json_or_empty(overrides_path(slug))

    payables = parse_payables_excel(arquivos["cap"])
    accounts = load_fornecedores(arquivos["pdc"]) if arquivos.get("pdc") else []
    baixa_confianca = preparar_fornecedores(payables, accounts, overrides)

    bb_txns = parse_ofx_file(arquivos["8"], '8') if arquivos.get("8") else []
    sicoob_txns = parse_ofx_file(arquivos["551"], '551') if arquivos.get("551") else []

    entries, unclassified = classify_all(bb_txns, sicoob_txns, payables, ano_mes)
    _remap_haroke(entries, empresa["contas"])

    resumo = {}
    for bucket in BUCKETS:
        itens = entries[bucket]
        resumo[bucket] = (len(itens), sum(abs(l.valor) for l in itens))

    return dict(entries=entries, unclassified=unclassified, baixa_confianca=baixa_confianca,
                resumo=resumo, overrides=overrides)


def processar_empresa(empresa: dict, arquivos: dict, ano_mes: str):
    if empresa["modelo"] == "antoninho":
        return processar_antoninho_generico(empresa, arquivos, ano_mes)
    return processar_haroke_generico(empresa, arquivos, ano_mes)


def gerar_txt(empresa: dict, resultado: dict, cnpj: str):
    """Devolve um dict {nome_do_arquivo_sugerido: conteudo} — a Antoninho
    gera 2 arquivos, a Haroke gera 1."""
    if empresa["modelo"] == "antoninho":
        return {
            "conciliacao": gerar_txt_conciliacao(resultado["lancamentos"], cnpj),
            "pendencias": gerar_txt_pendencias(resultado["pendencias"], cnpj),
        }
    return {"conciliacao": gerar_txt_haroke(resultado["entries"], cnpj)}
