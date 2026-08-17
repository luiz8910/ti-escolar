# Roadmap e backlog priorizado

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

## 12. Roadmap / Próximos passos

- [ ] Scaffold do back-end (camadas hexagonais, FastAPI, SQLAlchemy/Alembic, pgvector).
- [x] **Chat de demonstração removido** (10/ago/2026): a raiz `/` do painel simulava a
  interface do WhatsApp sobre as rotas públicas `/api/chat/*`. Existia para desenvolver e
  demonstrar a conversa **sem depender da homologação da Meta**; com o inbound real no ar
  ela virou uma segunda porta de entrada — a única sem login — que gravava conversa e
  gastava LLM. Removidos: `app/interfaces/api/chat.py`, os DTOs de mensagem, as configs
  `CHAT_DEMO_*`, `web/app/page.tsx` (agora redireciona para `/admin`), o link "Ver demo do
  chat" da sidebar e os tokens de tema `--wa-*`. `AtenderConversa` ficou sem ponto de
  entrada por um tempo; em 10/ago/2026 **passou a ser o caminho do inbound real** (§6j), e
  `ReceberMensagemRecebida` foi removido no lugar dele.
- [ ] `docker-compose.yml` com `db` / `backend` / `web` + migrations + seed.
- [ ] Adaptador **Meta WhatsApp Cloud API** (outbound) com templates, cota e **fila**
  (throttling, retry com backoff e agendamento — §9a).
- [~] **Migração para a Meta Cloud API direta** (canal único desde 27/jul/2026, com a verificação
  da empresa aprovada). Ver §9e:
  - [x] **Validação de `X-Hub-Signature-256`** no webhook (§9e.2) — era **bloqueante para o
    go-live**: o endpoint aceitava qualquer POST, permitindo forjar status de entrega e
    (após o inbound) conversas falsas.
  - [x] Remoção completa da Twilio (adaptador, webhook, testes, `TWILIO_*`, `content_sid`).
  - [x] **App publicado na Meta** ("Ao vivo", app id `3140942352961209`, em 06/ago/2026) — era
    **bloqueante e silencioso**: app não publicado recebe apenas webhooks de *teste*, então o
    inbound real não chega e nenhum status de entrega é registrado, sem nada dar erro. Ver
    `docs/producao-whatsapp.md` §1.1.
  - [x] **Número verificado e inscrito na WABA de produção** (id `2116419572321695`) em
    09/ago/2026 — `+55 15 99753-6978`, `phone_number_id` `1231892910008454`. O código não chegava
    em 06/ago (tráfego internacional de entrada); três dias depois **um único SMS entregou**, sem
    trocar chip nem método: o bloqueio era transitório, e a regra que vale é **esperar em vez de
    insistir**. Registrar o número exige ainda um **PIN de 6 dígitos** que a Meta não reexibe —
    guardado fora do repositório. Ver `docs/producao-whatsapp.md` §2 (passo 5) e §2.1.
  - [x] **Canal ligado e inbound provado em real** (10/ago/2026). O `/health` responde
    `{"canal": "meta"}` e a **primeira conversa real do produto** aconteceu: mensagem de WhatsApp
    ao número da escola → webhook → assinatura validada → roteamento por `phone_number_id` →
    RAG/LLM → resposta pelo número da escola → registro em `/admin/historico/conversas`.
    Três armadilhas silenciosas seguraram esse passo, todas registradas em
    `docs/producao-whatsapp.md`: o **app não publicado** (§1.1), o **canal sem token** (§6.1.1 —
    `criar_canal` cai no `DemoMessageChannel` sem erro) e a **WABA não inscrita no app**
    (§5.1 — `POST /{waba-id}/subscribed_apps`, que não tem interface no console). Nas três, o
    console fica verde e o sintoma é ausência de sinal. **Ainda falta o outbound real**
    (pagamento na WABA + templates aprovados).
  - [x] `Tenant.meta_phone_number_id` (migration `0024_tenant_meta_phone_number_id`, único por
    índice UNIQUE parcial) + `TenantRepository.por_meta_phone_number_id` + campo no painel.
  - [x] `MetaMessageChannel` honrando o `remetente` (URL montada por envio), com
    `Tenant.remetente_canal` resolvendo o id da escola — o outbound deixou de ser single-tenant.
  - [x] **Inbound** no `POST /api/webhook/meta` (`ProcessarInboundMeta`): roteia por
    `metadata.phone_number_id`, **descarta número desconhecido** (sem tenant de fallback),
    responde ativamente pelo número da escola e deduplica reentregas por `wamid`.
  - [x] Idempotência **durável** do inbound (tabela `inbound_atendimento`, com estado
    `em_atendimento` × `concluida`, migration `0026`). **[ ] Falta a fila/worker**, para o
    `200 OK` não depender da latência da LLM (§9e.1).
  - [x] Inbound de **mídia** (imagem/documento): baixado pela Graph API e guardado como
    documento da escola (§6k). Áudio segue fora, por exigir transcrição.
  - [ ] Automação do registro de número na WABA pela Graph API (§9e.3).
