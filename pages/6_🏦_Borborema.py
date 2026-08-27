import tempfile
import os
from datetime import datetime

import streamlit as st
import pandas as pd

from core.auth import require_password
from core.borborema.generate import processar, gerar_txt
from core.borborema.classify import NOMES_CATEGORIA

st.set_page_config(page_title="Borborema — Conciliação Bancária", page_icon="🏦", layout="wide")
require_password()

CNPJ_PADRAO = "19817980000148"

st.title("🏦 Borborema Borborema E Cia Ltda — Conciliação Bancária")
st.caption(
    "Lê o extrato Bradesco em PDF (escaneado, sem camada de texto — o app usa OCR), "
    "classifica cada lançamento automaticamente e gera o .txt de importação contábil "
    "do mês, no mesmo layout usado pelas outras empresas."
)
st.warning(
    "⚠️ **Este extrato é uma imagem escaneada, então o OCR erra** (dígito trocado, "
    "linha perdida, às vezes até a própria página do banco sai com uma via física "
    "cortada). Por isso o app confere automaticamente o saldo de cada dia contra o "
    "\"SALDO EM dd/mm\" impresso no extrato — todo dia com saldo divergente vem "
    "marcado abaixo para revisão manual antes de gerar o .txt. **Sempre confira a "
    "tabela — principalmente as linhas marcadas — antes de baixar o arquivo final.**"
)


def init_state():
    defaults = {
        "borborema_cnpj": CNPJ_PADRAO,
        "borborema_ano": str(datetime.now().year),
        "borborema_result": None,
        "borborema_df": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()

st.subheader("1. Extrato do mês")
c1, c2 = st.columns([1, 1])
st.session_state["borborema_cnpj"] = c1.text_input("CNPJ", value=st.session_state["borborema_cnpj"])
st.session_state["borborema_ano"] = c2.text_input("Ano do período (AAAA)", value=st.session_state["borborema_ano"])

pdf_file = st.file_uploader("Extrato Bradesco (PDF)", type=["pdf"], key="borborema_pdf")

if st.button("🔄 Processar (OCR)", type="primary", disabled=pdf_file is None):
    with st.spinner("Lendo o PDF com OCR — isso demora um a três minutos, dependendo do número de páginas..."):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "extrato.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_file.getbuffer())
            result = processar(pdf_path)
    st.session_state["borborema_result"] = result
    rows = []
    for l in result["lancamentos"]:
        rows.append({
            "revisar": l.revisar,
            "data": l.date,
            "debito": l.debito,
            "credito": l.credito,
            "historico": l.historico,
            "valor": l.valor,
            "complemento": l.complemento,
            "categoria": NOMES_CATEGORIA.get(l.categoria, l.categoria or "(não classificado)"),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["revisar", "data"], ascending=[False, True], kind="stable").reset_index(drop=True)
    st.session_state["borborema_df"] = df

result = st.session_state["borborema_result"]
if result is None:
    st.info("Envie o extrato em PDF e clique em Processar.")
    st.stop()

st.subheader("2. Resumo")
mcol1, mcol2, mcol3 = st.columns(3)
mcol1.metric("Lançamentos extraídos", len(result["lancamentos"]))
mcol2.metric("Para revisar", result["total_revisar"])
mcol3.metric("Dias com saldo divergente", len(result["dias_divergentes"]))

if result["saldo_anterior"] is None:
    st.error(
        "Não encontrei o \"SALDO ANTERIOR\" impresso no extrato — sem ele não dá pra "
        "conferir o saldo de nenhum dia. Confira TODOS os lançamentos abaixo com atenção "
        "redobrada antes de baixar o arquivo."
    )

if result["dias_divergentes"]:
    linhas_div = []
    for dia, (calc, esperado) in sorted(result["dias_divergentes"].items(), key=lambda kv: kv[0]):
        linhas_div.append(f"**{dia}**: calculado R$ {calc:,.2f} × impresso no extrato R$ {esperado:,.2f}"
                           .replace(",", "§").replace(".", ",").replace("§", "."))
    st.warning(
        "Estes dias têm saldo calculado diferente do saldo impresso no extrato — "
        "algum lançamento do dia está errado ou faltando (erro de OCR). "
        "Os lançamentos desses dias já vêm marcados para revisão na tabela abaixo:\n\n"
        + "\n\n".join(linhas_div)
    )
else:
    st.success("O saldo calculado bateu com o saldo impresso em todos os dias conferidos.")

st.subheader("3. Lançamentos — confira e corrija antes de baixar")
st.caption(
    "Edite direto na tabela qualquer campo que estiver errado (a coluna **revisar** é só "
    "um alerta visual, marque/desmarque como quiser). Linhas com valores manifestamente "
    "errados podem ser apagadas com o ícone de lixeira, e você pode adicionar uma linha "
    "nova pelo **+** no fim da tabela para um lançamento que o OCR não pegou."
)

edited_df = st.data_editor(
    st.session_state["borborema_df"],
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "revisar": st.column_config.CheckboxColumn("Revisar?"),
        "data": st.column_config.TextColumn("Data (dd/mm)"),
        "debito": st.column_config.TextColumn("Débito"),
        "credito": st.column_config.TextColumn("Crédito"),
        "historico": st.column_config.TextColumn("Histórico"),
        "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
        "complemento": st.column_config.TextColumn("Complemento"),
        "categoria": st.column_config.TextColumn("Categoria (informativo)", disabled=True),
    },
    key="borborema_editor",
)

pendentes = int(edited_df["revisar"].sum()) if not edited_df.empty else 0
if pendentes:
    st.warning(f"Ainda há {pendentes} lançamento(s) marcado(s) para revisar.")

st.subheader("4. Baixar arquivo")
cnpj = st.session_state["borborema_cnpj"]
ano = st.session_state["borborema_ano"]


class _L:
    """Wrapper simples só pra reaproveitar gerar_txt sem reimportar o dataclass."""
    def __init__(self, row):
        self.date = row["data"]
        self.debito = str(row["debito"])
        self.credito = str(row["credito"])
        self.historico = str(row["historico"])
        self.valor = float(row["valor"])
        self.complemento = row["complemento"] or ""


lancamentos_final = [_L(row) for _, row in edited_df.iterrows()] if not edited_df.empty else []
txt = gerar_txt(lancamentos_final, cnpj, ano)

mes_guess = lancamentos_final[0].date.split('/')[1] if lancamentos_final else "00"
nome_arquivo = st.text_input(
    "Nome do arquivo", value=f"LANCAMENTOS_{mes_guess}{ano}.txt",
)
st.download_button(
    "⬇️ Baixar .txt de lançamentos", data=txt.encode("utf-8"),
    file_name=nome_arquivo, mime="text/plain", type="primary",
)
