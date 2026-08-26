import os
import tempfile

import streamlit as st

from core.auth import require_password
from core.common.templates import TEMPLATES, BANCOS_NOMES
from core.generic.empresas import load_empresas, update_empresa, cadastro_path, overrides_path
from core.generic.engine import processar_empresa, gerar_txt
from core.antoninho.cadastro import save_cadastro, registrar_fornecedor
from core.antoninho.generate import NOMES_REGRA as NOMES_REGRA_ANTONINHO
from core.haroke.cadastro import save_overrides
from core.haroke.classify import NOMES_REGRA as NOMES_REGRA_HAROKE

st.set_page_config(page_title="Empresas (self-service) — Conciliação", page_icon="🏢", layout="wide")
require_password()

st.title("🏢 Empresas criadas na hora")
st.caption(
    "Empresas criadas pela tela \"Nova Empresa\", prontas pra gerar arquivo — sem "
    "precisar de mim nem de um novo deploy no GitHub."
)

empresas = load_empresas()
if not empresas:
    st.info(
        "Nenhuma empresa foi criada por aqui ainda. Vá em **🏗️ Nova Empresa** para criar a "
        "primeira (escolha \"Criar empresa agora\" no final do formulário)."
    )
    st.stop()

nomes_empresas = {f"{e['nome']} ({TEMPLATES[e['modelo']]['nome']})": e["slug"] for e in empresas}
escolha = st.selectbox("Empresa", options=list(nomes_empresas.keys()))
slug = nomes_empresas[escolha]
empresa = next(e for e in empresas if e["slug"] == slug)
modelo = TEMPLATES[empresa["modelo"]]

if empresa.get("verificado"):
    st.success(
        "✅ Verificada — alguém já conferiu um mês fechado de verdade dessa empresa contra "
        "o arquivo gerado aqui e bateu certinho."
    )
else:
    st.warning(
        "⚠️ **Empresa ainda não verificada.** Ela foi criada agora mesmo pelo formulário — "
        "ninguém conferiu ainda se o arquivo gerado bate com um fechamento real. Revise os "
        "primeiros meses com atenção redobrada, principalmente a seção \"Fornecedores para "
        "revisar\" (o cadastro dessa empresa começa vazio, então tudo cai lá no primeiro mês). "
        "Quando tiver certeza de que um mês bateu, marque como verificada no final desta "
        "página."
    )

st.caption(modelo["descricao"])

if "empresas_state" not in st.session_state:
    st.session_state["empresas_state"] = {}
state = st.session_state["empresas_state"].setdefault(slug, {"result": None, "revisao": {}})

st.subheader("1. Arquivos do mês")
c1, c2 = st.columns(2)
cnpj = c1.text_input("CNPJ", value=empresa.get("cnpj", ""), key=f"cnpj_{slug}")
ano_mes = c2.text_input("Mês/ano do período (AAAAMM)", value="", key=f"anomes_{slug}",
                         help="Transações fora desse mês são ignoradas.")

arquivos = {}
cols = st.columns(len(empresa["bancos"]))
for banco, col in zip(empresa["bancos"], cols):
    up = col.file_uploader(f"Extrato {BANCOS_NOMES.get(banco, banco)} (OFX)", type=["ofx"], key=f"ofx_{slug}_{banco}")
    arquivos[banco] = up

cap_file = st.file_uploader("Contas a Pagar (Excel)", type=["xlsx"], key=f"cap_{slug}")
pdc_obrigatorio = modelo["estrategia_fornecedor"] == "nome"
pdc_file = st.file_uploader(
    f"Plano de Contas (Excel){'' if pdc_obrigatorio else ' — opcional'}",
    type=["xlsx"], key=f"pdc_{slug}",
    help="Usado pra achar a conta de cada fornecedor por similaridade de nome."
    if pdc_obrigatorio else
    "Se enviado, sugere conta pra fornecedores fora do cadastro.",
)

bancos_ok = all(arquivos.values())
processar_disabled = not (bancos_ok and cap_file and ano_mes and (pdc_file or not pdc_obrigatorio))
if st.button("🔄 Processar", type="primary", disabled=processar_disabled):
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = {}
        for banco, up in arquivos.items():
            p = os.path.join(tmpdir, f"{banco}.ofx")
            with open(p, "wb") as f:
                f.write(up.getbuffer())
            paths[banco] = p
        cap_path = os.path.join(tmpdir, "cap.xlsx")
        with open(cap_path, "wb") as f:
            f.write(cap_file.getbuffer())
        paths["cap"] = cap_path
        if pdc_file:
            pdc_path = os.path.join(tmpdir, "pdc.xlsx")
            with open(pdc_path, "wb") as f:
                f.write(pdc_file.getbuffer())
            paths["pdc"] = pdc_path
        else:
            paths["pdc"] = None

        state["result"] = processar_empresa(empresa, paths, ano_mes)
        state["revisao"] = {}

result = state["result"]
if result is None:
    st.info("Envie os arquivos do mês e clique em Processar.")
    st.stop()

st.subheader("2. Resumo por regra")
nomes_regra = NOMES_REGRA_ANTONINHO if empresa["modelo"] == "antoninho" else NOMES_REGRA_HAROKE
total_geral = sum(v[1] for v in result["resumo"].values())
total_count = sum(v[0] for v in result["resumo"].values())
mcol1, mcol2 = st.columns(2)
mcol1.metric("Lançamentos classificados", total_count)
mcol2.metric("Total movimentado", f"R$ {total_geral:,.2f}".replace(",", "§").replace(".", ",").replace("§", "."))
for chave, (cnt, total) in sorted(result["resumo"].items(), key=lambda kv: -kv[1][1]):
    if cnt == 0:
        continue
    nome_regra = nomes_regra.get(chave, f"Categoria {chave}")
    st.write(f"**{nome_regra}** — {cnt} lançamento(s), R$ {total:,.2f}".replace(",", "§").replace(".", ",").replace("§", "."))

