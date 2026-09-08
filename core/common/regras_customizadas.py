"""
Regras de classificação personalizadas — cadastradas pelo próprio usuário do
app, pela tela, sem precisar mexer em código, para tipos de lançamento novos
que aparecem no extrato e ainda não têm regra fixa no motor de classificação
(cada empresa já tem seu conjunto de regras fixas, validado contra um mês
fechado real; isto aqui é só a "válvula de escape" para o que aparecer
depois disso).

Cada empresa (Haroke, Antoninho, ...) guarda sua própria lista, num par de
arquivos JSON — mesmo padrão já usado no cadastro de fornecedores/overrides:
um arquivo "seed" (ponto de partida, versionado no Git) e um arquivo "vivo"
(gravado pelo app enquanto está rodando; só fica permanente se for baixado
e subir no lugar do seed no GitHub — ver README, seção "Publicando na
nuvem").

Formato de cada regra:
{
  "padrao": "texto a comparar com o memo do banco",
  "tipo_match": "igual" | "prefixo" | "contem",
  "banco": "8" | "551" | "552" | ""  (vazio = qualquer banco),
  "debito": "conta, ou a palavra especial BANCO",
  "credito": "conta, ou a palavra especial BANCO",
  "historico": "código do histórico",
  "descricao": "explicação livre, pra lembrar por que a regra existe"
}

"debito"/"credito": a palavra especial "BANCO" (sem acento, qualquer caixa)
significa "a conta do banco de onde veio essa transação" — assim uma regra
só serve tanto para transações do BB quanto do Sicoob (ou o banco que for)
sem precisar cadastrar duas vezes. Qualquer outro texto é usado literalmente
como número de conta.

As regras são checadas **na ordem cadastrada**, e só depois de todas as
regras fixas do motor (ou seja: uma regra fixa que já cobre o memo sempre
tem prioridade sobre uma regra personalizada com o mesmo padrão).
"""
import json
import os

TIPOS_MATCH = ("igual", "prefixo", "contem")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _paths(empresa_slug: str):
    seed = os.path.join(_ROOT, f"{empresa_slug}_regras_customizadas_seed.json")
    live = os.path.join(_ROOT, f"{empresa_slug}_regras_customizadas.json")
    return seed, live


def regra_vazia() -> dict:
    return {"padrao": "", "tipo_match": "prefixo", "banco": "", "debito": "506",
            "credito": "BANCO", "historico": "429", "descricao": ""}


def load_regras(empresa_slug: str) -> list:
    """Carrega as regras personalizadas daquela empresa. Na primeira vez
    (sem arquivo "vivo" ainda), parte do seed, se existir, e já grava o
    arquivo vivo — mesmo comportamento do cadastro de fornecedores."""
    seed, live = _paths(empresa_slug)
    if os.path.exists(live):
        with open(live, encoding='utf-8') as f:
            return json.load(f)
    if os.path.exists(seed):
        with open(seed, encoding='utf-8') as f:
            regras = json.load(f)
        save_regras(regras, empresa_slug)
        return regras
    return []


def save_regras(regras: list, empresa_slug: str):
    _, live = _paths(empresa_slug)
    with open(live, 'w', encoding='utf-8') as f:
        json.dump(regras, f, ensure_ascii=False, indent=1)


def encontrar_regra(memo: str, banco: str, regras: list):
    """Devolve a primeira regra cadastrada que casa com esse memo/banco, ou
    None se nenhuma bater. Comparação sempre em maiúsculas (acento
    importa — cadastre o padrão exatamente como aparece no extrato)."""
    memo_up = (memo or "").strip().upper()
    for r in regras:
        banco_regra = (r.get("banco") or "").strip()
        if banco_regra and banco_regra != banco:
            continue
        padrao = (r.get("padrao") or "").strip().upper()
        if not padrao:
            continue
        tipo = r.get("tipo_match", "prefixo")
        if tipo == "igual" and memo_up == padrao:
            return r
        if tipo == "prefixo" and memo_up.startswith(padrao):
            return r
        if tipo == "contem" and padrao in memo_up:
            return r
    return None


def resolver_conta(campo: str, banco: str) -> str:
    campo = (campo or "").strip()
    if campo.upper() == "BANCO":
        return banco
    return campo or banco
