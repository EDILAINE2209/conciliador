import json

import streamlit as st

from core.auth import require_password
from core.common.templates import TEMPLATES, BANCOS_NOMES
from core.generic.empresas import add_empresa

st.set_page_config(page_title="Nova Empresa", page_icon="🏗️", layout="wide")
require_password()

st.title("🏗️ Nova Empresa")
st.info(
    "Preencha os dados abaixo \"copiando\" as regras já validadas da Antoninho ou da "
    "Haroke. No final você escolhe: **criar a empresa agora** (fica pronta pra usar na "
    "hora, em **🏢 Empresas**) ou **baixar um pedido** pra eu revisar antes — veja o "
    "aviso da opção 1 antes de decidir."
)

st.subheader("1. Dados da empresa")
c1, c2 = st.columns(2)
nome_empresa = c1.text_input("Nome da empresa")
cnpj = c2.text_input("CNPJ")

st.subheader("2. Copiar de qual empresa?")
modelo_key = st.radio(
    "Modelo", options=list(TEMPLATES.keys()), format_func=lambda k: TEMPLATES[k]["nome"],
    horizontal=True,
)
modelo = TEMPLATES[modelo_key]
st.caption(modelo["descricao"])

st.subheader("3. Bancos usados")
bancos_marcados = []
permitidos = modelo["bancos_permitidos"]
cols = st.columns(len(permitidos))
for codigo, col in zip(permitidos, cols):
    marcado = col.checkbox(BANCOS_NOMES[codigo], value=True, key=f"banco_{modelo_key}_{codigo}")
    if marcado:
        bancos_marcados.append(codigo)
if modelo_key == "haroke":
    st.caption(
        "O modelo Haroke só sabe lidar com Sicoob e Banco do Brasil (foi só com esses "
        "dois que essa lógica foi validada). Pra outro banco, use o modelo Antoninho."
    )

st.subheader("4. Contas contábeis por categoria")
st.caption(
    f"Estas são as categorias do modelo \"{modelo['nome']}\". A coluna \"conta de "
    "exemplo\" mostra o que essa empresa usa, só como referência — preencha ao lado "
    "a conta que a SUA empresa nova usa para cada categoria (deixe em branco pra usar "
    "a mesma conta de exemplo)."
)
contas = {}
for cat in modelo["categorias"]:
    cc1, cc2, cc3 = st.columns([3, 2, 2])
    cc1.text(cat["nome"])
    cc2.text(f"exemplo: {cat['conta_exemplo']}")
    valor = cc3.text_input("Conta desta empresa", key=f"conta_{modelo_key}_{cat['chave']}",
                            label_visibility="collapsed", placeholder=cat["conta_exemplo"])
    contas[cat["chave"]] = valor.strip() or cat["conta_exemplo"]

st.subheader("5. Fornecedores")
if modelo["estrategia_fornecedor"] == "id":
    st.caption(
        "Esta empresa vai achar a conta do fornecedor por um cadastro de ID, igual a "
        "Antoninho — ele começa vazio: no primeiro mês, todo fornecedor cai em revisão "
        "manual (aba \"Fornecedores para revisar\", já na página de processar), e o "
        "cadastro vai crescendo sozinho a partir daí."
    )
else:
    st.caption(
        "Esta empresa vai achar a conta do fornecedor por similaridade de nome contra "
        "um Plano de Contas, igual a Haroke — você precisa enviar o Plano de Contas "
        "atualizado toda vez que gerar o arquivo do mês."
    )

st.subheader("6. Observações / regras especiais")
observacoes = st.text_area(
    "Alguma regra fora do padrão? (ex.: \"PIX grande pra outra empresa da carteira tem "
    "conta própria\", como acontece na Haroke) — regras assim NÃO são aplicadas "
    "automaticamente pelo modo self-service; anote aqui e ajuste manualmente o arquivo "
    "gerado, ou baixe um pedido pra eu incluir a regra de verdade.",
    height=100,
)

pronto = bool(nome_empresa and cnpj and bancos_marcados)
if not pronto:
    st.info("Preencha ao menos o nome, o CNPJ e pelo menos um banco para continuar.")

st.subheader("7. Criar")
col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Opção 1 — criar agora (self-service)**")
    st.caption(
        "A empresa fica pronta pra usar imediatamente em **🏢 Empresas**, sem precisar "
        "falar comigo. Ela nasce marcada como **não verificada** até alguém conferir um "
        "mês fechado de verdade contra o arquivo gerado — os primeiros meses merecem "
        "atenção redobrada. Isso também não fica salvo entre reinícios do app até você "
        "subir o `empresas.json` pro GitHub (mesma regra do cadastro de fornecedores)."
    )
    if st.button("🚀 Criar empresa agora", type="primary", disabled=not pronto):
        nova = add_empresa({
            "nome": nome_empresa, "cnpj": cnpj, "modelo": modelo_key,
            "bancos": bancos_marcados, "contas": contas, "observacoes": observacoes,
            "verificado": False,
        })
        st.success(
            f"Empresa \"{nova['nome']}\" criada! Vá em **🏢 Empresas** no menu à esquerda "
            "pra gerar o primeiro arquivo."
        )
        st.page_link("pages/5_🏢_Empresas.py", label="Ir para 🏢 Empresas", icon="🏢")

with col_b:
    st.markdown("**Opção 2 — baixar pedido pra eu revisar**")
    st.caption(
        "Baixa um `.json` com tudo isso. Mande pra mim numa conversa, de preferência "
        "junto com os extratos e o Contas a Pagar de um mês já fechado — bom pra casos "
        "fora do padrão (banco novo, regra especial) que o modo self-service não cobre."
    )
    pedido = {
        "nome_empresa": nome_empresa, "cnpj": cnpj, "modelo": modelo_key,
        "bancos": bancos_marcados, "contas_por_categoria": contas,
        "estrategia_fornecedor": modelo["estrategia_fornecedor"], "observacoes": observacoes,
    }
    st.download_button(
        "⬇️ Baixar pedido (.json)",
        data=json.dumps(pedido, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=f"pedido_nova_empresa_{(nome_empresa or 'empresa').strip().replace(' ', '_')}.json",
        mime="application/json",
        disabled=not pronto,
    )
