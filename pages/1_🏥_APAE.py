import os
import re
import tempfile

import streamlit as st

from core.auth import require_password
from core.pdf_extract import extract_from_pdf
from core.matching import build_report_entries, match
from core.ofx_parse import parse_ofx_file
from core.txt_generator import generate_txt, write_txt
from core.config import load_config, save_config, get_or_create_empresa

st.set_page_config(page_title="APAE — Conciliação de Doações", page_icon="🏥", layout="wide")
require_password()

NOME_EMPRESA = "APAE São Sebastião do Paraiso"


def init_state():
    defaults = {
        "config": load_config(),
        "extraction": None,
        "report_entries": None,
        "matched": None,
        "unmatched_pix": None,
        "ambiguous": None,
        "ambiguous_choice": {},
        "pix_classification": {},
        "year": "2026",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()
cfg = st.session_state["config"]
empresa = get_or_create_empresa(cfg, NOME_EMPRESA, cnpj_padrao="19098326000121")

st.title("🏥 APAE São Sebastião do Paraiso — Conciliação de Doações")

tab_gerar, tab_config = st.tabs(["Gerar TXT", "⚙️ Configurações"])

# ==========================================================================
# ABA: CONFIGURAÇÕES
# ==========================================================================
with tab_config:
    st.subheader("Dados gerais")
    empresa["cnpj"] = st.text_input("CNPJ (cabeçalho do arquivo)", value=empresa["cnpj"])

    st.subheader("Contas contábeis")
    c1, c2, c3, c4 = st.columns(4)
    empresa["contas"]["doacao_pf"] = c1.text_input("Doação Pessoa Física", value=empresa["contas"]["doacao_pf"])
    empresa["contas"]["doacao_pj"] = c2.text_input("Doação Pessoa Jurídica", value=empresa["contas"]["doacao_pj"])
    empresa["contas"]["suspensa"] = c3.text_input("Suspensa (não confirmado no banco)", value=empresa["contas"]["suspensa"])
    empresa["contas"]["banco"] = c4.text_input("Conta banco (confirmado)", value=empresa["contas"]["banco"])

    empresa["historico_doacao"] = st.text_input("Histórico padrão de doação", value=empresa["historico_doacao"])
    empresa["tolerancia_valor"] = st.number_input(
        "Tolerância de valor no casamento banco x relatório (R$)",
        value=float(empresa.get("tolerancia_valor", 0.005)), step=0.001, format="%.3f",
    )

    st.subheader("Regras especiais reutilizáveis")
    st.caption(
        "Use isso para classificar PIX do banco que não são doações do relatório "
        "mas têm um lançamento contábil conhecido — por exemplo, venda de ingressos "
        "de um evento (feijoada), sempre lançados numa conta/histórico específicos."
    )

    for i, regra in enumerate(empresa["regras_especiais"]):
        with st.expander(f"📌 {regra['nome']}", expanded=False):
            rc1, rc2, rc3 = st.columns(3)
            regra["nome"] = rc1.text_input("Nome da regra", value=regra["nome"], key=f"regra_nome_{i}")
            regra["conta_credito"] = rc2.text_input("Conta crédito", value=regra["conta_credito"], key=f"regra_conta_{i}")
            regra["historico"] = rc3.text_input("Histórico", value=regra["historico"], key=f"regra_hist_{i}")
            regra["descricao"] = st.text_area("Descrição", value=regra.get("descricao", ""), key=f"regra_desc_{i}")
            if st.button("🗑️ Remover regra", key=f"del_regra_{i}"):
                empresa["regras_especiais"].pop(i)
                st.rerun()

    st.markdown("**Adicionar nova regra**")
    nc1, nc2, nc3 = st.columns(3)
    novo_nome = nc1.text_input("Nome", key="novo_regra_nome")
    novo_conta = nc2.text_input("Conta crédito", key="novo_regra_conta")
    novo_hist = nc3.text_input("Histórico", key="novo_regra_hist")
    novo_desc = st.text_area("Descrição", key="novo_regra_desc")
    if st.button("➕ Adicionar regra", key="btn_add_regra"):
        if novo_nome and novo_conta and novo_hist:
            empresa["regras_especiais"].append({
                "nome": novo_nome, "conta_credito": novo_conta,
                "historico": novo_hist, "descricao": novo_desc,
            })
            st.rerun()
        else:
            st.warning("Preencha nome, conta crédito e histórico.")

    if st.button("💾 Salvar configurações", type="primary"):
        save_config(cfg)
        st.session_state["config"] = cfg
        st.success("Configurações salvas.")

# ==========================================================================
# ABA: GERAR TXT
# ==========================================================================
with tab_gerar:
    st.caption(f"CNPJ {empresa['cnpj'] or '— não cadastrado —'}")
    st.subheader("1. Arquivos do mês")
    col1, col2, col3 = st.columns([2, 2, 1])
    pdf_file = col1.file_uploader("Relatório de Faturamento (PDF)", type=["pdf"])
    ofx_file = col2.file_uploader("Extrato bancário (OFX) — opcional", type=["ofx"])
    st.session_state["year"] = col3.text_input("Ano", value=st.session_state["year"])

    if st.button("🔄 Processar arquivos", type="primary", disabled=(pdf_file is None)):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "relatorio.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_file.getbuffer())
            extraction = extract_from_pdf(pdf_path)

            entries = build_report_entries(extraction.records)

            matched, unmatched_pix, ambiguous = [], [], []
            if ofx_file is not None:
                ofx_path = os.path.join(tmpdir, "extrato.ofx")
                with open(ofx_path, "wb") as f:
                    f.write(ofx_file.getbuffer())
                pix_list = parse_ofx_file(ofx_path, st.session_state["year"])
                matched, unmatched_pix, ambiguous = match(
                    entries, pix_list, tolerance=empresa.get("tolerancia_valor", 0.005)
                )

            st.session_state["extraction"] = extraction
            st.session_state["report_entries"] = entries
            st.session_state["matched"] = matched
            st.session_state["unmatched_pix"] = unmatched_pix
            st.session_state["ambiguous"] = ambiguous
            st.session_state["ambiguous_choice"] = {}
            st.session_state["pix_classification"] = {}

    extraction = st.session_state["extraction"]
    if extraction is None:
        st.info("Envie o PDF do relatório de doações (e opcionalmente o OFX do banco) e clique em Processar.")
        st.stop()

    entries = st.session_state["report_entries"]
    unmatched_pix = st.session_state["unmatched_pix"]
    ambiguous = st.session_state["ambiguous"]

    st.subheader("2. Conferência da extração")
    t = extraction.totals
    mcol1, mcol2, mcol3 = st.columns(3)
    mcol1.metric("Recibos extraídos", len(extraction.records))
    mcol2.metric("Total Geral (relatório)", t.get("geral_count", "?"))
    mcol3.metric("Total Recebido (relatório)", f"R$ {t.get('geral_total', 0):.2f}" if t.get("geral_total") else "?")

    if extraction.warnings:
        for w in extraction.warnings:
            st.error(w)
    else:
        st.success("Contagem e soma extraídas batem com os totais impressos no relatório.")

    if ambiguous:
        st.subheader("3. Casos ambíguos (nome + valor batem com mais de um doador)")
        st.caption("Escolha a qual doador do relatório cada PIX corresponde, ou deixe pendente.")
        for pix, candidates in ambiguous:
            key = f"amb_{pix.fitid}"
            options = ["— deixar pendente —"] + [
                f"{c.raw} (data relatório {c.date})" for c in candidates
            ]
            choice = st.selectbox(
                f"PIX {pix.real_date} R$ {pix.amt:.2f} — \"{pix.name_raw}\"",
                options, key=key,
            )
            if choice == options[0]:
                st.session_state["ambiguous_choice"][pix.fitid] = None
            else:
                idx = options.index(choice) - 1
                st.session_state["ambiguous_choice"][pix.fitid] = candidates[idx]

    resolved_extra_unmatched = []
    for pix, candidates in (ambiguous or []):
        choice = st.session_state["ambiguous_choice"].get(pix.fitid)
        for c in candidates:
            c.matched_pix = None
        if choice is not None:
            choice.matched_pix = pix
        else:
            resolved_extra_unmatched.append(pix)

    all_unmatched = list(unmatched_pix or []) + resolved_extra_unmatched

    if all_unmatched:
        st.subheader("4. PIX do banco sem correspondência no relatório")
        st.caption(
            "Ordenados do maior para o menor valor. Classifique cada um: deixe como "
            "\"pendente\" (padrão: debita banco / credita conta suspensa) ou associe a "
            "uma regra especial (ex.: ingressos de evento)."
        )
        regra_nomes = ["— pendente (padrão) —"] + [r["nome"] for r in empresa["regras_especiais"]]
        for pix in sorted(all_unmatched, key=lambda p: -p.amt):
            key = f"cls_{pix.fitid}"
            choice = st.selectbox(
                f"{pix.real_date}  R$ {pix.amt:.2f}  —  \"{pix.name_raw}\"  ({pix.memo[:60]}…)",
                regra_nomes, key=key,
            )
            st.session_state["pix_classification"][pix.fitid] = (
                None if choice == regra_nomes[0] else choice
            )

    st.subheader("5. Gerar arquivo final")
    out_lines, resumo = generate_txt(
        entries, all_unmatched, st.session_state["pix_classification"], empresa, st.session_state["year"]
    )

    rcol1, rcol2, rcol3 = st.columns(3)
    rcol1.metric("Total doações (289+765)", f"R$ {resumo['total_doacoes']:.2f}")
    rcol2.metric("Confirmados no banco", resumo["count_confirmado"])
    rcol3.metric("Pendentes (aguardando confirmação)", resumo["count_pendente"])

    if t.get("geral_total") is not None:
        diff = abs(resumo["total_doacoes"] - t["geral_total"])
        if diff <= 0.01:
            st.success(f"✅ Total de doações bate exatamente com o relatório (R$ {t['geral_total']:.2f}).")
        else:
            st.error(
                f"⚠️ Total de doações (R$ {resumo['total_doacoes']:.2f}) difere do relatório "
                f"(R$ {t['geral_total']:.2f}) — diferença de R$ {diff:.2f}."
            )

    if resumo["count_banco_pendente"]:
        st.warning(
            f"{resumo['count_banco_pendente']} PIX do banco ainda sem classificação "
            f"(pendentes), totalizando R$ {resumo['total_banco_pendente']:.2f}."
        )
    for nome, cnt in resumo["count_especial"].items():
        st.info(f"Regra \"{nome}\": {cnt} lançamento(s), total R$ {resumo['total_especial'][nome]:.2f}.")

    mes = st.session_state["year"]
    default_name = f"Apaesspa_DOACOES_{mes}.txt"
    filename = st.text_input("Nome do arquivo de saída", value=default_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, filename)
        write_txt(out_lines, out_path)
        with open(out_path, "rb") as f:
            st.download_button(
                "⬇️ Baixar arquivo .txt", data=f.read(), file_name=filename,
                mime="text/plain", type="primary",
            )
