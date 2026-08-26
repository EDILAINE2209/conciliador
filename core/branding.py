"""
Logo da contabilidade no topo do menu lateral, em todas as páginas do app
(inclusive na tela de login). Basta colocar o arquivo em
`assets/logo.png` (ou logo.svg / logo.jpg — ver LOGO_CANDIDATES abaixo) na
raiz do projeto e subir pro GitHub; se nenhum desses arquivos existir, o
app simplesmente não mostra logo nenhum, sem quebrar.
"""
import os

import streamlit as st

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_LOGO_CANDIDATES = ["logo.png", "logo.svg", "logo.jpg", "logo.jpeg"]


def _logo_path():
    for nome in _LOGO_CANDIDATES:
        p = os.path.join(_ASSETS_DIR, nome)
        if os.path.exists(p):
            return p
    return None


def show_logo():
    p = _logo_path()
    if p:
        st.logo(p)