st.subheader("3. Fornecedores para revisar")
if empresa["modelo"] == "antoninho":
    novos = result["novos_fornecedores"]
    sugestoes = result.get("sugestoes", {})
    if novos:
        st.warning(
            f"{len(novos)} fornecedor(es) não encontrados no cadastro desta empresa caíram na "
            "conta configurada como \"fornecedor não cadastrado\". Confira e informe a conta "
            "certa — isso já cadastra o fornecedor pelo ID pros próximos meses."
        )
        for complemento, cnt in sorted(novos.items(), key=lambda kv: -kv[1]):
            sug_txt = ""
            default_conta = empresa["contas"].get("fornecedor_fallback", "")
            if complemento in sugestoes:
                sug_conta, sug_nome, sug_score = sugestoes[complemento]
                sug_txt = f"  → sugestão: {sug_conta} {sug_nome} (score {sug_score:.2f})"
                default_conta = sug_conta
            cc1, cc2, cc3 = st.columns([4, 1, 1])
            cc1.text(f"{complemento}  ({cnt}x){sug_txt}")
            atual = state["revisao"].get(complemento, default_conta)
            nova_conta = cc2.text_input("Conta", value=atual, key=f"rev_{slug}_{complemento}", label_visibility="collapsed")
            state["revisao"][complemento] = nova_conta
            if cc3.button("Aplicar", key=f"apply_{slug}_{complemento}"):
                fid = complemento.split(' - ', 1)[0].strip()
                nome = complemento.split(' - ', 1)[-1].strip()
                if fid.isdigit():
                    registrar_fornecedor(result["cadastro"], fid, nome, nova_conta)
                    save_cadastro(result["cadastro"], cadastro_path(slug))
                    st.success(f"Cadastrado: {complemento} → conta {nova_conta}. Reprocesse os arquivos para aplicar.")
                else:
                    st.error("Não foi possível identificar o ID numérico do fornecedor neste item.")
    else:
        st.success("Todos os fornecedores encontrados já têm conta cadastrada.")
else:
    baixa = result["baixa_confianca"]
    if baixa:
        st.warning(
            f"{len(baixa)} parcela(s) do Contas a Pagar tiveram a conta do fornecedor achada por "
            "similaridade de nome com confiança baixa (abaixo de 95%). Confira ou informe a "
            "conta correta abaixo."
        )
        vistos = set()
        for p in baixa:
            if p.nome in vistos:
                continue
            vistos.add(p.nome)
            cc1, cc2, cc3 = st.columns([4, 1, 1])
            cc1.text(f"{p.nome}  (score {p.match_score:.2f} → sugestão: {p.conta_fornecedor} {p.conta_fornecedor_nome})")
            atual = state["revisao"].get(p.nome, p.conta_fornecedor)
            nova_conta = cc2.text_input("Conta", value=atual, key=f"rev_{slug}_{p.nome}", label_visibility="collapsed")
            state["revisao"][p.nome] = nova_conta
            if cc3.button("Aplicar", key=f"apply_{slug}_{p.nome}"):
                result["overrides"][p.nome] = nova_conta
                save_overrides(result["overrides"], overrides_path(slug))
                st.success(f"Correção salva: {p.nome} → conta {nova_conta}. Reprocesse os arquivos para aplicar.")
    else:
        st.success("Todos os fornecedores encontrados tiveram alta confiança na conta sugerida.")

if result.get("unclassified"):
    st.error(
        f"{len(result['unclassified'])} lançamento(s) do extrato não se encaixaram em nenhuma "
        "regra conhecida (tipo de movimento novo para esta empresa)."
    )
    for u in result["unclassified"]:
        st.write(f"`{u.get('banco', '?')}` {u.get('date','')} R$ {u.get('amt',0):.2f} — {u.get('memo','')}")

st.subheader("4. Baixar arquivo(s)")
arquivos_gerados = gerar_txt(empresa, result, cnpj)
for chave, conteudo in arquivos_gerados.items():
    label = "conciliação bancária" if chave == "conciliacao" else "pendências do Contas a Pagar"
    nome_arquivo = st.text_input(
        f"Nome do arquivo ({label})",
        value=f"Conciliacao_{empresa['nome'].replace(' ', '_')}_{chave}_{ano_mes}.txt",
        key=f"nome_{slug}_{chave}",
    )
    st.download_button(
        f"⬇️ Baixar {label}", data=conteudo.encode("utf-8"), file_name=nome_arquivo,
        mime="text/plain", type="primary", key=f"dl_{slug}_{chave}",
    )

if not empresa.get("verificado"):
    st.subheader("5. Verificação")
    st.caption(
        "Depois de conferir um mês já fechado dessa empresa contra o arquivo gerado acima "
        "(linha a linha, do mesmo jeito que foi feito com a Antoninho e a Haroke), marque "
        "aqui — isso só afeta o aviso mostrado nesta tela pros próximos meses."
    )
    if st.button("✅ Marcar esta empresa como verificada"):
        update_empresa(slug, verificado=True)
        st.success("Empresa marcada como verificada. Recarregue a página para ver o novo status.")
