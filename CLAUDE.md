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
  `MessageQuota`, `Contato` (pai/responsável), `Grupo` + associação `grupo_contatos`,
  `Sala` (turma) + associação `sala_contatos`, `FonteConhecimento` (documento da escola),
  `PromptTenant` (system prompt da escola) e `ResumoEscola` (visão agregada do super admin).
- **Embeddings:** tabela `conhecimento` com coluna `vector` (pgvector) + metadados para RAG;
  `fonte_id` liga cada trecho à `FonteConhecimento` que o originou.
- **Migrations:** `0001_initial` → `0002_admins_grupos` → `0003_salas` →
  `0004_conhecimento_prompt` → `0005_alunos` → `0006_licenciamento_tenant` →
  `0006_destinatario_entrega` → `0007_ficha_financeira_tenant`. **Cadeia linear obrigatória:**
  ao criar uma migration, encadeie no head atual (`down_revision` = último head) para evitar
  **multiple heads** no `alembic upgrade head` do deploy.
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
  `/grupos/{id}/contatos`, `/grupos/{id}/enviar`. **Autenticação por JWT (HS256):** o
  `POST /api/admin/login` devolve `{ access_token, expira_em, usuario }`; as demais rotas
  exigem `Authorization: Bearer <token>`. O token é assinado com `JWT_SECRET` e expira
  conforme `JWT_EXPIRA_MINUTOS` (default 480 min). A dependência `usuario_autenticado`
  decodifica o token (`app/infrastructure/security.py`, só stdlib) e **revalida o usuário
  no banco** (existência + `ativo`) a cada requisição. O painel guarda o token no
  `localStorage` (`web/lib/admin.ts`) e o reenvia no cabeçalho `Authorization`.

---

### 6b. Base de conhecimento por tenant e system prompt da escola

- **Documentos da escola (RAG):** o admin sobe textos/arquivos de procedimentos
  (`FonteConhecimento`); o caso de uso `IngerirDocumento` fragmenta o conteúdo
  (`fragmentar`), gera embeddings e indexa cada trecho no `VectorStore` com `fonte_id`
  apontando para a fonte. Isso enriquece o contexto da LLM **apenas daquele tenant**.
  Gestão (listar/remover) via `app/interfaces/api/conhecimento.py`
  (`/api/admin/conhecimento`); remover uma fonte apaga seus trechos indexados.
- **System prompt do tenant (`PromptTenant`):** um "CLAUDE.md" por escola, editável no
  painel (`/api/admin/prompt`). É anexado às diretrizes-base do assistente
  (`montar_sistema` / `montar_sistema_agente`) e tem **prioridade institucional**.
  `ResponderDuvida` e `AtenderConversa` recebem um `PromptTenantRepository` opcional e
  injetam o texto da escola no prompt de sistema.
- **Painel:** páginas `web/app/admin/conhecimento/` (upload/lista) e `web/app/admin/prompt/`
  (editor das instruções). O upload lê o arquivo no navegador e envia o texto via JSON
  (sem multipart no servidor).

### 6c. Salas (turmas), pais/responsáveis e relatório

- **`Sala`** (turma, ex.: "4ª série B") por tenant, única por `(tenant_id, nome)`. Agrega
  **`Contato`s** (pais/responsáveis) em **N:N** via `sala_contatos` — um responsável pode estar em
  mais de uma sala. Casos de uso em `app/application/cadastro_use_cases.py`.
- **CRUD completo** de pais e de salas, vínculo/desvínculo pai↔sala e **relatório de pais por
  sala** (`RelatorioPaisDaSala`). `Contato` continua único por `(tenant_id, telefone)`.
- **Rotas** em `app/interfaces/api/cadastro.py` (prefixo `/api/admin`, reaproveitando
  `usuario_autenticado` e `_exige_acesso_tenant`): `pais` (POST/GET/PUT/DELETE),
  `salas` (POST/GET/PUT/DELETE), `salas/{id}/pais` (GET relatório · POST vincular) e
  `salas/{id}/pais/{contato_id}` (DELETE desvincular).
