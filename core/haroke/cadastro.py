"""
Correções manuais de fornecedor -> conta contábil da Haroke.

Diferente da Antoninho (onde o cadastro é por ID numérico do fornecedor),
aqui a conta de cada fornecedor é achada automaticamente comparando o nome
do Contas a Pagar com o nome no Plano de Contas (similaridade de texto) —
então este arquivo guarda só as correções manuais para os casos em que essa
comparação erra ou em que o fornecedor ainda não tem conta própria no plano
(caem em 506, Fornecedores Diversos).

Reconstruído a partir do fechamento de julho/2026 (ver
Regras_Conciliacao_Haroke.md, enviado junto com os arquivos da empresa).
"""
import json
import os

SEED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "haroke_overrides_seed.json")
OVERRIDES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                               "haroke_overrides.json")

CONTA_PADRAO = "506"  # Fornecedores Diversos


def load_overrides(path: str = OVERRIDES_PATH) -> dict:
    """{"NOME EXATO DO FORNECEDOR NO CONTAS A PAGAR": "conta"}"""
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    if os.path.exists(SEED_PATH):
        with open(SEED_PATH, encoding='utf-8') as f:
            overrides = json.load(f)
        save_overrides(overrides, path)
        return overrides
    return {}


def save_overrides(overrides: dict, path: str = OVERRIDES_PATH):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(overrides, f, ensure_ascii=False, indent=1, sort_keys=True)
