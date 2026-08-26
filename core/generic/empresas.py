"""
Lista de empresas criadas via self-service na página "Nova Empresa"
(diferente da Antoninho e da Haroke, que são páginas fixas em pages/).
Cada empresa é um dict:

{
  "slug": "mercadinho_teste",       # identifica a empresa (nome de arquivo, url, etc.)
  "nome": "Mercadinho Teste LTDA",
  "cnpj": "11222333000144",
  "modelo": "antoninho" | "haroke",
  "bancos": ["551", "8"],
  "contas": {"pix_recebido": "504", ...},   # chave da categoria -> conta desta empresa
  "observacoes": "...",
  "verificado": False,              # vira True quando alguém confirma que bateu
                                     # com um mês fechado de verdade
  "criado_em": "2026-08-26",
}

Fica salvo em empresas.json na pasta do app — igual ao padrão já usado
para o cadastro da Antoninho e as correções da Haroke (sem seed, porque
não existe uma empresa self-service "de fábrica").

IMPORTANTE (mesma limitação de sempre): isso só é durável se o arquivo for
baixado e subido pro GitHub depois — se o app reiniciar antes disso, as
empresas criadas aqui dentro se perdem.
"""
import json
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EMPRESAS_PATH = os.path.join(_ROOT, "empresas.json")
EMPRESAS_DATA_DIR = os.path.join(_ROOT, "empresas_data")


def slugify(nome: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '_', nome.strip().lower())
    return s.strip('_') or "empresa"


def load_empresas(path: str = EMPRESAS_PATH) -> list[dict]:
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return []


def save_empresas(empresas: list[dict], path: str = EMPRESAS_PATH):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(empresas, f, ensure_ascii=False, indent=1, sort_keys=False)


def add_empresa(empresa: dict, path: str = EMPRESAS_PATH) -> dict:
    """Gera um slug único (evita colisão com empresa já existente) e
    adiciona à lista. Devolve a empresa com o slug definitivo."""
    empresas = load_empresas(path)
    existentes = {e["slug"] for e in empresas}
    base = slugify(empresa["nome"])
    slug = base
    i = 2
    while slug in existentes:
        slug = f"{base}_{i}"
        i += 1
    empresa = dict(empresa, slug=slug)
    empresas.append(empresa)
    save_empresas(empresas, path)
    return empresa


def update_empresa(slug: str, **campos):
    empresas = load_empresas()
    for e in empresas:
        if e["slug"] == slug:
            e.update(campos)
            break
    save_empresas(empresas)


def get_empresa(slug: str):
    for e in load_empresas():
        if e["slug"] == slug:
            return e
    return None


def cadastro_path(slug: str) -> str:
    os.makedirs(EMPRESAS_DATA_DIR, exist_ok=True)
    return os.path.join(EMPRESAS_DATA_DIR, f"{slug}_cadastro.json")


def overrides_path(slug: str) -> str:
    os.makedirs(EMPRESAS_DATA_DIR, exist_ok=True)
    return os.path.join(EMPRESAS_DATA_DIR, f"{slug}_overrides.json")