- **Painel:** `web/app/admin/salas/` — CRUD de salas e pais, vínculo e **relatório imprimível**
  (PDF). O seed cria salas demo ("4ª série B", "5ª série A") com responsáveis vinculados.

### 6c-bis. Alunos (CRUD)

- **`Aluno`** por tenant, com **série 1:1 obrigatória** (`sala_id` → `Sala`, FK restritiva) e
  **responsáveis N:N** (`Contato`s via `aluno_responsaveis`, `ON DELETE CASCADE`). Campos: `nome`,
  `matricula` (opcional), `ativo` (marca **ex-aluno** — base da futura transferência/promoção de
  série). `sala_nome` é denormalizado só para exibição.
- **CRUD completo** + vínculo/desvínculo de responsáveis e filtro por série. Casos de uso em
  `app/application/cadastro_use_cases.py` (`CadastrarAluno`, `ListarAlunos`, `ObterAluno`,
  `AtualizarAluno`, `RemoverAluno`, `VincularResponsavelAoAluno`, `DesvincularResponsavelDoAluno`);
  a série informada é validada como pertencente ao tenant. Repositório `SqlAlunoRepository`.
- **Exclusão de série com alunos:** como `sala_id` é obrigatório, `RemoverSala` exige uma
  estratégia: sem `mover_para` **exclui** os alunos junto com a série; com `mover_para=<sala_id>`
  **transfere** os alunos para outra série (validada no tenant, diferente da removida) antes de
  apagar a original. No painel, o diálogo de exclusão oferece as duas opções e permite **criar a
  série destino** na hora (reusando `POST /salas`).
- **Rotas** em `app/interfaces/api/cadastro.py`: `alunos` (POST · GET `tenant/{tenant_id}` com
  `?sala_id=` opcional), `alunos/{id}` (GET/PUT/DELETE), `alunos/{id}/responsaveis`
  (POST vincular · DELETE `/{contato_id}` desvincular) e `DELETE /salas/{id}?mover_para=` para a
  exclusão de série com transferência.
- **Painel:** `web/app/admin/alunos/` — cadastro, edição (série + situação ativo/ex-aluno),
  gestão de responsáveis e filtro por série. O seed cria um aluno por sala demo.
- A remoção de tenant (`SqlTenantRepository.remover`) apaga `aluno_responsaveis` → `alunos` na
  cascata explícita.

### 6c-ter. Cobertura de contatos da turma (alerta + aviso ao professor)

- **Cobertura:** uma turma (`Sala`) informa quantos **alunos ativos** estão **sem nenhum
  responsável (`Contato`) com telefone** vinculado — `Aluno.tem_contato` é falso quando nenhum
  responsável tem telefone preenchido. Ex-alunos (`ativo=False`) são ignorados. O value object
  `CoberturaContatosSala` (`total_alunos`, `alunos_sem_contato`, `total_sem_contato`) consolida o
  alerta "X alunos na turma, Y sem contato de responsável".
- **Casos de uso** em `app/application/cadastro_use_cases.py`: `CoberturaDeContatosDaSala` (uma
  turma, com a lista de alunos descobertos), `ResumoCoberturaDasSalas` (todas as turmas do tenant,
  carregando os alunos uma vez para evitar N+1) e `NotificarProfessorContatosFaltantes`, que envia
  um **texto livre pelo `MessageChannel`** ao WhatsApp do professor listando os faltantes (falha se
  não há nenhum). **Dor de campo:** hoje pedem ao professor para coletar os contatos e ele esquece.
- **Rotas** em `app/interfaces/api/cadastro.py`: `GET /salas/tenant/{tenant_id}/cobertura`
  (resumo de todas), `GET /salas/{id}/cobertura?tenant_id=` (detalhe) e
  `POST /salas/{id}/notificar-professor` (corpo: `telefone`, `mensagem` opcional).
