"""
Leitor do relatório "Contas a Pagar por Entrada" (Excel exportado do sistema
da Antoninho). É um relatório de página múltipla despejado num único sheet,
com linhas de cabeçalho repetidas, linhas "Entrada: dd/mm/aaaa" e linhas
"Sub Total:" intercaladas — este leitor filtra tudo isso e fica só com as
linhas de parcela de fato.

Colunas reais (há células mescladas no Excel original, por isso os índices
pulam): 0=Fornecedor ("ID - NOME"), 5=Documento, 8=Vencimento, 10=V. Parcela.
"""
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Payable:
    fornecedor: str      # "ID - NOME" como veio na planilha
    fid: str              # só o ID numérico
    nome: str
    documento: str
    vencimento: str        # AAAAMMDD
    valor: float
    usado: bool = field(default=False, compare=False)


def parse_payables_excel(path: str) -> list[Payable]:
    xls = pd.ExcelFile(path)
    df = xls.parse(xls.sheet_names[0], header=None)
    out = []
    for i in range(len(df)):
        row = df.iloc[i]
        v0 = row[0]
        if pd.isna(v0):
            continue
        v0 = str(v0)
        if ' - ' not in v0:
            continue  # cabeçalho, "Entrada:", "Sub Total:", "Total Geral:" etc.
        try:
            documento = str(row[5])
            vencimento = pd.to_datetime(row[8]).strftime('%Y%m%d')
            valor = float(row[10])
        except Exception:
            continue
        fid, _, nome = v0.partition(' - ')
        out.append(Payable(
            fornecedor=v0, fid=fid.strip(), nome=nome.strip(),
            documento=documento, vencimento=vencimento, valor=valor,
        ))
    return out
