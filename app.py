import streamlit as st

from core.auth import require_password

st.set_page_config(page_title="Conciliação Contábil — CSJ_IA", page_icon="📄", layout="wide")
require_password()

st.title("📄 Conciliação Contábil")
st.write(
    "Escolha uma empresa no menu à esquerda para gerar o arquivo de importação "
    "contábil do mês."
)
st.page_link("pages/1_🏥_APAE.py", label="APAE São Sebastião do Paraiso — Doações", icon="🏥")
st.page_link("pages/2_🏪_Antoninho.py", label="Antoninho Atacado e Varejo — Conciliação Bancária", icon="🏪")
