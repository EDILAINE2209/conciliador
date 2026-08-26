"""
Leitor da lista de fornecedores (grupo de contas 2.1.3.01) do Plano de
Contas da Haroke. A lógica em si (norm/load_fornecedores) foi promovida
para core/common/plano_de_contas.py porque deixou de ser específica da
Haroke — a Antoninho passou a usar o mesmo leitor. Este módulo só
reexporta, para não quebrar os imports existentes (core.haroke.generate,
core.haroke.matching).
"""
from core.common.plano_de_contas import norm, load_fornecedores

__all__ = ["norm", "load_fornecedores"]
