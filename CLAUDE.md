# CLAUDE.md — TI-Escolar

> Guia para o Claude Code (e para a equipe) sobre o que é este projeto, como ele é
> arquitetado e quais convenções seguir. Este documento é o **norte** do desenvolvimento.
> Onde algo ainda não existe no código, está marcado como **[Roadmap]**.

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
- Pais / responsáveis / alunos → interagem pelo WhatsApp (e pelo demo).
- Secretaria / coordenação da escola → cadastram conteúdo, disparam avisos. **[Roadmap: painel admin]**

**Front-ends:**
- O front-end inicial é um **demo em Next.js que simula a interface do WhatsApp**, usado para
  desenvolver e demonstrar o fluxo de conversa sem depender da homologação da Meta.
- A UI/integração de **chat real** do WhatsApp (inbound) fica para **[Roadmap]**. O **outbound**
  via Meta Cloud API já é considerado na arquitetura desde já.

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
5. **Administração** — **super admin** da plataforma (cross-tenant) e **admin por tenant** (escola),
   com autenticação e regras de permissão.
6. **Multi-tenant** — isolamento por escola em todas as funcionalidades.

---

## 3. Stack tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Back-end | **Python 3.12+**, **FastAPI** (async), **Pydantic v2** |
| Persistência | **PostgreSQL** + **pgvector**, **SQLAlchemy 2.0**, **Alembic** (migrations) |
| LLM | Porta `LLMProvider` (abstração **multi-provider**); adaptadores em infra (ex.: Anthropic Claude, OpenAI), selecionáveis por env |
| RAG / busca | Embeddings em **pgvector**; recuperação por similaridade |
| Front-end demo | **Next.js** (App Router) + **TypeScript** + **Tailwind**, simulando o WhatsApp; fala com o back-end via **REST/WebSocket** |
| Mensageria externa | **Meta WhatsApp Cloud API** (outbound) — adaptador em infra |
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
`mensagem recebida` → `interfaces` (DTO) → caso de uso `ReceberMensagemRecebida` →
`ResponderDuvida` (busca no `VectorStore` + `LLMProvider` para raciocinar/redigir) →
resposta com fonte → `MessageChannel` (demo agora).

---

## 5. Estrutura de diretórios (alvo) — **[Roadmap: scaffold]**

```
ti-escolar/
├── CLAUDE.md
├── docker-compose.yml
├── docs/
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── domain/          # entidades, value objects, portas
│       ├── application/      # casos de uso
│       ├── infrastructure/   # adaptadores: db, pgvector, llm, meta_api, mocks
│       └── interfaces/       # FastAPI: rotas REST/WS, webhooks, DTOs
└── web/                      # demo Next.js (simula o WhatsApp)
```

---

## 6. Modelo de dados (multi-tenant)

- **Isolamento por `tenant_id`** (escola) em todas as tabelas relevantes.
- Entidades principais: `Tenant` (escola), `Usuario` (admin), `Conversa`, `Mensagem`,
  `Documento`, `Conhecimento` (FAQ/aviso/procedimento), `MessageTemplate`, `Broadcast`/Campanha,
  `MessageQuota`, `Contato` (pai/responsável), `Grupo` + associação `grupo_contatos`.
- **Embeddings:** tabela `conhecimento` com coluna `vector` (pgvector) + metadados para RAG.
- Toda consulta deve ser **escopada por tenant**; nunca vazar dados entre escolas.

### 6a. Administração e grupos

- **`Usuario`** com `papel` ∈ {`super_admin`, `tenant_admin`}. O super admin tem `tenant_id = NULL`
  (cross-tenant); o admin de tenant é amarrado a uma escola. Senhas com **PBKDF2-SHA256**
  (`app/infrastructure/security.py`, somente stdlib).
- **Permissões** (`CriarUsuario`): só super admin cria super admin; admin de tenant só cria/lista
  dentro do próprio tenant. Acesso a grupos exige `_exige_acesso_tenant` (403 fora do tenant).
- **`Grupo`** (por tenant) agrega **`Contato`s** (N:N via `grupo_contatos`). `Contato` é único por
  `(tenant_id, telefone)`. `EnviarBroadcastParaGrupo` resolve os membros do grupo em destinatários
  e delega a `EnviarBroadcast` (template aprovado + cota + rate limit).
- **Seed** (`app/seed.py`) cria: super admin, admin do tenant demo, e grupos ("Turma 5º A",
  "Pais do Fundamental I") com contatos. Credenciais default em `.env.example`
  (`SUPER_ADMIN_*`, `DEMO_ADMIN_*`) — **trocar em produção**.
- **Rotas** em `app/interfaces/api/admin.py`: `/api/admin/login`, `/usuarios`, `/grupos`,
  `/grupos/{id}/contatos`, `/grupos/{id}/enviar`. Autenticação atual via cabeçalhos
  `X-User-Email`/`X-User-Senha` (**JWT/sessão = [Roadmap]**).

---

## 7. Camada de LLM

