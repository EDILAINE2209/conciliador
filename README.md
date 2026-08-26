# Conciliação Contábil — CSJ_IA

Aplicativo web (Streamlit) com uma página por empresa/cliente, todas atrás
de uma única senha. Hoje tem três empresas ativas, mais uma página para
pedir a inclusão de empresas novas:

- **APAE São Sebastião do Paraiso** — concilia o relatório de doações
  (PDF) com o extrato bancário (OFX) e gera o `.txt` de importação.
- **Antoninho Atacado e Varejo** — concilia os 3 extratos bancários
  (Sicoob, Itaú, Banco do Brasil) com o Contas a Pagar e gera dois
  `.txt`: a conciliação bancária do mês e as pendências do Contas a
  Pagar. Também aceita, opcionalmente, o Plano de Contas para sugerir
  conta de fornecedores novos por similaridade de nome.
- **Haroke Supermercado** — concilia os 2 extratos bancários (Banco do
  Brasil, Sicoob) com o Contas a Pagar e o Plano de Contas (a conta de
  cada fornecedor é achada por similaridade de nome, em vez de um
  cadastro de IDs) e gera um único `.txt` de conciliação bancária.
- **Nova Empresa** — formulário para o próprio pessoal do departamento
  incluir uma empresa nova "copiando" as regras da Antoninho ou da
  Haroke: escolhe o modelo, os bancos, a conta de cada categoria, e tem
  duas saídas — **criar a empresa agora** (self-service, fica pronta na
  hora) ou **baixar um pedido** pra eu revisar antes (bom pra casos fora
  do padrão). Ver "Página: Nova Empresa" mais abaixo.
- **Empresas** — onde as empresas criadas pelo self-service acima geram
  o arquivo do mês, de forma bem parecida com a Antoninho/Haroke, mas
  numa página só e genérica (`core/generic/`) em vez de uma página fixa
  por empresa. Toda empresa nasce marcada como **não verificada** até
  alguém conferir um mês fechado de verdade — ver "Página: Empresas"
  mais abaixo.

Uma empresa criada pelo self-service pode, mais tarde, "virar" uma página
fixa de verdade (como a Antoninho e a Haroke) se fizer sentido — nesse
caso, segue o processo em "Adicionando uma empresa nova" mais abaixo.

## Rodando localmente

Requer Python 3.10+ e o pacote `poppler-utils` do sistema (fornece o
comando `pdftotext`, usado para ler o PDF da APAE).

```bash
# Ubuntu/Debian
sudo apt-get install -y poppler-utils

pip install -r requirements.txt
streamlit run app.py
```

Abre em `http://localhost:8501`. As páginas aparecem no menu à esquerda.

## Publicando na nuvem (acessível de qualquer lugar)

A forma mais simples e gratuita é o **Streamlit Community Cloud**:

1. Suba esta pasta inteira para um repositório no GitHub (pode ser
   privado) — `app.py`, `pages/`, `core/` (com as subpastas
   `core/antoninho/` e `core/haroke/`), `requirements.txt`,
   `packages.txt` e os arquivos `antoninho_fornecedores_seed.json` e
   `haroke_overrides_seed.json`. **Atenção**: se você arrastar os
   arquivos pelo navegador em vez de usar `git push`, confira depois se
   as subpastas (`pages/`, `core/`, `core/antoninho/`, `core/haroke/`)
   foram mesmo criadas no GitHub — o upload por arrasta-e-solta às vezes
   larga tudo solto na raiz.
2. Entre em https://share.streamlit.io, conecte sua conta do GitHub e
   escolha o repositório e o arquivo `app.py` (o app principal —
   Streamlit descobre as páginas em `pages/` sozinho).
3. Clique em "Deploy". Em alguns minutos você recebe uma URL pública que
   qualquer pessoa autorizada pode acessar de qualquer lugar.

### Protegendo com senha

Por padrão o app fica aberto para quem tiver o link. Para exigir uma
senha simples (a mesma para todas as páginas/empresas):

- No Streamlit Community Cloud: **Settings → Secrets** do app:
  ```toml
  APP_PASSWORD = "escolha-uma-senha-aqui"
  ```
- Rodando localmente:
  ```bash
  export APP_PASSWORD="escolha-uma-senha-aqui"
  streamlit run app.py
  ```

Se `APP_PASSWORD` não estiver definida, o app fica sem tela de login
(útil para testar).

## Página: APAE São Sebastião do Paraiso

**Aba "Gerar TXT":**

1. Envie o PDF do relatório do mês (obrigatório) e o OFX do banco
   (opcional — sem ele, tudo fica pendente na conta suspensa).