- **Painel:** `web/app/admin/salas/` — badge ⚠ na lista de turmas e, no detalhe da turma, um alerta
  com os alunos sem contato e o botão **"Notificar professor"** (modal pedindo o WhatsApp do
  professor + mensagem opcional). O seed cria um "Aluno Sem Contato" na primeira turma demo.

### 6d. Gestão de escolas (super admin)

- **CRUD de escolas (`Tenant`):** apenas o **super admin** cria/edita/remove escolas
  (`app/application/tenant_use_cases.py`: `CriarEscola`, `ListarEscolas`, `ObterEscola`,
  `AtualizarEscola`, `RemoverEscola`). `Tenant` é único por `slug`. A **remoção é em cascata
  explícita** (`SqlTenantRepository.remover` apaga, na mesma transação, mensagens → conversas →
  conhecimento → broadcasts → grupos/contatos → usuários → tenant, pois as FKs não têm
  `ON DELETE CASCADE`).
- **Visão cross-tenant:** `ListarEscolas` devolve `ResumoEscola` (totais de conversas, contatos e
  broadcasts por escola); o super admin também inspeciona **conversas + mensagens**
  (`ObterConversaDaEscola`) e **broadcasts** de cada escola.
- **Rotas** em `app/interfaces/api/admin.py` (guard `_exige_super_admin`): `/api/admin/escolas`
  (POST/GET), `/escolas/{tenant_id}` (GET/PUT/DELETE), `/escolas/{tenant_id}/conversas`,
  `/escolas/{tenant_id}/conversas/{conversa_id}` e `/escolas/{tenant_id}/broadcasts`.
- **Painel:** `web/app/admin/escolas/` (lista + detalhe por `[tenantId]`).

### 6e. Licenciamento, cobrança e bloqueio (super admin)

- **Estado no `Tenant`:** `status` ∈ {`ativo`, `bloqueado`, `cancelado`} + `motivo_bloqueio`/
  `bloqueado_em` e `motivo_cancelamento`/`cancelado_em`; a licença `plano` ∈ {`mensal`, `anual`}
  + `licenca_expira_em`; e a cobrança `valor_mensal_centavos`/`valor_anual_centavos`. Propriedades
  de domínio: `bloqueado`, `cancelado`, `acesso_suspenso`, `motivo_suspensao`, `mrr_centavos`,
  `arr_centavos`, `dias_para_expirar`, `licenca_expirada`, `licenca_a_vencer(dias_aviso)`.
  Migrations `0006_licenciamento_tenant` e `0007_ficha_financeira_tenant`.
- **Bloqueio e cancelamento:** `BloquearEscola`/`DesbloquearEscola` (suspensão reversível) e
  `CancelarEscola`/`ReativarEscola` (churn, com `motivo_cancelamento`/`cancelado_em`), em
  `app/application/tenant_use_cases.py`, só super admin. Tanto a escola **bloqueada** quanto a
  **cancelada** (`acesso_suspenso`) perdem acesso ao painel (`POST /login` recusa o
  `tenant_admin` com 403 + motivo) **e aos disparos** (guard `_exige_tenant_ativo` em
  `/grupos/{id}/enviar` e em `POST /api/broadcasts`). O super admin segue entrando.
- **Licença e preços:** `DefinirLicenca` ajusta plano, data de expiração e (opcionalmente) os
  preços por ciclo (`valor_*_centavos`; só altera quando informados). O contador "quanto falta
  para expirar" é `dias_para_expirar` (exposto em `LicencaSaida`).
- **Aviso por e-mail:** `NotificarLicencasAVencer` avisa os `tenant_admin` das escolas com
  **plano anual** dentro da janela `LICENSE_WARNING_DAYS` (default 30) do vencimento. Porta
  `EmailSender` no domínio; adaptador atual `LogEmailSender` (mock/log,
  `app/infrastructure/messaging/email.py`). Disparável pelo super admin via
  `POST /api/admin/licencas/notificar-vencimento` (ou por um job agendado).