- [x] **Canal Meta WhatsApp Cloud API** como canal único do produto, com a **assinatura
  `X-Hub-Signature-256`** validada no webhook. Ver §9c e §9e.2.
- [x] **Inbound real do WhatsApp** pelo webhook da Meta: mensagens recebidas são roteadas à
  escola pelo `phone_number_id`, atendidas por `AtenderConversa` e respondidas por uma
  segunda chamada à API, a partir do número da própria escola. O produto passou a **atender**,
  não só disparar (`app/application/inbound_use_cases.py`). Ver §9e.1.
- [ ] Integrações reais de `DocumentSource` (substituir mocks).
- [x] **Base de conhecimento por tenant** (upload de documentos → RAG) e **system prompt
  personalizado por escola** (um "CLAUDE.md" do tenant), com painel em `web/app/admin/`.
- [x] **Cadastro escolar:** CRUD de **pais/responsáveis** e **salas (turmas)**, vínculo N:N e
  **relatório de pais por sala** (`app/interfaces/api/cadastro.py`, `web/app/admin/turmas/`).
- [x] **Gestão de escolas pelo super admin:** CRUD de tenants + visão de **conversas e broadcasts**
  por escola (`app/application/tenant_use_cases.py`, `web/app/admin/escolas/`).
- [x] Modelo de **administração** (super admin / admin de tenant) + **grupos de contatos**.
- [x] **Painel administrativo** (UI Next.js): login, gestão de grupos/contatos, barra de cota e
  disparo direcionado a grupo (`web/app/admin/`).
- [x] **Autenticação JWT/sessão:** `POST /api/admin/login` emite um JWT (HS256, stdlib) e as
  rotas admin exigem `Authorization: Bearer`; o painel guarda o token (não a senha) no
  `localStorage`. Ver §6a.
- [x] **Catálogo de templates** (12/ago/2026): criar no painel, **submeter à Meta** pela
  Business Management API, e o webhook `message_template_status_update` fechando o ciclo.
  Escopo **global** (catálogo compartilhado, super admin) + **por escola** (nome prefixado
  pelo slug). Ver §9a-bis (`app/application/templates_use_cases.py`,
  `web/app/admin/templates/`).
  - [x] **Várias contas do WhatsApp (WABA)** (13/ago/2026) — a conta virou entidade
    (`Waba` + `Tenant.waba_id`), o status do template passou a ser **por conta** e o global
    é replicado em todas. Sem isso, a escola seguinte ao teto de números do portfólio teria
    o disparo recusado pela Graph API **depois** de o painel dizer "aprovado". Ver §9a-ter.
  - [x] **Escolher o template na tela de disparo** (13/ago/2026) — o envio a grupo saiu do
    `DEMO_TEMPLATE_ID` cravado e passou a oferecer só os templates **aprovados na conta
    daquela escola**, com um campo por variável do corpo. Fecha junto o descasamento de
    parâmetros, que a Meta recusava depois de consumir a cota.
  - [~] **Cota de envio no nível do portfólio** (17/ago/2026) — o contador por tenant/dia
    virou um **livro de envios** (`envios_iniciados`, migration `0044`) contando
    **destinatários distintos numa janela de 24h corridas, por portfólio**. Corrige de uma
    vez os três erros do modelo anterior — dia de calendário, relógio em UTC (o "dia" virava
    às 21h de Brasília) e contagem por escola, que dava a cinco escolas de teste a impressão
    de 1250 de capacidade. A retomada de atendimento fora das 24h passou a consumir cota,
    o que antes acontecia em silêncio. Ver §9a-sexies.
    - [ ] **Falta ler o tier real da Meta** (`whatsapp_business_manager_messaging_limit`;
      o `messaging_limit_tier` foi depreciado) em vez do `META_DAILY_TIER_LIMIT` cravado.
  - [ ] **Assinar `message_template_status_update` no console da Meta** — sem isso o status
    só muda pelo botão "Sincronizar". Ver `docs/producao-whatsapp.md` §5.