2. Informe o ano.
3. Clique em **Processar arquivos** e confira o resumo — o app avisa se
   a quantidade de recibos ou a soma não baterem com os totais impressos
   no relatório.
4. Resolva **casos ambíguos** (PIX que bate nome+valor com mais de um
   doador) e classifique **PIX sem correspondência** (pendente, ou uma
   regra especial como "Ingressos Feijoada").
5. Confira os totais finais e baixe o `.txt`.

**Aba "⚙️ Configurações":** CNPJ, contas contábeis (doação PF/PJ,
suspensa, banco), histórico padrão, e as **regras especiais**
reutilizáveis (cadastre uma vez, aparece sempre como opção depois).

Regras de contabilização já validadas: doação com PIX confirmado ->
debita banco / credita 289 ou 765, na data do banco; sem confirmação ->
debita suspensa / credita 289 ou 765, na data do relatório; PIX sem
doação correspondente -> debita banco / credita suspensa (ou a regra
especial escolhida).

## Página: Antoninho Atacado e Varejo

**Aba "Gerar arquivos do mês":**

1. Informe o CNPJ e o período (`AAAAMM`, ex. `202608`) — transações fora
   desse mês nos extratos são ignoradas.
2. Envie os 3 extratos (Sicoob, Itaú, Banco do Brasil, todos `.ofx`) e o
   relatório "Contas a Pagar por Entrada" exportado em Excel. O Plano de
   Contas (Excel) é opcional — não é preciso para processar o mês.
3. Clique em **Processar**. O app classifica cada transação bancária
   automaticamente em uma de 8 categorias (PIX recebido, cartão/
   maquininha, tarifas, IOF, juros, BB Rende Fácil, pagamento a
   fornecedor, ou "demais movimentos") e casa cada pagamento de boleto
   com a parcela correspondente do Contas a Pagar para descobrir de qual
   fornecedor se trata.
4. Confira **"Fornecedores para revisar"**: são pagamentos cujo
   fornecedor não foi encontrado no cadastro (caem na conta 506
   "Fornecedores Diversos" por padrão). Se você enviou o Plano de Contas,
   o campo já vem preenchido com uma sugestão (achada por similaridade de
   nome, igual à Haroke) — confira antes de aplicar, principalmente as de
   confiança mais baixa. Informe a conta certa ali mesmo — isso já
   cadastra o fornecedor pelo ID para os próximos meses.
5. Baixe os dois arquivos: a **conciliação bancária** (tudo que foi
   identificado nos extratos) e as **pendências do Contas a Pagar**
   (parcelas que venceram no período mas não apareceram em nenhum
   extrato — ficam como pendência, na conta transitória "5", até
   aparecerem pagas num mês seguinte).

**Aba "📇 Cadastro de fornecedores":** lista e permite editar/adicionar
manualmente o vínculo `ID do fornecedor -> conta contábil`. Esse cadastro
foi reconstruído a partir dos arquivos reais de julho/2026 (258
fornecedores) e cresce sozinho conforme a aba de revisão vai sendo usada.

### Precisão e limitações conhecidas

O motor de classificação foi validado linha a linha contra os dois
arquivos de referência de julho/2026 já fechados (2.691 lançamentos
bancários e 182 pendências): reproduz o valor total exato e mais de 99%
das linhas de forma idêntica, incluindo a conta específica de cada
fornecedor. As poucas divergências restantes (cerca de 10-15 lançamentos
em ~15 fornecedores, de ~2.870 no total) acontecem quando o pagamento de
um boleto não bate com nenhuma parcela do Contas a Pagar enviado — nesse
caso o app não adivinha: lança na conta 506 e sinaliza na aba de revisão
para você confirmar a conta certa. Recomenda-se, como em qualquer mês
novo, conferir o resumo e a lista de revisão antes de importar os `.txt`
no sistema contábil — exatamente como já era feito manualmente.

## Página: Haroke Supermercado

**Aba "Gerar arquivo do mês":**

1. Informe o CNPJ e o período (`AAAAMM`, ex. `202608`) — transações fora
   desse mês nos extratos são ignoradas.
2. Envie os 2 extratos (Banco do Brasil e Sicoob, `.ofx`), o relatório
   de Contas a Pagar (Excel) e o Plano de Contas (Excel) do mês.
3. Clique em **Processar**. O app classifica cada transação bancária em
   uma de 12 categorias e casa cada pagamento com a parcela
   correspondente do Contas a Pagar; a conta do fornecedor é achada
   comparando o nome dele com os nomes do Plano de Contas (similaridade
   de texto), não por um cadastro de IDs como na Antoninho.
