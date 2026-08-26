"""
Sugestão de conta contábil para um fornecedor novo (fora do cadastro por
ID) da Antoninho, por similaridade de nome contra um Plano de Contas
enviado na hora — mesma técnica usada na Haroke (core/haroke/matching.py),
mas sem lista de overrides: aqui a sugestão, uma vez aceita na tela de
revisão, já vira uma entrada normal do cadastro por ID (não precisa de um
mecanismo de correção à parte).
"""
import difflib

from core.antoninho.plano_de_contas import norm


def best_account(nome_fornecedor: str, accounts: list[dict]):
    """Devolve (conta, nome_da_conta, score) com o melhor candidato do
    Plano de Contas para o nome informado. (None, nome_fornecedor, 0.0) se
    a lista de contas estiver vazia."""
    n1 = norm(nome_fornecedor)
    best, best_score = None, 0.0
    for acc in accounts:
        score = difflib.SequenceMatcher(None, n1, acc['norm']).ratio()
        if score > best_score:
            best_score, best = score, acc
    if best is None:
        return None, nome_fornecedor, 0.0
    return best['code'], best['nome'], best_score
