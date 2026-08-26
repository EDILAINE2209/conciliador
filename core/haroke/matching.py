"""
Acha a conta contábil de um fornecedor por similaridade de texto entre o
nome do Contas a Pagar e os nomes das contas de fornecedor do Plano de
Contas — com uma lista de correções manuais (overrides) que tem prioridade
sobre a comparação automática.
"""
import difflib

from core.haroke.plano_de_contas import norm


def best_account(nome_fornecedor: str, accounts: list[dict], overrides: dict):
    """Devolve (conta, nome_da_conta, score). score=1.0 quando veio de uma
    correção manual (overrides); caso contrário é a similaridade de texto
    (0 a 1) do melhor candidato achado no Plano de Contas."""
    if nome_fornecedor in overrides:
        code = str(overrides[nome_fornecedor])
        acc = next((a for a in accounts if a['code'] == code), None)
        return code, (acc['nome'] if acc else nome_fornecedor), 1.0

    n1 = norm(nome_fornecedor)
    best, best_score = None, 0.0
    for acc in accounts:
        score = difflib.SequenceMatcher(None, n1, acc['norm']).ratio()
        if score > best_score:
            best_score, best = score, acc
    if best is None:
        return None, nome_fornecedor, 0.0
    return best['code'], best['nome'], best_score