4. Confira **"Fornecedores para revisar"**: são parcelas cujo match de
   nome ficou com confiança abaixo de 95% — o app já mostra a conta
   sugerida e o score. Informe a conta certa ali mesmo — isso salva uma
   correção manual para os próximos meses.
5. Baixe o arquivo de conciliação bancária do mês.

**Aba "📇 Correções de fornecedor":** lista e permite editar/adicionar
manualmente as correções de nome que têm prioridade sobre a comparação
automática com o Plano de Contas — por exemplo quando a grafia no
Contas a Pagar diverge do plano, ou quando o fornecedor ainda não tem
conta própria (cai em 506, Fornecedores Diversos, até uma conta ser
criada).

### Precisão e limitações conhecidas

O motor de classificação foi validado linha a linha contra o arquivo de
referência de julho/2026 já fechado (945 lançamentos, R$ 445.357,46):
reprodução byte a byte, incluindo a ordem das linhas e a conta
encontrada para cada fornecedor. Como a conta do fornecedor aqui vem de
comparação de texto (em vez de um cadastro fixo de IDs como na
Antoninho), fornecedores com nomes muito parecidos no Plano de Contas
podem exigir uma correção manual ocasional — a aba de revisão sinaliza
exatamente esses casos antes de gerar o `.txt` definitivo.

## Página: Nova Empresa

Formulário para o próprio pessoal do departamento incluir uma empresa
nova, "copiando" as regras já validadas da Antoninho (fornecedor por
cadastro de ID, funciona com Sicoob/Itaú/BB em qualquer combinação) ou da
Haroke (fornecedor por nome contra um Plano de Contas, só Sicoob+BB).

1. Preenche nome, CNPJ, o modelo a copiar, quais bancos usa e a conta
   contábil de cada categoria do modelo escolhido (pode deixar em branco
   pra usar a mesma conta de exemplo do modelo).
2. No final, duas opções:
   - **🚀 Criar empresa agora** — self-service: a empresa fica pronta pra
     usar na hora, na página **🏢 Empresas** (ver abaixo), sem precisar
     falar comigo. Ela nasce marcada como **não verificada**.
   - **⬇️ Baixar pedido (.json)** — pra casos fora do padrão que o modo
     self-service não cobre (banco novo, regra especial tipo a da
     Antoninho na Haroke). Manda esse arquivo numa conversa com o Claude,
     de preferência junto com um mês já fechado de verdade dessa empresa,
     pra eu montar a lógica certa e revisar antes de qualquer arquivo
     contábil real sair dela.

### Como funciona o self-service por baixo dos panos

O motor genérico (`core/generic/engine.py`) **não reimplementa** a
classificação — ele roda a mesma função já validada da Antoninho ou da
Haroke (mesmos padrões de memo, mesma forma de casar fornecedor) e só
troca, no final, os números de conta genéricos do modelo pelos números
que a empresa nova de verdade usa. Isso mantém o motor "validado" intacto
e concentra o código novo numa camada fina de remapeamento — mas **não
substitui a verificação contra um mês fechado real**: uma empresa nova
sempre nasce com o cadastro de fornecedor vazio, então tudo cai em
revisão manual no primeiro mês, e continua marcada como "não verificada"
na tela até alguém confirmar que bateu.

## Página: Empresas

Onde as empresas criadas pela "Nova Empresa" (opção self-service) geram
o arquivo do mês — mesma ideia da Antoninho/Haroke (upload dos extratos e
do Contas a Pagar, resumo por regra, seção de fornecedores pra revisar,
download do `.txt`), só que numa página só, genérica, que lê a
configuração de cada empresa em vez de ter uma página fixa por empresa.

Mostra um aviso "⚠️ não verificada" até alguém marcar, no final da
página, que já conferiu um mês fechado de verdade contra o arquivo
gerado — recomendado antes de confiar 100% numa empresa nova.

As empresas ficam salvas em `empresas.json` (lista) e os cadastros/
correções de fornecedor de cada uma em `empresas_data/<slug>_*.json` —
mesma limitação de sempre: só ficam permanentes se forem baixados e
subidos pro GitHub (ver "Publicando na nuvem" mais acima).

## Adicionando uma empresa nova como página fixa (opcional)

Não é um passo obrigatório — uma empresa criada pelo self-service já
funciona direto na página **🏢 Empresas**. Vale a pena promovê-la a uma
página fixa (como a Antoninho e a Haroke) quando ela tiver uma regra
especial que o motor genérico não cobre, ou só por organização, depois
de já estar rodando há alguns meses sem problema.