- **Rotas** (super admin, `app/interfaces/api/admin.py`): `/escolas/{tenant_id}/bloquear`,
  `/escolas/{tenant_id}/desbloquear`, `/escolas/{tenant_id}/cancelar`,
  `/escolas/{tenant_id}/reativar`, `PUT /escolas/{tenant_id}/licenca` e
  `/licencas/notificar-vencimento`.
- **Painel:** `web/app/admin/escolas/` (badge de status/expiração, modais de bloqueio, cancelamento
  e licença — esta com os preços por ciclo —, botão "Avisar vencimentos") e o detalhe `[tenantId]`
  (faixa de licença). Badge reutilizável em `web/components/admin/LicencaBadge.tsx`. Login
  bloqueado/cancelado mostra o motivo.

### 6f. Ficha financeira / histórico da escola (super admin)

- **Visão derivada (sem ledger de faturas):** `ObterFichaFinanceira`
  (`app/application/tenant_use_cases.py`, só super admin) monta o value object
  `FichaFinanceiraEscola` a partir do `Tenant` + `MetricasUsoEscola` (contadores via
  `TenantRepository.metricas_uso`) + a cota diária Meta (`META_DAILY_TIER_LIMIT`). Consolida:
  **ciclo de vida** (`criado_em` = data de início, `dias_de_casa`, `cancelado_em`/motivo),
  **cobrança** (preços, `mrr_centavos`/`arr_centavos`, `receita_acumulada_centavos` = LTV estimado
  por `meses_ativos × MRR`, `status_pagamento` derivado da licença), **próxima renovação**
  (`licenca_expira_em`), **uso** (usuários ativos, contatos, alunos, conversas, broadcasts) e um
  **`health_score`** heurístico (licença + bloqueio + tier de envio).
- **Endpoint:** `GET /api/admin/escolas/{tenant_id}/ficha-financeira` (`FichaFinanceiraSaida`).
- **Painel:** card "Ficha financeira" no detalhe `web/app/admin/escolas/[tenantId]/` (métricas de
  cobrança, uso e saúde); preços editáveis no modal de licença da lista `web/app/admin/escolas/`.

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

### 9b. Confirmação de recebimento (não-entrega reativa)

Análogo à "confirmação de recebimento" de e-mail: depois de um broadcast, aponta quais
responsáveis **provavelmente não receberam** o aviso, para que o admin possa agir (pode ser algo
crítico que passou despercebido).

- **Correlação webhook ↔ destinatário:** ao enviar, `EnviarBroadcast` guarda o **id externo da
  Meta** (`wamid`) em `DestinatarioBroadcast.mensagem_id_externo` e o `atualizado_em`. O webhook
  (`POST /api/webhook/meta`) chama `RegistrarStatusEntrega`, que percorre os `statuses` do payload
  e atualiza o status do destinatário pelo `wamid` (`StatusEntrega` casa diretamente com
  `sent`/`delivered`/`read`/`failed`). Persistência em `destinatarios_broadcast` (migration
  `0006_destinatario_entrega`).
- **Detecção reativa:** `VerificarRecebimentoBroadcast` (recebe `BroadcastRepository` +
  `ContatoRepository`) sinaliza, **escopado por tenant**: destinatários em `FALHOU` (imediato) e
  em `ENVIADO` sem confirmação (`delivered`/`read`) há mais de `apos_minutos` (default 60).
  `ENTREGUE`/`LIDO` confirmam recebimento; `PENDENTE`/`ENFILEIRADO` (bloqueados por cota) ficam de
  fora. Resolve o **nome do responsável** via `Contato.por_telefone`.
