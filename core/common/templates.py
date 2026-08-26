"""
Descrição dos dois "modelos" de empresa já validados no app (Antoninho e
Haroke), usada pela página "Nova Empresa" — tanto para gerar o pedido de
revisão quanto para o modo self-service (core/generic/engine.py).

As chaves em "categorias" (`chave`) são estáveis e usadas diretamente pelo
motor genérico para remapear a conta de cada categoria — não renomeie sem
atualizar core/generic/engine.py junto.

estrategia_fornecedor e bancos_permitidos não são escolha livre no modo
self-service: cada modelo já reaproveita uma função de classificação
existente (core.antoninho.classify / core.haroke.classify) que só sabe
lidar com a estratégia e os bancos com que foi validada.
"""

BANCOS_NOMES = {
    "551": "Sicoob",
    "8": "Banco do Brasil",
    "552": "Itaú",
}

TEMPLATES = {
    "antoninho": {
        "nome": "Antoninho Atacado e Varejo",
        "descricao": (
            "Fornecedor é achado por um cadastro de ID numérico (o mesmo ID que "
            "aparece no Contas a Pagar), construído aos poucos — a empresa nova "
            "começa sem nenhum fornecedor cadastrado, tudo cai em revisão manual "
            "no primeiro mês. Funciona com Sicoob, Banco do Brasil e/ou Itaú, em "
            "qualquer combinação."
        ),
        "estrategia_fornecedor": "id",
        "bancos_permitidos": ["551", "8", "552"],
        "categorias": [
            {"chave": "pix_recebido", "nome": "PIX recebidos (Sicoob)", "conta_exemplo": "504"},
            {"chave": "cartao", "nome": "Cartão / maquininha (SIPAG, Cielo, Rede)", "conta_exemplo": "730"},
            {"chave": "tarifas", "nome": "Tarifas bancárias", "conta_exemplo": "906"},
            {"chave": "iof", "nome": "IOF", "conta_exemplo": "907"},
            {"chave": "juros", "nome": "Juros", "conta_exemplo": "374"},
            {"chave": "rendefacil", "nome": "BB Rende Fácil (aplicação e resgate)", "conta_exemplo": "11"},
            {"chave": "fornecedor_fallback", "nome": "Fornecedor não cadastrado (usado até revisar)", "conta_exemplo": "506"},
            {"chave": "demais", "nome": "Demais movimentos", "conta_exemplo": "506"},
        ],
    },
    "haroke": {
        "nome": "Haroke Supermercado",
        "descricao": (
            "Fornecedor é achado por similaridade de nome contra um Plano de "
            "Contas enviado a cada processamento. Funciona só com Banco do "
            "Brasil e Sicoob (os dois bancos com que essa lógica foi validada) — "
            "para outro banco, use o modelo Antoninho."
        ),
        "estrategia_fornecedor": "nome",
        "bancos_permitidos": ["8", "551"],
        "categorias": [
            {"chave": "fornecedor_fallback", "nome": "Fornecedor não encontrado no Plano de Contas", "conta_exemplo": "506"},
            {"chave": "pix_recebidos", "nome": "PIX recebidos", "conta_exemplo": "744"},
            {"chave": "cred_liq_cobranca", "nome": "Créd. Liq. Cobrança (só Sicoob)", "conta_exemplo": "744"},
            {"chave": "sipag_cielo", "nome": "SIPAG / Cielo / Rede (cartão)", "conta_exemplo": "504"},
            {"chave": "tarifas", "nome": "Tarifas bancárias", "conta_exemplo": "698"},
            {"chave": "rendefacil", "nome": "BB Rende Fácil (aplicação e resgate)", "conta_exemplo": "731"},
            {"chave": "iof", "nome": "IOF (só Sicoob)", "conta_exemplo": "718"},
            {"chave": "juros", "nome": "Juros (só Sicoob)", "conta_exemplo": "374"},
            {"chave": "demais", "nome": "Demais movimentos", "conta_exemplo": "506"},
        ],
    },
}
