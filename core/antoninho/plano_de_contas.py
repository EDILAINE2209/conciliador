"""
Leitor do Plano de Contas para a Antoninho — reexporta a lógica genérica de
core/common/plano_de_contas.py (mesmo leiaute observado na Haroke). Usado
como fonte de SUGESTÃO de conta para fornecedores fora do cadastro por ID
(ver core/antoninho/matching.py); ao contrário da Haroke, a Antoninho não
guarda essas sugestões separadas — uma vez aceita, ela vira uma entrada
comum no cadastro por ID (antoninho_fornecedores.json), do mesmo jeito que
uma conta informada manualmente.
"""
from core.common.plano_de_contas import norm, load_fornecedores

__all__ = ["norm", "load_fornecedores"]
