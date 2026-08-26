"""
Autenticação simples por senha única, compartilhada entre todas as páginas
do app (a sessão fica autenticada para todas as empresas de uma vez).

Defina a variável de ambiente APP_PASSWORD (ou o secret "APP_PASSWORD" no
Streamlit Cloud) para exigir senha. Se não estiver definida, o app fica
aberto sem tela de login — útil para testar localmente.
"""
import os

import streamlit as st

from core.branding import show_logo


def _senha_configurada():
    pwd = os.environ.get("APP_PASSWORD")
    if pwd:
        return pwd
    try:
        return st.secrets.get("APP_PASSWORD", None)
    except Exception:
        return None


def require_password():
    """Bloqueia a página atual com uma tela de senha, se APP_PASSWORD
    estiver configurada e a sessão ainda não tiver sido autenticada.
    Chame isso logo no início de CADA página (app.py e cada arquivo em
    pages/)."""
    show_logo()
    pwd = _senha_configurada()
    if not pwd:
        return
    if st.session_state.get("auth_ok"):
        return

    st.title("🔒 Acesso restrito")
    entered = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if entered == pwd:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()
