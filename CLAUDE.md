# CLAUDE.md — TI-Escolar

> Guia para o Claude Code (e para a equipe) sobre o que é este projeto, como ele é
> arquitetado e quais convenções seguir. Este documento é o **norte** do desenvolvimento.
> Onde algo ainda não existe no código, está marcado como **[Roadmap]**.

> **Este arquivo é o índice.** O guia detalhado mora em [`docs/guia/`](docs/guia/), um
> arquivo por assunto — ver o **[mapa do guia](#mapa-do-guia)**. Aqui ficam apenas a visão
> geral, a arquitetura, as convenções e os avisos que ninguém pode deixar de ler. **A
> numeração das seções foi preservada na mudança** (§6a, §9c, §12a…): as referências
> cruzadas espalhadas pelo código e pelos documentos continuam válidas — o mapa diz em
> qual arquivo cada uma está.

---

## 1. Visão geral

**TI-Escolar** é uma plataforma de comunicação escolar cujo principal canal com o usuário
final é o **WhatsApp**. Ela tem dois papéis complementares:

1. **Atendimento (inbound):** um **chatbot** que tira dúvidas gerais sobre procedimentos e
   avisos da escola e que **recupera e envia documentos** (boletins, declarações, calendários,
   circulares) integrando-se a sistemas externos.
2. **Comunicação ativa (outbound):** **disparo de mensagens e avisos a pais/responsáveis** via
   **Meta WhatsApp Cloud API**, usando **templates aprovados** e respeitando os **limites diários**
   impostos pela Meta.

O produto é **multi-tenant**: cada **escola é um tenant isolado**, com seus próprios avisos,
documentos, usuários, templates e cota de mensagens.

**Usuários:**
- Pais / responsáveis / alunos → interagem pelo **WhatsApp**.
- Secretaria / coordenação da escola → cadastram conteúdo, disparam avisos, pelo painel.

**Front-ends:**
- O **painel** (`web/`, Next.js) é a interface da escola: administração do tenant, portal do
  professor e super admin. É o único front do produto.
- Não há mais simulador de chat. Até o inbound real entrar no ar (10/ago/2026), a raiz `/`
  servia um **demo em Next.js que imitava a interface do WhatsApp**, atendido por rotas
  públicas `/api/chat/*`; com o canal da Meta atendendo de verdade ele deixou de ter função e
  foi removido — era a única superfície sem login que gravava conversa e consumia LLM. A raiz
  agora redireciona para `/admin`.

---

## 2. Funcionalidades-núcleo

1. **Dúvidas via RAG** — respostas sobre procedimentos/avisos com **busca vetorial** e **citação da
   fonte**, em **português (BR), tom formal-cordial / institucional**.
2. **Recuperação e envio de documentos** — via integrações com sistemas externos (porta de
   integração + adaptadores **mock** por enquanto).
3. **Disparo ativo (outbound) para pais** — notificações/avisos via **Meta Cloud API**, com
   **templates** e **controle de limites diários por tier**.
4. **Grupos de distribuição** — contatos (números de WhatsApp dos pais) organizados em **grupos**
   por escola; mensagens podem ser dirigidas **apenas aos membros de um grupo** (ex.: "Turma 5º A").
5. **Administração** — **super admin** da plataforma (cross-tenant), que faz **CRUD de escolas
   (tenants)** e acompanha **conversas e broadcasts** de cada escola; e **admin por tenant**
   (escola), com autenticação e regras de permissão.
6. **Cadastro escolar (pais e salas)** — o admin da escola cadastra **pais/responsáveis** (CRUD) e
   **salas/turmas** (ex.: "4ª série B"), vincula pais a salas (N:N) e extrai o **relatório de pais
   por sala**.
7. **Multi-tenant** — isolamento por escola em todas as funcionalidades.

---

## 3. Stack tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Back-end | **Python 3.12+**, **FastAPI** (async), **Pydantic v2** |
| Persistência | **PostgreSQL** + **pgvector**, **SQLAlchemy 2.0**, **Alembic** (migrations) |
| LLM | Porta `LLMProvider` (abstração **multi-provider**); adaptadores em infra (ex.: Anthropic Claude, OpenAI), selecionáveis por env |
| RAG / busca | Embeddings em **pgvector**; recuperação por similaridade |
| Front-end | **Next.js** (App Router) + **TypeScript** + **Tailwind** — painel admin e portal do professor; fala com o back-end via **REST** |
| Mensageria externa | **Meta WhatsApp Cloud API** (inbound + outbound) — adaptador em infra |
| Testes | **pytest** (back-end) |
| Orquestração | **Docker** + **docker-compose** |
| Qualidade | **ruff** + **black** (sugeridos), type hints obrigatórios |

> **Modelos LLM:** ao usar a API da Anthropic, prefira os modelos Claude mais recentes
> (ex.: Opus 4.8 / Sonnet 4.6 / Haiku 4.5). A escolha do provedor/modelo é configurável e nunca
> deve estar acoplada ao domínio.

---

## 4. Arquitetura — Clean / Hexagonal

O back-end segue **arquitetura limpa (hexagonal / ports & adapters)**. A **regra de dependência**
é absoluta: **o domínio não importa framework**; todas as dependências apontam para dentro.

```
            interfaces (FastAPI: REST / WebSocket / webhooks)
                              │  (DTOs)
                              ▼
            application (casos de uso — orquestram portas)
                              │  (usa portas/interfaces)
                              ▼
            domain (entidades, value objects, PORTAS)
                              ▲
                              │  (implementa portas)
            infrastructure (SQLAlchemy, pgvector, LLM, Meta API, mocks)
```

**Portas (interfaces no domínio):**
- `LLMProvider` — geração/raciocínio sobre respostas.
- `MessageChannel` — envio/recebimento de mensagens (**inbound + outbound**).
- `DocumentSource` — recuperação de documentos em sistemas externos.
- `KnowledgeRepository` / `VectorStore` — indexação e busca semântica.
- `RateLimiter` / `QuotaPolicy` — controle de taxa e cota diária de envio.

**Fluxo de uma dúvida (inbound):**
`webhook da Meta` → `interfaces` (assinatura validada) → `ProcessarInboundMeta` (roteia a
escola pelo `phone_number_id`) → `AtenderConversa` (**tool use**: o LLM decide entre buscar
no `VectorStore`, recuperar documento ou chamar a secretaria — §6j) → resposta com fonte →
`MessageChannel` (Meta, pelo número da própria escola). O contrato entre o transporte e o
atendimento é a porta `Atendedor`; **texto vazio significa não responder** (a conversa está
com uma pessoa).

---

## 5. Estrutura de diretórios (alvo) — **[Roadmap: scaffold]**

```
ti-escolar/
├── CLAUDE.md                  # este índice
├── docker-compose.yml
├── docs/
│   ├── guia/                  # o guia detalhado, um arquivo por assunto
│   └── *.md                   # operação: produção, rollback, backup, testes manuais
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── domain/          # entidades, value objects, portas
│       ├── application/      # casos de uso
│       ├── infrastructure/   # adaptadores: db, pgvector, llm, meta_api, mocks
│       └── interfaces/       # FastAPI: rotas REST/WS, webhooks, DTOs
├── web/                      # painel admin + portal do professor (Next.js)
└── site/                     # landing page institucional (tiescolar.com.br)
```

---

## Mapa do guia

Cada arquivo abaixo é a continuação deste documento — mesma voz, mesma numeração de seções,
e o **porquê** de cada decisão junto do que ela faz. Abra o que o assunto pedir; não é
preciso ler tudo.

| Arquivo | Seções | Abra quando precisar de… |
|---|---|---|
| [`docs/guia/metodo-de-trabalho.md`](docs/guia/metodo-de-trabalho.md) | §0 | **ler primeiro** — o que conta como progresso, ritual de abrir/fechar sessão, corte do beta, regras de escopo |
| [`docs/guia/modelo-de-dados.md`](docs/guia/modelo-de-dados.md) | §6 | entidades, isolamento por `tenant_id`, **cadeia de migrations** e suas armadilhas |
| [`docs/guia/administracao-e-acesso.md`](docs/guia/administracao-e-acesso.md) | §6a | `Usuario`, papéis × cargos, hierarquia, JWT, grupos, escola em foco do super admin |
| [`docs/guia/conhecimento-e-llm.md`](docs/guia/conhecimento-e-llm.md) | §6b, §7, §8 | base de conhecimento por escola (RAG), system prompt do tenant, porta `LLMProvider`, `DocumentSource` |
| [`docs/guia/cadastro-escolar.md`](docs/guia/cadastro-escolar.md) | §6c, §6c-bis, §6c-ter, §6c-quater, §6c-quinquies | turmas, alunos, responsáveis, professores, cobertura de contatos e importação em massa |
| [`docs/guia/escolas-e-licenciamento.md`](docs/guia/escolas-e-licenciamento.md) | §6d, §6e, §6f | CRUD de escolas (super admin), número/WABA da escola, licença, bloqueio, ficha financeira |
| [`docs/guia/comunicacao-interna.md`](docs/guia/comunicacao-interna.md) | §6g, §6h, §6i | respostas rápidas, avisos temporizados, fila de impressão, mural, canal professor↔escola, faltas, ficha de matrícula, matrícula self-service |
| [`docs/guia/atendimento-humano.md`](docs/guia/atendimento-humano.md) | §6j, §6l | quando o assistente entrega a conversa à secretaria, expediente, janela de 24h, saída antecipada |
| [`docs/guia/documentos-recebidos.md`](docs/guia/documentos-recebidos.md) | §6k, §6k.1, §6k.2 | arquivos que o responsável manda pelo WhatsApp, retenção/LGPD, leitura por IA, anti-spam |
| [`docs/guia/canal-whatsapp.md`](docs/guia/canal-whatsapp.md) | §9, §9b, §9c, §9e | adaptador da Meta, webhook e assinatura, inbound real, multi-tenant de envio, onboarding de número |
| [`docs/guia/templates-e-disparo.md`](docs/guia/templates-e-disparo.md) | §9a, §9a-bis, §9a-ter, §9a-quater, §9a-quinquies | templates (HSM), catálogo e submissão à Meta, várias WABAs, cota diária, retomada do disparo, erro de envio |
| [`docs/guia/landing-page.md`](docs/guia/landing-page.md) | §9d | o site institucional `site/` e seu deploy na Cloudflare Pages |
| [`docs/guia/observabilidade.md`](docs/guia/observabilidade.md) | §13, §16, §16a | histórico de conversas/disparos, auditoria de ações, painel de logs, notificações do painel |
| [`docs/guia/seguranca-e-lgpd.md`](docs/guia/seguranca-e-lgpd.md) | §14, §15, §17 | postura de segurança do super admin, checklist de pré-deploy, auditoria LGPD contínua |
| [`docs/guia/roadmap.md`](docs/guia/roadmap.md) | §12, §12a | o que está feito, o que falta e em que ordem |

**Fora do guia** — o que não descreve o produto, mas o trabalho em volta dele:

| Arquivo | Abra quando… |
|---|---|
| [`LOG.md`](LOG.md) | abrir ou fechar sessão — quatro linhas por sessão, é o que faz o §0 funcionar |
| [`docs/pendencias-externas.md`](docs/pendencias-externas.md) | **algo estiver travado e não for código** — segredo, credencial, cartão, chip, clique no painel de um provedor |
| [`docs/pipelines.md`](docs/pipelines.md) | mexer nas esteiras de deploy por branch *(chega com o PR #87)* |
| [`docs/producao-fly.md`](docs/producao-fly.md) | deploy, segredos, DNS, rollback e custo do back-end de produção |
| [`docs/producao-whatsapp.md`](docs/producao-whatsapp.md) | go-live do canal na Meta |
| [`docs/plano-correcoes-teste-10-08.md`](docs/plano-correcoes-teste-10-08.md) | os apontamentos do teste de 10/ago e a Fase 0 (arquivos no S3) |
| [`docs/checklist-teste-manual.md`](docs/checklist-teste-manual.md) | testar o produto inteiro na mão |
| [`docs/runbook-rollback.md`](docs/runbook-rollback.md) · [`docs/backup.md`](docs/backup.md) | algo der errado depois de publicar |
**Operação** (fora do guia, em `docs/`): [`pipelines.md`](docs/pipelines.md) (as esteiras
de homolog e produção, e o modelo de branches), [`producao-fly.md`](docs/producao-fly.md)
(o back-end de produção na Fly), [`producao-whatsapp.md`](docs/producao-whatsapp.md)
(go-live do canal), [`runbook-rollback.md`](docs/runbook-rollback.md),
[`backup.md`](docs/backup.md), [`checklist-teste-manual.md`](docs/checklist-teste-manual.md).

> **Ao mexer no guia:** mantenha a numeração das seções e atualize a linha correspondente
> deste mapa. Seção nova entra no arquivo do assunto — não neste índice.

---

## Avisos que não podem se perder

O detalhe de cada um está na seção indicada; ficam aqui porque o custo de descobri-los
tarde já foi pago uma vez.
- **Antes de codar, abra o §0.** Uma sessão começa com recapitulação, **um** fluxo do corte
  do beta e escopo acordado; termina com registro em `LOG.md`. Progresso é fluxo funcionando
  ponta a ponta na escola — não commit, feature ou refactor. (§0)
- **Multi-tenant é invariante, não recurso:** toda consulta escopada por `tenant_id`; nunca
  vazar dados entre escolas. (§6)
- **Migrations em cadeia linear.** `down_revision` = head atual; o CI recusa mais de um head,
  e o deploy roda `alembic upgrade head` no `CMD` — head duplicado é **container que não
  sobe**. O id da revisão cabe em **32 caracteres**, e estourar só falha na hora de aplicar.
  **Merge verde não é prova de que o código está na `main`** — confira o `baseRefName` quando
  o PR sair de uma branch que não é a `main`. (§6)
- **`MESSAGE_CHANNEL=meta` sem `META_ACCESS_TOKEN` cai no canal demo em silêncio:** o processo
  sobe, o WhatsApp não está no ar e nada acusa erro. `canal_efetivo(settings)` é a fonte única
  de qual adaptador está em uso. (§9c)
- **A Meta aceita UMA URL de webhook por app.** Não há webhook "de teste" e "de produção" —
  há *o* webhook. Desde 29/ago/2026 ele aponta para a **produção**
  (`https://api.tiescolar.com.br/api/webhook/meta`, com o `/api`), e por isso o **homolog
  está em `MESSAGE_CHANNEL=demo`**: manter os dois ligados é impossível, e um homolog em
  `meta` ainda dispararia WhatsApp real a partir de dado de teste. Ligar o canal num
  ambiente é desligá-lo no outro. (§9c, [`docs/producao-whatsapp.md`](docs/producao-whatsapp.md) §11)
- **Nenhum dos dois back-ends publica sozinho:** mergear na `main` não sobe a API. No
  **homolog** (Render) é *Manual Deploy → Deploy latest commit*; na **produção**
  (Fly.io, app `ti-escolar`) é `cd backend && fly deploy`. (§12a,
  [`docs/producao-fly.md`](docs/producao-fly.md))
  > A esteira que conserta isso está no **PR #87** (`feat/pipelines-homolog-producao`) e
  > **ainda não foi mergeada** — e, mesmo depois do merge, ela **pula o deploy** enquanto os
  > segredos que só o Luiz cadastra não existirem. Até lá o aviso acima continua valendo.
  > ([`docs/pendencias-externas.md`](docs/pendencias-externas.md) §1)
- **Travou e não é código? Não improvise:** segredo, credencial da AWS, cartão na Meta, chip,
  branch no painel do Render — está tudo em
  [`docs/pendencias-externas.md`](docs/pendencias-externas.md), com o **como conferir que
  caiu** de cada um. Item novo desse tipo entra lá, não no roadmap.
- **A branch é o ambiente:** `develop` publica no **homolog** (Render + Vercel) e `main`
  publica na **produção** (Fly.io + Cloudflare Pages), pelas esteiras `deploy-homolog.yml`
  e `deploy-producao.yml`. Trabalho novo sai da `develop`; produção é um PR
  `develop → main`. Até 02/set/2026 nenhum dos dois back-ends publicava sozinho — se algum
  documento ainda mandar abrir o painel do Render ou rodar `fly deploy` na mão, é resquício
  disso (os comandos seguem valendo como rollback). (§12a,
  [`docs/pipelines.md`](docs/pipelines.md))
- **Deploy verde não é prova de deploy feito:** o `/health` responde `ok` na versão velha
  também. Quem distingue é o campo `versao` (o commit da imagem), que a esteira compara com
  o que acabou de publicar. Ao mexer no `Dockerfile` ou no `/health`, esse campo tem de
  continuar chegando — sem ele a esteira volta a jurar que publicou. (§12a)
- **Produção não semeia, mas agora provisiona.** `app.seed` é proibido em `APP_ENV=production`
  e continua sendo; o que existe para pôr **uma** escola de pé num banco real é
  `python -m app.provisionar` — tenant, admin (senha do ambiente), conta e conhecimento
  opcional, **sem** aluno/responsável/ficha fictícios. (§10,
  [`docs/producao-whatsapp.md`](docs/producao-whatsapp.md) §11.3)
- **A chave do arquivo carrega a finalidade:** `{finalidade}/{tenant}/…`, porque o lifecycle
  do bucket apaga por **prefixo**. `doc/` compartilhado entre documento e impressão fazia a
  regra de 395 dias levar junto arquivo de professor que não tem `expira_em` nem expurgo — a
  linha sobrevive apontando para objeto que não existe, e o download vira 404. **Descartar
  apaga os bytes na hora** e reduz o registro ao que o anti-spam precisa. (§6k)
- **O dado mais sensível da base é documento de menor** (atestado, laudo, `cor_raca`, NIS):
  nenhuma URL pública, download auditado, prazo de retenção com expurgo. (§6k, §17)

---

## 10. Desenvolvimento com Docker — **[Roadmap: compose]**

Tudo roda sob Docker. Serviços previstos no `docker-compose.yml`:

- `db` — PostgreSQL + pgvector.
- `backend` — FastAPI.
- `web` — painel Next.js.

Comandos previstos (a definir no scaffold): `docker-compose up`, aplicação de **migrations**
(Alembic), **seed** de dados de demonstração e execução de **testes** (`pytest`).

> **Provisionamento × seed.** O `CMD` do container roda `alembic upgrade head` e
> `python -m app.bootstrap` — este último cria **apenas o super admin**, é idempotente (não
> sobrescreve senha de quem já existe) e recusa a senha de exemplo em produção. O **seed de
> demonstração** (`python -m app.seed`) só roda com `SEED_DEMO=true` e **nunca** com
> `APP_ENV=production`; fora de desenvolvimento ainda exige que as senhas tenham valor próprio.
> Até 29/jul/2026 o seed rodava no `CMD`, ou seja, **em produção a cada deploy**: despejava a
> escola-demo e logins com senha versionada no repositório dentro do banco real. Política em
> `app/bootstrap.py::avaliar_seed`.

---

## 11. Convenções

- **Python:** type hints obrigatórios; **ruff** + **black**; funções/casos de uso pequenos e testáveis.
- **Domínio em pt-BR** quando fizer sentido (nomes de entidades/casos de uso podem ser em português).
- **Respostas do bot:** sempre **pt-BR, formal-cordial / institucional**; citar fonte quando vier de RAG.
- **Dependências apontam para dentro:** domínio sem imports de framework; SDKs só em `infrastructure/`.
- **Multi-tenant first:** toda persistência e consulta escopada por `tenant_id`.
- **Testes:** pytest para domínio e casos de uso (com fakes/mocks das portas).
- **Segredos:** chaves de LLM e da Meta via variáveis de ambiente; nunca no código/repos.
- **Documentação:** este arquivo é o índice; o detalhe vai para o arquivo de assunto em
  `docs/guia/` (ver o [mapa](#mapa-do-guia)). Mantenha o CLAUDE.md enxuto — ele é carregado
  em toda sessão. 
- **Método antes de produto:** o §0 ([`metodo-de-trabalho.md`](docs/guia/metodo-de-trabalho.md))
  governa como as sessões acontecem e prevalece sobre impulso de escopo. Arquitetura e
  invariantes (§4, §6, §11) não são objeto de corte — só features são.
<critical>- **Branches:** Toda vez que solicitado uma alteração ou adição de nova feature você deve sincronizar a main com origin remote e abrir uma nova branch a partir da main com prefixo fix ou feat conforme o entendimento que você tem sobre a task a ser executada. Exemplo: fix/(nome da funcionalidade a ser corrigida) ou feat/(nome da funcionalidade)</critical>
  em toda sessão.
<critical>- **Branches:** Toda vez que solicitado uma alteração ou adição de nova feature você deve sincronizar a `develop` com o origin remote e abrir uma nova branch **a partir da `develop`** com prefixo fix ou feat conforme o entendimento que você tem sobre a task a ser executada. Exemplo: fix/(nome da funcionalidade a ser corrigida) ou feat/(nome da funcionalidade). O PR da feature aponta para a `develop` (homolog); a produção é um PR separado `develop → main` (ver [`docs/pipelines.md`](docs/pipelines.md)).</critical>
