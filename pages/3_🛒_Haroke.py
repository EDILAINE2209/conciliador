import json
import os
import tempfile

import streamlit as st

from core.auth import require_password
from core.haroke.cadastro import load_overrides, save_overrides, CONTA_PADRAO
from core.haroke.generate import processar, gerar_txt, NOMES_REGRA

st.set_page_config(page_title="Haroke — Conciliação Bancária", page_icon="🛒", layout="wide")
require_password()

CNPJ_PADRAO = "17041531000125"

st.title("🛒 Haroke Supermercado LTDA — Conciliação Bancária")
st.caption(
    "Lê os 2 extratos bancários (Banco do Brasil e Sicoob), o relatório de "
    "Contas a Pagar e o Plano de Contas, acha a conta de cada fornecedor por "
    "similaridade de nome, classifica cada lançamento automaticamente e gera "
    "o arquivo de importação contábil do mês."
)


def init_state():
    defaults = {
        "haroke_overrides": load_overrides(),
        "haroke_result": None,
        "haroke_cnpj": CNPJ_PADRAO,
        "haroke_ano_mes": "202607",
        "haroke_revisao": {},  # nome do fornecedor -> conta escolhida na revisão
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()
overrides = st.session_state["haroke_overrides"]

tab_gerar, tab_overrides = st.tabs(["Gerar arquivo do mês", "📇 Correções de fornecedor"])

# ==========================================================================
# ABA: CORREÇÕES DE FORNECEDOR
# ==========================================================================
with tab_overrides:
    st.subheader("Correções manuais de fornecedor → conta contábil")
    st.caption(
        "A conta de cada fornecedor é achada automaticamente comparando o nome "
        "do Contas a Pagar com o nome no Plano de Contas (similaridade de "
        "texto). Esta lista serve só para os casos em que essa comparação "
        "erra, ou em que o fornecedor ainda não tem conta própria no plano "
        f"(nesses casos cai em {CONTA_PADRAO}, Fornecedores Diversos)."
    )
    itens = sorted(overrides.items())
    for nome, conta in itens:
        c1, c2, c3 = st.columns([5, 1, 1])
        c1.text(nome)
        nova_conta = c2.text_input("Conta", value=str(conta), key=f"conta_ov_{nome}", label_visibility="collapsed")
        if nova_conta != str(conta):
            overrides[nome] = nova_conta
        if c3.button("Remover", key=f"rm_ov_{nome}"):
            del overrides[nome]
            st.rerun()

    st.markdown("**Adicionar correção manualmente**")
    nc1, nc2 = st.columns([5, 1])
    novo_nome = nc1.text_input("Nome do fornecedor (exatamente como aparece no Contas a Pagar)", key="novo_nome_ov")
    novo_conta = nc2.text_input("Conta", key="novo_conta_ov")
    if st.button("➕ Adicionar correção"):
        if novo_nome and novo_conta:
            overrides[novo_nome.strip()] = novo_conta.strip()
            st.rerun()
        else:
            st.warning("Preencha o nome e a conta.")

    if st.button("💾 Salvar correções", type="primary"):
        save_overrides(overrides)
        st.success("Correções salvas.")

    st.divider()
    st.caption(
        "⚠️ O botão acima só salva aqui dentro do app rodando agora. Se o app "
        "reiniciar (ele faz isso sozinho de tempos em tempos), essa gravação "
        "pode se perder. Pra deixar as mudanças permanentes, baixe o arquivo "
        "abaixo e suba no GitHub, substituindo o arquivo "
        "**haroke_overrides_seed.json** — assim as correções atualizadas "
        "viram o novo ponto de partida do app."
    )
    st.download_button(
        "⬇️ Baixar correções atualizadas (para subir no GitHub)",
        data=json.dumps(overrides, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"),
        file_name="haroke_overrides_seed.json",
        mime="application/json",
    )

# ==========================================================================
# ABA: GERAR ARQUIVO DO MÊS
# ==========================================================================
with tab_gerar:
    st.subheader("1. Arquivos do mês")
    st.session_state["haroke_cnpj"] = st.text_input("CNPJ", value=st.session_state["haroke_cnpj"])
    col_mes, _ = st.columns([1, 3])
    mes_ano_str = col_mes.text_input(
        "Mês/ano do período (AAAAMM)", value=st.session_state["haroke_ano_mes"],
        help="Transações fora desse mês são ignoradas — use o mesmo período dos extratos enviados.",
    )
    st.session_state["haroke_ano_mes"] = mes_ano_str

    c1, c2 = st.columns(2)
    ofx_bb = c1.file_uploader("Extrato Banco do Brasil (OFX)", type=["ofx"], key="ofx_bb_hrk")
    ofx_sicoob = c2.file_uploader("Extrato Sicoob (OFX)", type=["ofx"], key="ofx_sicoob_hrk")
    c3, c4 = st.columns(2)
    cap_file = c3.file_uploader("Contas a Pagar (Excel)", type=["xlsx"], key="cap_file_hrk")
    pdc_file = c4.file_uploader("Plano de Contas (Excel)", type=["xlsx"], key="pdc_file_hrk")

    processar_disabled = not (ofx_bb and ofx_sicoob and cap_file and pdc_file)
    if st.button("🔄 Processar", type="primary", disabled=processar_disabled):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = {}
            for nome, up in (("bb", ofx_bb), ("sicoob", ofx_sicoob), ("cap", cap_file), ("pdc", pdc_file)):
                ext = "ofx" if nome in ("bb", "sicoob") else "xlsx"
                p = os.path.join(tmpdir, f"{nome}.{ext}")
                with open(p, "wb") as f:
                    f.write(up.getbuffer())
                paths[nome] = p

            result = processar(paths["bb"], paths["sicoob"], paths["cap"], paths["pdc"], overrides, mes_ano_str)
            st.session_state["haroke_result"] = result
            st.session_state["haroke_revisao"] = {}

    result = st.session_state["haroke_result"]
    if result is None:
        st.info("Envie os 2 extratos OFX, o Contas a Pagar e o Plano de Contas do mês, e clique em Processar.")
        st.stop()

    st.subheader("2. Resumo por regra")
    resumo = result["resumo"]
    total_geral = sum(v[1] for v in resumo.values())
    total_lancamentos = sum(v[0] for v in resumo.values())
    mcol1, mcol2 = st.columns(2)
    mcol1.metric("Lançamentos classificados", total_lancamentos)
    mcol2.metric("Total movimentado", f"R$ {total_geral:,.2f}".replace(",", "§").replace(".", ",").replace("§", "."))

    for bucket, (cnt, total) in sorted(resumo.items(), key=lambda kv: -kv[1][1]):
        if cnt == 0:
            continue
        nome_regra = NOMES_REGRA.get(bucket, bucket)
        st.write(f"**{nome_regra}** — {cnt} lançamento(s), R$ {total:,.2f}".replace(",", "§").replace(".", ",").replace("§", "."))

    if result["unclassified"]:
        st.error(
            f"{len(result['unclassified'])} lançamento(s) do extrato não se encaixaram em nenhuma "
            "regra conhecida — é um tipo de movimento novo. Confira a lista abaixo antes de "
            "importar o arquivo; será preciso decidir a regra e avisar para ela ser incluída no app."
        )
        for u in result["unclassified"]:
            st.write(f"`{u['banco']}` {u['date']} R$ {u['amt']:.2f} — {u['memo']}")

    st.subheader("3. Fornecedores para revisar")
    baixa = result["baixa_confianca"]
    if baixa:
        st.warning(
            f"{len(baixa)} parcela(s) do Contas a Pagar tiveram a conta do fornecedor achada por "
            "similaridade de nome com confiança baixa (abaixo de 95%). Confira se a conta sugerida "
            "está certa ou informe a conta correta abaixo — isso já vira uma correção manual para os "
            "próximos meses."
        )
        vistos = set()
        for p in baixa:
            if p.nome in vistos:
                continue
            vistos.add(p.nome)
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.text(f"{p.nome}  (score {p.match_score:.2f} → sugestão: {p.conta_fornecedor} {p.conta_fornecedor_nome})")
            conta_atual = st.session_state["haroke_revisao"].get(p.nome, p.conta_fornecedor)
            nova_conta = c2.text_input("Conta", value=conta_atual, key=f"rev_hrk_{p.nome}", label_visibility="collapsed")
            st.session_state["haroke_revisao"][p.nome] = nova_conta
            if c3.button("Aplicar", key=f"apply_hrk_{p.nome}"):
                overrides[p.nome] = nova_conta
                save_overrides(overrides)
                st.success(f"Correção salva: {p.nome} → conta {nova_conta}. Reprocesse os arquivos para aplicar.")
    else:
        st.success("Todos os fornecedores encontrados tiveram alta confiança na conta sugerida.")

    st.subheader("4. Baixar arquivo")
    cnpj = st.session_state["haroke_cnpj"]
    txt_conciliacao = gerar_txt(result["entries"], cnpj)
    nome_arquivo = st.text_input(
        "Nome do arquivo", value=f"Conciliacao_Haroke_{mes_ano_str[4:6]}{mes_ano_str[0:4]}.txt",
    )
    st.download_button(
        "⬇️ Baixar conciliação bancária", data=txt_conciliacao.encode("utf-8"),
        file_name=nome_arquivo, mime="text/plain", type="primary",
    )