1. Crie `pages/N_🏷️_NomeDaEmpresa.py` (o número define a ordem no menu).
2. Se a lógica de conciliação for parecida com a APAE (nome+valor) ou com
   a Antoninho (classificação de extrato + Contas a Pagar), reaproveite
   os módulos em `core/` ou `core/antoninho/`. Se for um leiaute ou tipo
   de dado bem diferente (ex. concilia PDF com Excel, ou usa outra chave
   de casamento), crie uma subpasta nova em `core/` para ela, seguindo o
   mesmo padrão: um módulo de leitura de cada arquivo de entrada, um de
   classificação/casamento, um de geração do `.txt`.
3. Chame `core.auth.require_password()` logo no topo da página nova.
4. Antes de publicar, reproduza um mês já fechado dessa empresa linha a
   linha (mesmo processo da Antoninho e da Haroke) — só shippar depois de
   bater 100% ou de entender e documentar cada divergência.

## Logo da contabilidade

O app mostra automaticamente um logo no topo do menu lateral (em todas as
páginas, inclusive na tela de login) se existir um arquivo
`assets/logo.png` (ou `.svg`, `.jpg`, `.jpeg`) na raiz do projeto — ver
`core/branding.py`. Sem esse arquivo, o app funciona normalmente, só sem
logo. Para ativar: coloque o arquivo do logo em `assets/logo.png` e suba
essa pasta pro GitHub junto com o resto.

## Estrutura do projeto

```
apae_app/
├── app.py                          # página inicial (login + menu)
├── requirements.txt
├── packages.txt                    # poppler-utils (para o PDF da APAE)
├── antoninho_fornecedores_seed.json  # cadastro inicial de fornecedores (Antoninho)
├── haroke_overrides_seed.json      # correções manuais iniciais de fornecedor (Haroke)
├── config.json                     # config da APAE (gerado automaticamente)
├── antoninho_fornecedores.json     # cadastro vivo de fornecedores (gerado automaticamente)
├── haroke_overrides.json           # correções vivas de fornecedor (gerado automaticamente)
├── empresas.json                   # empresas criadas via self-service (gerado automaticamente)
├── empresas_data/                  # cadastro/correções de cada empresa self-service (idem)
├── assets/
│   └── logo.png                    # logo da contabilidade (opcional — ver "Logo da contabilidade")
├── pages/
│   ├── 1_🏥_APAE.py
│   ├── 2_🏪_Antoninho.py
│   ├── 3_🛒_Haroke.py
│   ├── 4_🏗️_Nova_Empresa.py        # cria empresa (self-service) OU baixa pedido pra revisão
│   └── 5_🏢_Empresas.py            # gera arquivo do mês pras empresas self-service
└── core/
    ├── auth.py                     # tela de senha, compartilhada por todas as páginas
    ├── branding.py                 # logo no topo do menu lateral, se assets/logo.* existir
    ├── config.py                   # config da APAE
    ├── pdf_extract.py              # leitura do PDF de doações (APAE)
    ├── ofx_parse.py                # leitura do OFX de PIX recebidos (APAE)
    ├── matching.py                 # casamento nome+valor (APAE)
    ├── txt_generator.py            # geração do .txt final da APAE
    ├── common/
    │   ├── plano_de_contas.py      # leitura genérica de fornecedores no Plano de Contas
    │   │                           # (usada pela Antoninho e pela Haroke)
    │   └── templates.py            # descrição dos modelos "Antoninho"/"Haroke" usada na
    │                               # página Nova Empresa
    ├── generic/
    │   ├── empresas.py              # empresas.json: criar/listar/atualizar empresas self-service
    │   └── engine.py                # roda a classificação da Antoninho/Haroke sem alterar
    │                                # nada nela, e remapeia as contas pra empresa self-service
    ├── antoninho/
    │   ├── ofx_parse.py            # leitura genérica dos 3 extratos (todas as transações)
    │   ├── payables.py             # leitura do Contas a Pagar (Excel)
    │   ├── cadastro.py             # cadastro fornecedor -> conta contábil (por ID)
    │   ├── plano_de_contas.py      # reexporta core/common/plano_de_contas.py
    │   ├── matching.py             # sugestão de conta por similaridade de nome (opcional)
    │   ├── classify.py             # motor de classificação (12 regras)
    │   └── generate.py             # orquestra tudo e gera os 2 .txt
    └── haroke/
        ├── plano_de_contas.py      # reexporta core/common/plano_de_contas.py
        ├── cadastro.py             # correções manuais de fornecedor -> conta contábil
        ├── matching.py             # acha a conta do fornecedor por similaridade de nome
        ├── classify.py             # motor de classificação (12 regras)
        └── generate.py             # orquestra tudo e gera o .txt (reaproveita
                                     # core/antoninho/ofx_parse.py e payables.py)
```