- [x] **Transferência de responsáveis** (Onda 2 · F1) Progressão de série na virada de ano:
  os alunos ativos são promovidos para a série seguinte (ou marcados como ex-alunos na
  última série) e os responsáveis são inativados **apenas quando todos os seus alunos já são
  ex-alunos**. Ver §6h (`app/application/progressao_use_cases.py`, `web/app/admin/progressao/`).
- [x] **CRUD de Alunos** Aluno por tenant com **série 1:1** (`sala_id`) e **responsáveis N:N**
  (`aluno_responsaveis`), com `ativo` para marcar ex-aluno. Ver §6c-bis
  (`app/interfaces/api/cadastro.py`, `web/app/admin/alunos/`).
- [x] **CRUD de Professores** Professor por tenant (**nome + telefone**), vinculado à série por
  **`Sala.professor_id`** (uma série → um professor; um professor → N séries). Ver §6c-quinquies
  (`app/interfaces/api/cadastro.py`, `web/app/admin/professores/`).

### 12a. Backlog priorizado (novas tasks)

**Infra / deploy**
- [x] **Landing page institucional** (`site/`) em Next.js com export estático + pipeline
  `.github/workflows/site.yml` para a **Cloudflare Pages**. Ver §9d. Dados legais já
  preenchidos a partir do Cartão CNPJ. **Pendente:** criar o projeto Pages + secrets e
  apontar `tiescolar.com.br` (hoje sem registro A/CNAME) — pré-requisito para reenviar a
  verificação da empresa na Meta.
- [x] **Deploy automatizado**: são **três destinos**, um por camada —
  **back-end (FastAPI) → Render**, que **NÃO tem Auto-Deploy**: apesar do que esta linha
  afirmava, todo evento na aba *Events* do serviço é *"Manually triggered by you via
  Dashboard"*. **Mergear não publica o back-end** — depois do merge é preciso ir ao painel do
  Render → **Manual Deploy** → *Deploy latest commit*, senão o serviço fica atrás da `main`
  (foi o que aconteceu em 09/ago, quando `/health/pronto` respondia 404 em produção);
  **painel admin (`web/`) → Vercel**, que consome a API do Render;
  **landing page (`site/`) → Cloudflare Pages**, via `.github/workflows/site.yml` (§9d).
  O CI (`.github/workflows/ci.yml`) roda três jobs em PRs e na `main`, como portão de
  qualidade antes do merge: **back-end** (ruff + `alembic upgrade head` + pytest),
  **painel `web/`** (`tsc --noEmit` + `next build`) e **landing `site/`** (typecheck + export
  estático). O front entrou no CI em 29/jul/2026 — até então um erro de TypeScript só
  aparecia quando a Vercel tentava publicar. O `next lint` **não** é usado: o projeto não tem
  configuração de ESLint e o comando entra em modo interativo.
  > O `ruff` está fixado em `>=0.5,<0.16` no `backend/pyproject.toml`: sem teto, o CI
  > instalava a versão mais nova a cada execução e a 0.16.0 quebrou a build sem que o
  > código mudasse (358 dos 424 achados eram `B008`, o `Depends()` do FastAPI).