- **Endpoint:** `GET /api/admin/escolas/{tenant_id}/broadcasts/{broadcast_id}/nao-entregues`
  (`?apos_minutos=`), guardado por `_exige_acesso_tenant`. O **painel** depende do histórico de
  broadcasts no admin da escola — ver §12a (**[Roadmap]**).

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
<critical>- **Branches:** Toda vez que solicitado uma alteração ou adição de nova feature você deve sincronizar a main com origin remote e abrir uma nova branch a partir da main com prefixo fix ou feat conforme o entendimento que você tem sobre a task a ser executada. Exemplo: fix/(nome da funcionalidade a ser corrigida) ou feat/(nome da funcionalidade)</critical>

---

## 12. Roadmap / Próximos passos

- [ ] Scaffold do back-end (camadas hexagonais, FastAPI, SQLAlchemy/Alembic, pgvector).
- [ ] Scaffold do demo Next.js (UI estilo WhatsApp + REST/WebSocket).
- [ ] `docker-compose.yml` com `db` / `backend` / `web` + migrations + seed.
- [ ] Adaptador **Meta WhatsApp Cloud API** (outbound) com templates, cota e fila.
- [ ] Inbound real do WhatsApp (webhook da Meta).
- [ ] Integrações reais de `DocumentSource` (substituir mocks).
- [x] **Base de conhecimento por tenant** (upload de documentos → RAG) e **system prompt
  personalizado por escola** (um "CLAUDE.md" do tenant), com painel em `web/app/admin/`.
- [x] **Cadastro escolar:** CRUD de **pais/responsáveis** e **salas (turmas)**, vínculo N:N e
  **relatório de pais por sala** (`app/interfaces/api/cadastro.py`, `web/app/admin/salas/`).
- [x] **Gestão de escolas pelo super admin:** CRUD de tenants + visão de **conversas e broadcasts**
  por escola (`app/application/tenant_use_cases.py`, `web/app/admin/escolas/`).
- [x] Modelo de **administração** (super admin / admin de tenant) + **grupos de contatos**.
- [x] **Painel administrativo** (UI Next.js): login, gestão de grupos/contatos, barra de cota e
  disparo direcionado a grupo (`web/app/admin/`).
- [x] **Autenticação JWT/sessão:** `POST /api/admin/login` emite um JWT (HS256, stdlib) e as
  rotas admin exigem `Authorization: Bearer`; o painel guarda o token (não a senha) no
  `localStorage`. Ver §6a.
- [ ] Endpoint para listar/gerenciar **templates** (o painel ainda usa o template do seed).
- [ ] **Transferência de responsáveis** Ser possível que os pais de alunos sejam transferidos para a série seguinte ou fiquem inativos caso estejam na última série disponível. Apenas tornar responsáveis inativos se todos os alunos deste responsável já são ex-alunos.
- [x] **CRUD de Alunos** Aluno por tenant com **série 1:1** (`sala_id`) e **responsáveis N:N**
  (`aluno_responsaveis`), com `ativo` para marcar ex-aluno. Ver §6c-bis
  (`app/interfaces/api/cadastro.py`, `web/app/admin/alunos/`).

### 12a. Backlog priorizado (novas tasks)

**Infra / deploy**
- [x] **Deploy automatizado do Render**: o deploy é feito nativamente pelo **Render**
  (Auto-Deploy ligado no push à `main`). O CI (`.github/workflows/ci.yml`) roda
  **lint (ruff) + migrations (alembic upgrade head) + pytest** em PRs e na `main`, servindo de
  portão de qualidade antes do merge.

**Observabilidade / histórico**
- [ ] **Histórico completo de mensagens em massa (broadcasts)** enviadas no admin da escola —
  listar disparos com template, grupo/destinatários, status de entrega e data.
- [ ] **Histórico completo de conversas do WhatsApp** (mensagens recebidas e enviadas pela LLM),
  consultável no admin da escola.