- Contrato único: porta **`LLMProvider`** no domínio (ex.: `gerar(prompt/messages, opções) -> resposta`).
- Adaptadores concretos ficam em **`infrastructure/`**; a **seleção do provedor/modelo é por
  variável de ambiente**. Nenhuma chamada a SDK de LLM fora da infraestrutura.
- O **"raciocínio" sobre a resposta** acontece no caso de uso de orquestração RAG
  (`ResponderDuvida`): recupera trechos relevantes, monta o contexto, chama o `LLMProvider` e
  retorna a resposta **com citação de fonte**.

---

## 8. Integrações de documentos

- Porta **`DocumentSource`** abstrai sistemas externos (sistema acadêmico, drive, etc.).
- Por enquanto, **adaptadores mock** em `infrastructure/` simulam a recuperação de documentos.
- **Para adicionar uma integração real:** implementar um novo adaptador de `DocumentSource` sem
  tocar em domínio/aplicação; registrar via injeção de dependência/config.

---

## 9. Canal de mensagens

A porta **`MessageChannel`** cobre **inbound** (receber/responder) e **outbound** (disparo ativo).

- **Agora:** adaptador do **demo Next.js** para o chat (inbound) via REST/WebSocket.
- **Agora também:** adaptador **Meta WhatsApp Cloud API** para **outbound** (ver §9a).
- **[Roadmap]:** UI/integração de **chat real** do WhatsApp para inbound (webhook da Meta).

### 9a. Mensagens ativas para pais (outbound via Meta Cloud API)

Disparo de notificações/avisos a pais/responsáveis. Pontos obrigatórios de projeto:

- **Templates (HSM):** mensagens enviadas **fora da janela de atendimento de 24h** exigem
  **template aprovado** pela Meta. Modelar `MessageTemplate` com **categoria** (utility / marketing /
  authentication) e status de aprovação; documentar o fluxo de submissão/aprovação.
- **Limites diários por tier:** a Meta limita o número de **destinatários únicos por 24h** por número
  de telefone, em tiers (**1K → 10K → 100K → ilimitado**), com escala automática conforme a
  **qualidade** do número. Modelar `MessageQuota` por **tenant/número**, contar destinatários e
  definir o comportamento ao **atingir o limite** (enfileirar para a próxima janela, recusar, alertar).
- **Rate limiting & fila:** porta **`RateLimiter`/`QuotaPolicy`** + **fila de envio** com
  **throttling**, **retry com backoff** e **agendamento** de broadcasts — para não estourar nem a
  **cota diária** nem a **taxa por segundo** da API.
- **Consentimento e status:** registrar **opt-in/opt-out**, respeitar a **janela de 24h**, e atualizar
  **status de entrega** (`sent` / `delivered` / `read` / `failed`) a partir dos **webhooks** da Meta.

---

## 10. Desenvolvimento com Docker — **[Roadmap: compose]**

Tudo roda sob Docker. Serviços previstos no `docker-compose.yml`:

- `db` — PostgreSQL + pgvector.
- `backend` — FastAPI.
- `web` — demo Next.js.

Comandos previstos (a definir no scaffold): `docker-compose up`, aplicação de **migrations**
(Alembic), **seed** de dados de demonstração e execução de **testes** (`pytest`).

---

## 11. Convenções

- **Python:** type hints obrigatórios; **ruff** + **black**; funções/casos de uso pequenos e testáveis.
- **Domínio em pt-BR** quando fizer sentido (nomes de entidades/casos de uso podem ser em português).
- **Respostas do bot:** sempre **pt-BR, formal-cordial / institucional**; citar fonte quando vier de RAG.
- **Dependências apontam para dentro:** domínio sem imports de framework; SDKs só em `infrastructure/`.
- **Multi-tenant first:** toda persistência e consulta escopada por `tenant_id`.
- **Testes:** pytest para domínio e casos de uso (com fakes/mocks das portas).
- **Segredos:** chaves de LLM e da Meta via variáveis de ambiente; nunca no código/repos.

---

## 12. Roadmap / Próximos passos

- [ ] Scaffold do back-end (camadas hexagonais, FastAPI, SQLAlchemy/Alembic, pgvector).
- [ ] Scaffold do demo Next.js (UI estilo WhatsApp + REST/WebSocket).
- [ ] `docker-compose.yml` com `db` / `backend` / `web` + migrations + seed.
- [ ] Adaptador **Meta WhatsApp Cloud API** (outbound) com templates, cota e fila.
- [ ] Inbound real do WhatsApp (webhook da Meta).
- [ ] Integrações reais de `DocumentSource` (substituir mocks).
- [x] Modelo de **administração** (super admin / admin de tenant) + **grupos de contatos**.
- [x] **Painel administrativo** (UI Next.js): login, gestão de grupos/contatos, barra de cota e
  disparo direcionado a grupo (`web/app/admin/`).
- [ ] **Autenticação JWT/sessão** (hoje credenciais ficam no `localStorage` via cabeçalhos) e
  endpoint para listar/gerenciar **templates** (o painel usa o template do seed).
