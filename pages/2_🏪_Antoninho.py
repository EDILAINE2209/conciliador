import json
import os
import tempfile

import streamlit as st

from core.auth import require_password
from core.antoninho.cadastro import load_cadastro, save_cadastro, registrar_fornecedor, CONTA_PADRAO
from core.antoninho.generate import processar, gerar_txt_conciliacao, gerar_txt_pendencias, NOMES_REGRA
from core.antoninho.plano_de_contas import load_fornecedores, load_clientes
from core.antoninho.matching import best_account

st.set_page_config(page_title="Antoninho — Conciliação Bancária", page_icon="🏪", layout="wide")
require_password()

CNPJ_PADRAO = "00894231000196"

st.title("🏪 Antoninho Atacado e Varejo — Conciliação Bancária")
st.caption(
    "Lê os 3 extratos bancários (Sicoob, Itaú e Banco do Brasil) e o relatório "
    "de Contas a Pagar, classifica cada lançamento automaticamente e gera os "
    "dois arquivos de importação contábil do mês."
)


def init_state():
    defaults = {
        "antoninho_cadastro": load_cadastro(),
        "antoninho_result": None,
        "antoninho_cnpj": CNPJ_PADRAO,
        "antoninho_ano_mes": "202607",
        "antoninho_revisao": {},   # complemento -> conta escolhida na revisão
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()
cadastro = st.session_state["antoninho_cadastro"]

tab_gerar, tab_cadastro = st.tabs(["Gerar arquivos do mês", "📇 Cadastro de fornecedores"])

# ==========================================================================
# ABA: CADASTRO DE FORNECEDORES
# ==========================================================================
with tab_cadastro:
    st.subheader("Fornecedores com conta contábil própria")
    st.caption(
        f"Fornecedores fora desta lista caem na conta {CONTA_PADRAO} (Fornecedores "
        "Diversos) e aparecem sinalizados para revisão manual na aba ao lado. "
        "Esse cadastro foi reconstruído a partir dos arquivos de julho/2026 e vai "
        "crescendo conforme fornecedores novos aparecem nos meses seguintes."
    )
    busca = st.text_input("🔎 Buscar por nome ou ID", key="busca_cadastro")
    itens = sorted(cadastro.items(), key=lambda kv: kv[1]["nome"])
    if busca:
        b = busca.upper()
        itens = [(fid, v) for fid, v in itens if b in v["nome"].upper() or b in fid]
    st.caption(f"{len(itens)} de {len(cadastro)} fornecedores")

    for fid, v in itens[:200]:
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.text(fid)
        c2.text(v["nome"])
        nova_conta = c3.text_input("Conta", value=v["conta"], key=f"conta_{fid}", label_visibility="collapsed")
        if nova_conta != v["conta"]:
            cadastro[fid]["conta"] = nova_conta

    st.markdown("**Adicionar fornecedor manualmente**")
    nc1, nc2, nc3 = st.columns([1, 3, 1])
    novo_fid = nc1.text_input("ID (número do fornecedor)", key="novo_fid")
    novo_nome_forn = nc2.text_input("Nome", key="novo_nome_forn")
    novo_conta_forn = nc3.text_input("Conta", key="novo_conta_forn")
    if st.button("➕ Adicionar ao cadastro"):
        if novo_fid and novo_conta_forn:
            registrar_fornecedor(cadastro, novo_fid.strip(), novo_nome_forn.strip(), novo_conta_forn.strip())
            st.rerun()
        else:
            st.warning("Preencha ao menos o ID e a conta.")

    if st.button("💾 Salvar cadastro", type="primary"):
        save_cadastro(cadastro)
        st.success("Cadastro salvo.")

    st.divider()
    st.caption(
        "⚠️ O botão acima só salva aqui dentro do app rodando agora. Se o app "
        "reiniciar (ele faz isso sozinho de tempos em tempos), essa gravação "
        "pode se perder. Pra deixar as mudanças permanentes, baixe o arquivo "
        "abaixo e suba no GitHub, substituindo o arquivo "
        "**antoninho_fornecedores_seed.json** — assim o cadastro atualizado "
        "vira o novo ponto de partida do app."
    )
    st.download_button(
        "⬇️ Baixar cadastro atualizado (para subir no GitHub)",
        data=json.dumps(cadastro, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"),
        file_name="antoninho_fornecedores_seed.json",
        mime="application/json",
    )

# ==========================================================================
# ABA: GERAR ARQUIVOS DO MÊS
# ==========================================================================
with tab_gerar:
    st.subheader("1. Arquivos do mês")
    st.session_state["antoninho_cnpj"] = st.text_input("CNPJ", value=st.session_state["antoninho_cnpj"])
    col_mes, _ = st.columns([1, 3])
    mes_ano_str = col_mes.text_input(
        "Mês/ano do período (AAAAMM)", value=st.session_state["antoninho_ano_mes"],
        help="Transações fora desse mês são ignoradas — use o mesmo período dos extratos enviados.",
    )
    st.session_state["antoninho_ano_mes"] = mes_ano_str

    c1, c2, c3 = st.columns(3)
    ofx_sicoob = c1.file_uploader("Extrato Sicoob (OFX)", type=["ofx"], key="ofx_sicoob")
    ofx_itau = c2.file_uploader("Extrato Itaú (OFX)", type=["ofx"], key="ofx_itau")
    ofx_bb = c3.file_uploader("Extrato Banco do Brasil (OFX)", type=["ofx"], key="ofx_bb")
    cap_file = st.file_uploader("Contas a Pagar por Entrada (Excel)", type=["xlsx"], key="cap_file")
    pdc_file = st.file_uploader(
        "Plano de Contas (Excel) — opcional, mas recomendado", type=["xlsx"], key="pdc_file_atn",
        help="Não é obrigatório para processar o mês. Se enviado, o app usa: (1) a lista de "
             "fornecedores do Plano de Contas para SUGERIR uma conta (por similaridade de "
             "nome) para os fornecedores que aparecerem fora do cadastro, na seção "
             "\"Fornecedores para revisar\" abaixo — a conta ainda precisa ser conferida e "
             "aplicada manualmente, igual já acontece hoje; e (2) a lista de clientes (grupo "
             "1.1.2.01) para identificar automaticamente a conta do cliente nas transferências "
             "recebidas do Banco do Brasil (regra 13) — sem o Plano de Contas, essas caem na "
             "conta genérica 504 (Clientes Diversos).",
    )

    processar_disabled = not (ofx_sicoob and ofx_itau and ofx_bb and cap_file)
    if st.button("🔄 Processar", type="primary", disabled=processar_disabled):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = {}
            for banco, up in (("551", ofx_sicoob), ("552", ofx_itau), ("8", ofx_bb)):
                p = os.path.join(tmpdir, f"{banco}.ofx")
                with open(p, "wb") as f:
                    f.write(up.getbuffer())
                paths[banco] = p
            cap_path = os.path.join(tmpdir, "contas_a_pagar.xlsx")
            with open(cap_path, "wb") as f:
                f.write(cap_file.getbuffer())

            accounts_clientes = None
            if pdc_file is not None:
                try:
                    accounts_clientes = load_clientes(pdc_file)
                except Exception as e:
                    st.error(f"Não consegui ler o grupo de clientes do Plano de Contas enviado: {e}")

            result = processar(paths, cap_path, cadastro, mes_ano_str, accounts_clientes=accounts_clientes)
            st.session_state["antoninho_result"] = result
            st.session_state["antoninho_revisao"] = {}

    result = st.session_state["antoninho_result"]
    if result is None:
        st.info("Envie os 3 extratos OFX e o Contas a Pagar do mês, e clique em Processar.")
        st.stop()

    st.subheader("2. Resumo por regra")
    resumo = result["resumo"]
    total_geral = sum(v[1] for v in resumo.values())
    mcol1, mcol2 = st.columns(2)
    mcol1.metric("Lançamentos classificados", len(result["lancamentos"]))
    mcol2.metric("Total movimentado", f"R$ {total_geral:,.2f}".replace(",", "§").replace(".", ",").replace("§", "."))

    for hist, (cnt, total) in sorted(resumo.items(), key=lambda kv: -kv[1][1]):
        nome_regra = NOMES_REGRA.get(hist, f"Histórico {hist}")
        st.write(f"**{nome_regra}** — {cnt} lançamento(s), R$ {total:,.2f}".replace(",", "§").replace(".", ",").replace("§", "."))

    st.subheader("3. Fornecedores para revisar")
    novos = result["novos_fornecedores"]

    accounts = None
    if pdc_file is not None:
        try:
            accounts = load_fornecedores(pdc_file)
        except Exception as e:
            st.error(f"Não consegui ler o Plano de Contas enviado: {e}")

    if novos:
        aviso = (
            f"{len(novos)} fornecedor(es) não encontrados no cadastro caíram na conta "
            f"{CONTA_PADRAO} (Fornecedores Diversos) por padrão. Confira se está certo "
            "ou informe a conta correta abaixo — isso já atualiza o cadastro para os "
            "próximos meses."
        )
        if accounts is not None:
            aviso += (
                " Como você enviou o Plano de Contas, o campo já vem preenchido com a "
                "sugestão encontrada por similaridade de nome — confira antes de aplicar, "
                "principalmente as de confiança mais baixa."
            )
        st.warning(aviso)
        for complemento, cnt in sorted(novos.items(), key=lambda kv: -kv[1]):
            nome_busca = complemento.split(' - ', 1)[-1].strip()
            sugestao_txt = ""
            sugestao_default = CONTA_PADRAO
            if accounts:
                sug_conta, sug_nome, sug_score = best_account(nome_busca, accounts)
                if sug_conta:
                    sugestao_default = sug_conta
                    sugestao_txt = f"  → sugestão: {sug_conta} {sug_nome} (score {sug_score:.2f})"
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.text(f"{complemento}  ({cnt}x){sugestao_txt}")
            conta_atual = st.session_state["antoninho_revisao"].get(complemento, sugestao_default)
            nova_conta = c2.text_input("Conta", value=conta_atual, key=f"rev_{complemento}", label_visibility="collapsed")
            st.session_state["antoninho_revisao"][complemento] = nova_conta
            if c3.button("Aplicar", key=f"apply_{complemento}"):
                fid = complemento.split(' - ', 1)[0].strip()
                nome = complemento.split(' - ', 1)[-1].strip()
                if fid.isdigit():
                    registrar_fornecedor(cadastro, fid, nome, nova_conta)
                    save_cadastro(cadastro)
                    st.success(f"Cadastrado: {complemento} → conta {nova_conta}. Reprocesse os arquivos para aplicar.")
                else:
                    st.error("Não foi possível identificar o ID numérico do fornecedor neste item — ajuste manualmente no txt gerado.")
    else:
        st.success("Todos os fornecedores encontrados já têm conta cadastrada.")

    st.subheader("4. Baixar arquivos")
    cnpj = st.session_state["antoninho_cnpj"]
    txt_conciliacao = gerar_txt_conciliacao(result["lancamentos"], cnpj)
    txt_pendencias = gerar_txt_pendencias(result["pendencias"], cnpj)

    dcol1, dcol2 = st.columns(2)
    nome_conc = dcol1.text_input("Nome do arquivo (conciliação bancária)", value=f"Conciliacao_Bancaria_Antoninho_{mes_ano_str[4:6]}{mes_ano_str[0:4]}.txt")
    dcol1.download_button(
        "⬇️ Baixar conciliação bancária", data=txt_conciliacao.encode("utf-8"),
        file_name=nome_conc, mime="text/plain", type="primary",
    )
    nome_pend = dcol2.text_input("Nome do arquivo (pendências)", value=f"Pendencias_Contas_a_Pagar_Antoninho_{mes_ano_str[4:6]}{mes_ano_str[0:4]}.txt")
    dcol2.download_button(
        "⬇️ Baixar pendências do Contas a Pagar", data=txt_pendencias.encode("utf-8"),
        file_name=nome_pend, mime="text/plain", type="primary",
    )

    st.caption(
        f"{len(result['pendencias'])} parcela(s) do Contas a Pagar com vencimento no "
        "período não foram encontradas em nenhum dos 3 extratos e ficaram como pendência."
    )