- [ ] **Log de auditoria de ações** — gravar ações feitas por **usuários logados** no admin da
  escola **e** ações da **LLM** (quem, o quê, quando, payload relevante). Base para
  rastreabilidade/compliance.

**Limpeza de UI (remoções)**
- [ ] **Remover** a emissão de relatórios em **lista** de pais na seção "Salas e pais"
  (não faz sentido manter).
- [ ] **Remover** o dropdown de seleção de escola dentro do **admin da escola**
  (tenant admin é amarrado a uma única escola — não faz sentido).

**Licenciamento / cobrança / bloqueio** _(ver §6e)_
- [x] **Bloqueio de escola (tenant)** por falta de pagamento ou outro motivo — flag de status
  no `Tenant` que suspende acesso ao painel e disparos, com motivo registrado.
- [x] **Plano anual: contador de expiração** — exibir quanto falta para a licença expirar
  (`dias_para_expirar` / `LicencaSaida`).
- [x] **Plano anual: aviso por email** de que a licença está próxima do vencimento
  (`NotificarLicencasAVencer` + porta `EmailSender`; adaptador atual é mock/log).

**Cadastro em massa**
- [ ] **Importação de alunos em massa** por **planilha ou PDF**, usando **LLM** para validar os
  dados e normalizar a formatação da planilha/PDF antes de persistir.

**Engajamento / cobertura de contatos** _(feedback de diretora — campo)_
- [x] **Alerta de aluno sem responsável com telefone vinculado** — a turma (`Sala`) sinaliza
  quantos alunos **ativos** estão **sem nenhum responsável (`Contato`) com telefone vinculado**
  e permite **disparar uma notificação ao professor** para solicitar os contatos faltantes.
  Ver §6c-ter (`app/interfaces/api/cadastro.py`, `web/app/admin/salas/`).
- [ ] **Confirmação de recebimento de avisos (não-entrega reativa)** — análogo à "confirmação de
  recebimento" de e-mail: após um broadcast, se algum número **não recebeu** a mensagem (celular
  desligado, sem sinal, etc.), depois de um intervalo o sistema **aponta que o responsável X não
  recebeu** o aviso. Implementado no back-end (ver §9b): o webhook da Meta atualiza o status por
  destinatário e um endpoint lista as não-entregas. **[Roadmap]** painel: depende do
  **histórico de broadcasts** no admin da escola.
  - [ ] **Notificação ativa de não-entrega (scheduler)** — hoje a não-entrega é calculada
    **sob demanda** no endpoint `.../nao-entregues`. Falta o **job agendado** que, depois do
    intervalo, roda `VerificarRecebimentoBroadcast` e **notifica o admin ativamente** (push/email)
    sobre os responsáveis que não receberam. Depende da **fila/scheduler de broadcasts** (§9a,
    ainda roadmap); o caso de uso já está pronto para ser chamado por ele.

**Super admin — histórico da escola**
- [x] **Histórico/ficha financeira da escola** no super admin (ver §6f):
  - [x] Quando entrou (`criado_em` / `dias_de_casa`).
  - [x] Quando cancelou (churn) e **motivo do cancelamento** (`CancelarEscola`/`ReativarEscola`,
    `cancelado_em`/`motivo_cancelamento`).
  - [x] Quanto paga no **plano mensal/anual** (`valor_*_centavos`, editáveis no modal de licença).
  - [x] **Métricas:** MRR/ARR e receita acumulada (LTV estimado); plano/ciclo; status de pagamento
    (derivado da licença); próxima renovação; churn e motivo; nº de usuários ativos, contatos,
    alunos, conversas e broadcasts; health score (heurística licença + tier de envio).
  - **Decisão de escopo:** ficha **derivada**, sem ledger de faturas — receita acumulada/LTV são
    estimativas (`meses_ativos × MRR`). [Roadmap] tabela de faturas para receita/LTV reais e
    histórico de faturas; "último acesso/atividade" depende do log de auditoria (§12a).