**Prontidão para produção** _(ver §15 e §16)_
- [x] **Seed restrito a homologação** + `app.bootstrap` para o super admin (§10).
- [x] **Rate limiting** no login e no inbound, com contador no Postgres (§15, item 5).
- [x] **Idempotência durável** do inbound (`inbound_atendimento`, §9e.1).
- [x] **Painel de Logs** + id de correlação + telas de erro (§16, itens 6 e 8).
- [x] **E-mail real** via Resend (§6e).
- [x] **Soft delete de aluno** (§6c-bis).
- [x] **Paginação** das listagens que crescem (§15, item 7).
- [x] **Front no CI** (typecheck + build de `web/` e `site/`).
- [x] **Runbook de rollback** (`docs/runbook-rollback.md`) — falta o **ensaio**.
- [ ] **Política de backup** (`docs/backup.md`) — proposta escrita, **aguardando decisão**.
- [ ] **Alerta ativo** de falha crítica (e-mail/push/Sentry) — o que mantém o item 8 em ⚠️.

**Observabilidade / histórico** _(ver §13)_
- [x] **Histórico completo de mensagens em massa (broadcasts)** enviadas no admin da escola —
  lista os disparos com **template**, destinatários, **status de entrega** e data, e um detalhe
  por responsável (`ObterBroadcastDaEscola`, `web/app/admin/historico/disparos/`).
- [x] **Histórico completo de conversas do WhatsApp** (mensagens recebidas e respostas da LLM),
  consultável no admin da escola (`web/app/admin/historico/conversas/`).
- [~] **Log de auditoria de ações** — grava ações de **usuários logados** no painel (login,
  criação de usuário/grupo, disparo a grupo), com quem/o quê/quando/payload. Base para
  rastreabilidade/compliance (`web/app/admin/historico/auditoria/`).
  - [x] **Auditar as ações da LLM no inbound real** (10/ago/2026). O `llm.resposta` só era
    emitido por `AtenderConversa`, que atendia o chat de demonstração; o caminho real
    (`ReceberMensagemRecebida`) nunca auditou. Resolvido pela via mais completa das duas:
    o inbound **passou a usar `AtenderConversa`**, que além da auditoria traz o **tool use**
    (o LLM decide quando buscar conhecimento, recuperar documento ou chamar a secretaria, em
    vez do roteamento por palavra-chave). `ReceberMensagemRecebida` foi removido. Ver §6j.

**Atendimento humano** _(ver §6j)_
- [x] **Fila de atendimento da secretaria** — o assistente oferece atendimento humano
  quando não resolve, o responsável confirma, e o caso cai numa fila no painel. A
  secretaria responde **no mesmo fio de WhatsApp**, pelo número da escola.
  (`app/application/atendimento_humano_use_cases.py`, `web/app/admin/atendimentos/`).
- [x] **Inbound migrado para `AtenderConversa`** (tool use), fechando de quebra a auditoria
  da LLM no caminho real; `ReceberMensagemRecebida` removido.
- [x] **Expediente por escola** (`Tenant.expediente_*`) governando o que o assistente
  promete ao responsável. **Falta:** feriados/recesso.
- [x] **Tela de equipe da escola** (`web/app/admin/usuarios/`) — antes só existia a API.
  Desde 12/ago/2026 com **cargos e hierarquia** (§6a): a tela só oferece cargos abaixo do
  seu e esconde as ações em quem você não pode gerir, mas quem impõe é o back-end — o
  filtro na tela é conveniência, não segurança.
- [ ] **Notificar o atendente por WhatsApp/e-mail** — hoje a notificação é in-app (badge com
  polling na sidebar). Exige um telefone no `Usuario`.
