"""
Configuração do app: uma ou mais "empresas" cadastradas, cada uma com seu
CNPJ, contas contábeis, histórico padrão e regras especiais reutilizáveis
(ex.: "Ingressos Feijoada" -> conta 826 / histórico 338).

Fica tudo salvo em config.json na pasta do app. Pode ser editado pela tela
de "Configurações" do Streamlit sem mexer em código.

Formato:
{
  "empresas": {
    "Nome da empresa": {
      "cnpj": "...",
      "contas": {"doacao_pf": "289", "doacao_pj": "765", "suspensa": "5", "banco": "7"},
      "historico_doacao": "401",
      "tolerancia_valor": 0.005,
      "regras_especiais": [{"nome": ..., "conta_credito": ..., "historico": ..., "descricao": ...}]
    },
    ...
  }
}
"""
import json
import os

NOME_EMPRESA_PADRAO = "APAE São Sebastião do Paraiso"


def empresa_vazia() -> dict:
    return {
        "cnpj": "",
        "contas": {
            "doacao_pf": "289",
            "doacao_pj": "765",
            "suspensa": "5",
            "banco": "7",
        },
        "historico_doacao": "401",
        "tolerancia_valor": 0.005,
        "regras_especiais": [],
    }


def _empresa_padrao_apae() -> dict:
    e = empresa_vazia()
    e["cnpj"] = "19098326000121"
    e["regras_especiais"] = [
        {
            "nome": "Ingressos Feijoada",
            "conta_credito": "826",
            "historico": "338",
            "descricao": "PIX de venda de ingressos de evento (feijoada), identificado manualmente",
        }
    ]
    return e


DEFAULT_CONFIG = {
    "empresas": {
        NOME_EMPRESA_PADRAO: _empresa_padrao_apae(),
    }
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def _garantir_campos_empresa(empresa: dict) -> dict:
    base = empresa_vazia()
    for k, v in base.items():
        empresa.setdefault(k, v)
    for k, v in base["contas"].items():
        empresa["contas"].setdefault(k, v)
    return empresa


def load_config(path: str = CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        save_config(DEFAULT_CONFIG, path)
        return json.loads(json.dumps(DEFAULT_CONFIG))

    with open(path, encoding='utf-8') as f:
        cfg = json.load(f)

    # Migração automática: configs antigas (de antes do suporte a várias
    # empresas) tinham cnpj/contas/etc direto na raiz do arquivo. Se for o
    # caso, envolve isso numa única empresa para não perder nada.
    if "empresas" not in cfg:
        empresa_antiga = {
            "cnpj": cfg.get("cnpj", ""),
            "contas": cfg.get("contas", {}),
            "historico_doacao": cfg.get("historico_doacao", "401"),
            "tolerancia_valor": cfg.get("tolerancia_valor", 0.005),
            "regras_especiais": cfg.get("regras_especiais", []),
        }
        cfg = {"empresas": {NOME_EMPRESA_PADRAO: empresa_antiga}}

    if not cfg["empresas"]:
        cfg["empresas"][NOME_EMPRESA_PADRAO] = empresa_vazia()

    for nome, empresa in cfg["empresas"].items():
        cfg["empresas"][nome] = _garantir_campos_empresa(empresa)

    return cfg


def save_config(cfg: dict, path: str = CONFIG_PATH):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def adicionar_empresa(cfg: dict, nome: str, cnpj: str = "") -> dict:
    """Cria uma nova empresa com valores padrão (contas 289/765/5/7/401)."""
    nova = empresa_vazia()
    nova["cnpj"] = cnpj
    cfg["empresas"][nome] = nova
    return cfg


def remover_empresa(cfg: dict, nome: str) -> dict:
    cfg["empresas"].pop(nome, None)
    if not cfg["empresas"]:
        cfg["empresas"][NOME_EMPRESA_PADRAO] = empresa_vazia()
    return cfg


def get_or_create_empresa(cfg: dict, nome: str, cnpj_padrao: str = "") -> dict:
    """Usado por cada página do app (uma por empresa): devolve a config
    daquela empresa, criando com valores padrão na primeira vez que a
    página rodar (e salvando em disco, pra já ficar disponível na aba de
    configurações daquela página)."""
    if nome not in cfg["empresas"]:
        adicionar_empresa(cfg, nome, cnpj_padrao)
        save_config(cfg)
    return cfg["empresas"][nome]
