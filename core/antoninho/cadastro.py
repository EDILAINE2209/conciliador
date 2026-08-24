"""
Cadastro de fornecedores da Antoninho: mapeia o ID numérico do fornecedor
(o mesmo número que aparece em "123 - NOME DA EMPRESA" no Contas a Pagar)
para a conta contábil específica dele no Plano de Contas (ex.: 1219 para
FRIGORIFICO FRIGMAR EIRELI). Fornecedores sem conta própria caem na conta
506 "Fornecedores Diversos".

Esse mapeamento foi reconstruído a partir de dois arquivos de referência
reais de julho/2026 (a conciliação bancária já fechada e as pendências do
mês), cruzando cada pagamento com o Contas a Pagar por valor+vencimento —
zero inconsistências entre as duas fontes nos 258 fornecedores encontrados.
Ele é reaproveitável em qualquer mês seguinte (a conta de cada fornecedor
não muda), mas cresce com o tempo: fornecedores novos que a Antoninho
passar a usar precisam ser adicionados aqui na tela de "Cadastro" do app,
uma única vez.

Fica salvo em antoninho_fornecedores.json na pasta do app (separado do
config.json genérico, porque esse cadastro é grande e específico da
Antoninho).
"""
import json
import os

SEED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "antoninho_fornecedores_seed.json")
CADASTRO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              "antoninho_fornecedores.json")

CONTA_PADRAO = "506"  # Fornecedores Diversos


def load_cadastro(path: str = CADASTRO_PATH) -> dict:
    """{"<id>": {"conta": "1219", "nome": "FRIGORIFICO FRIGMAR EIRELI"}, ...}"""
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    # primeira execução: parte da semente reconstruída de julho/2026
    if os.path.exists(SEED_PATH):
        with open(SEED_PATH, encoding='utf-8') as f:
            cadastro = json.load(f)
        save_cadastro(cadastro, path)
        return cadastro
    return {}


def save_cadastro(cadastro: dict, path: str = CADASTRO_PATH):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cadastro, f, ensure_ascii=False, indent=1, sort_keys=True)


def get_conta(cadastro: dict, fid: str, nome: str = "") -> tuple[str, bool]:
    """Devolve (conta, encontrado). Se não encontrado, devolve a conta
    padrão (506) e encontrado=False, para o app poder sinalizar 'fornecedor
    novo, confira a conta' na tela de revisão."""
    if fid and fid in cadastro:
        return cadastro[fid]["conta"], True
    return CONTA_PADRAO, False


def registrar_fornecedor(cadastro: dict, fid: str, nome: str, conta: str):
    cadastro[fid] = {"conta": conta, "nome": nome}