- [x] **Template `retomada_atendimento` aprovado na Meta** (conferido em 12/ago/2026:
  "Ativo — Qualidade pendente", que é o estado normal de aprovado que ainda não enviou o
  bastante para ter nota). Já não é preciso preencher `TEMPLATE_RETOMADA_ATENDIMENTO` no
  Render — virou o default —, mas o **status precisa chegar ao catálogo**, pelo webhook ou
  pelo botão "Sincronizar com a Meta" (§9a-bis).

**Documentos dos pais** _(ver §6k)_
- [x] **Receber documento pelo WhatsApp** (imagem e PDF): baixado da Graph API, guardado na
  escola, classificado e vinculado a um aluno no painel (`web/app/admin/documentos/`).
- [x] **Retenção e expurgo** dos arquivos (dado sensível de menor), auditoria de download e
  política de privacidade atualizada.
- [ ] **Adaptador de object storage (Cloudflare R2)** — hoje os bytes vão para `bytea` no
  Neon, que cobra por GB. A porta `ArquivoStorage` já existe; falta o bucket, os secrets e
  o adaptador.
- [ ] **Job agendado do expurgo** — o caso de uso está pronto, mas depende de alguém
  chamar `POST /api/admin/documentos/expurgar`.
- [ ] **Áudio** (exige transcrição) e ligação automática com `SolicitacaoMatricula` (§E1).

**Limpeza de UI (remoções)**
- [x] **Remover** a emissão de relatórios em **lista** de pais na seção "Salas e pais"
  (não faz sentido manter).
- [x] **Remover** o dropdown de seleção de escola dentro do **admin da escola**
  (tenant admin é amarrado a uma única escola — não faz sentido).
- [x] **Remover o chat de demonstração** (10/ago/2026) — o simulador do WhatsApp na raiz `/`
  existia para demonstrar a conversa antes da homologação da Meta. Com o inbound real no ar,
  ele virou uma segunda porta de entrada, sem login, que gravava conversa e gastava LLM.
  Ver §1 e §15 item 1.

**Licenciamento / cobrança / bloqueio** _(ver §6e)_
- [x] **Bloqueio de escola (tenant)** por falta de pagamento ou outro motivo — flag de status
  no `Tenant` que suspende acesso ao painel e disparos, com motivo registrado.
- [x] **Plano anual: contador de expiração** — exibir quanto falta para a licença expirar
  (`dias_para_expirar` / `LicencaSaida`).
- [x] **Plano anual: aviso por email** de que a licença está próxima do vencimento
  (`NotificarLicencasAVencer` + porta `EmailSender`; adaptador atual é mock/log).

**Cadastro em massa**
- [x] **Importação de alunos em massa** por **planilha ou PDF**, usando **LLM** para validar os
  dados e normalizar a formatação da planilha/PDF antes de persistir. Fluxo prévia→confirmação,
  escopado por tenant. Ver §6c-quater (`app/application/importacao_use_cases.py`,
  `app/interfaces/api/cadastro.py`, `web/app/admin/alunos/`).

**Engajamento / cobertura de contatos** _(feedback de diretora — campo)_
- [x] **Alerta de aluno sem responsável com telefone vinculado** — a turma (`Sala`) sinaliza
  quantos alunos **ativos** estão **sem nenhum responsável (`Contato`) com telefone vinculado**
  e permite **disparar uma notificação ao professor** para solicitar os contatos faltantes.
  Ver §6c-ter (`app/interfaces/api/cadastro.py`, `web/app/admin/turmas/`).
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
- [ ] **Histórico/ficha financeira da escola** no super admin:
  - Quando entrou (data de início).
  - Quando cancelou (se aplicável) e **motivo do cancelamento**.
  - Quanto pagou no **plano anual** e quanto paga no **plano mensal**.
  - **Métricas sugeridas (adicionais):** MRR/ARR e receita acumulada (LTV) por escola;
    plano atual e ciclo (mensal/anual); status de pagamento e histórico de faturas;
    data da próxima renovação; churn e motivo; uso vs. cota (broadcasts/mensagens no
    período); nº de usuários ativos, contatos e alunos; data do último acesso/atividade;
    health score (qualidade do número Meta + tier de envio).
