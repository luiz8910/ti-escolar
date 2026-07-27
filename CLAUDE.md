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
├── web/                      # painel admin + demo Next.js (simula o WhatsApp)
└── site/                     # landing page institucional (tiescolar.com.br)
```

---

## 6. Modelo de dados (multi-tenant)

- **Isolamento por `tenant_id`** (escola) em todas as tabelas relevantes.
- Entidades principais: `Tenant` (escola), `Usuario` (admin), `Conversa`, `Mensagem`,
  `Documento`, `Conhecimento` (FAQ/aviso/procedimento), `MessageTemplate`, `Broadcast`/Campanha,
  `MessageQuota`, `Contato` (pai/responsável), `Grupo` + associação `grupo_contatos`,
  `Sala` (turma) + associação `sala_contatos`, `Professor` (vinculado à série por
  `Sala.professor_id`), `FonteConhecimento` (documento da escola),
  `PromptTenant` (system prompt da escola), `ResumoEscola` (visão agregada do super admin),
  `SolicitacaoInterna` (canal professor→escola), `MensagemMediada` (canal pai↔professor),
  `CotaImpressao` (franquia mensal de impressão), `AvisoFalta` (falta de professor +
  chamada de eventual), `FichaMatricula` (ficha de matrícula digital, 1:1 com `Aluno`) e
  `SolicitacaoMatricula` (matrícula self-service pelo WhatsApp). `Contato` tem flag `ativo`
  (responsável inativo — todos os alunos já são ex-alunos).
- **Embeddings:** tabela `conhecimento` com coluna `vector` (pgvector) + metadados para RAG;
  `fonte_id` liga cada trecho à `FonteConhecimento` que o originou.
- **Migrations:** `0001_initial` → `0002_admins_grupos` → `0003_salas` →
  `0004_conhecimento_prompt` → `0005_alunos` → `0006_licenciamento_tenant` →
  `0006_destinatario_entrega` → `0007_auditoria` → `0007_ficha_financeira_tenant` →
  `0008_professores` → `0009_tenant_whatsapp` → `0010_template_content_sid` →
  `0011_tenant_telefone_contato` → `0012_respostas_rapidas` → `0013_avisos_temporizados` →
  `0014_solicitacoes_impressao` → `0015_mural_professor` → `0016_solicitacoes_internas` →
  `0017_mensagens_mediadas` → `0018_cota_impressao` → `0019_contato_ativo` →
  `0020_avisos_falta` → `0021_ficha_matricula` → `0022_solicitacoes_matricula` →
  `0023_remover_content_sid`.
  **Cadeia linear obrigatória:** ao criar uma migration, encadeie no head atual
  (`down_revision` = último head) para evitar **multiple heads** no `alembic upgrade head`
  do deploy.
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

### 6c-quinquies. Professores (CRUD + atribuição à série)

- **`Professor`** por tenant, modelo **enxuto: apenas `nome` e `telefone`** (WhatsApp, E.164).
  Único por `(tenant_id, telefone)` (migration `0008_professores`, tabela `professores`).
- **Vínculo professor ↔ série:** o relacionamento mora na **série**, via
  **`Sala.professor_id`** (FK `salas.professor_id` → `professores.id`, `ON DELETE SET NULL`).
  Assim uma **série tem no máximo um professor**, e um **professor pode conduzir várias séries**
  (1:N). Remover o professor apenas **desvincula** as séries (não as apaga). `Sala.professor_nome`
  é denormalizado só para exibição.
- **Casos de uso** em `app/application/cadastro_use_cases.py`: `CadastrarProfessor` (valida
  telefone único), `ListarProfessores`, `ObterProfessor`, `AtualizarProfessor`,
  `RemoverProfessor`; e a atribuição via `SalaRepository.definir_professor` —
  `AtribuirProfessorASala` (define/troca; valida que o professor é do tenant),
  `RemoverProfessorDaSala` (`professor_id` ← `NULL`) e `ListarSeriesDoProfessor`. Repositório
  `SqlProfessorRepository`.
- **Rotas** em `app/interfaces/api/cadastro.py`: `professores` (POST · GET `tenant/{tenant_id}`),
  `professores/{id}` (GET/PUT/DELETE), `professores/{id}/series` (GET) e
  `PUT /salas/{id}/professor` (corpo `professor_id`; `null` desvincula).
- **Painel:** `web/app/admin/professores/` — cadastro/edição/exclusão de professores, atribuição do
  professor responsável por série e a lista das séries de cada professor. O seed cria um professor
  demo ("Prof. Carla Mendes") atribuído às séries de demonstração.
- A remoção de tenant (`SqlTenantRepository.remover`) apaga, na cascata explícita, `sala_contatos`
  → `salas` → `professores` (antes inexistente para `salas`; necessário pelas novas FKs).

### 6c-quater. Importação de alunos em massa (planilha/PDF + LLM)

- **Fluxo em duas etapas** (revisar antes de gravar), em
  `app/application/importacao_use_cases.py`:
  1. **Prévia** (`PrevisualizarImportacaoAlunos`): o texto bruto da planilha/PDF vai à
     `LLMProvider`, que **normaliza e estrutura** os alunos (nomes, telefones em E.164, série).
     O resultado é **validado em código** (a LLM não é fonte de verdade) e devolvido para
     revisão — **nada é persistido**. Telefones via `normalizar_telefone` (E.164 BR);
     séries citadas inexistentes no tenant são marcadas `serie_nova`.
  2. **Confirmação** (`ConfirmarImportacaoAlunos`): recebe as linhas revisadas e persiste de
     forma **determinística e sem LLM** — resolve/cria `Sala` (se `criar_series_ausentes`),
     reaproveita/cria `Contato` por telefone (dedupe) e cadastra os `Aluno`s com responsáveis.
     Linhas inválidas e séries ausentes (sem permissão de criar) são **ignoradas**.
- **Value objects** (`entities.py`): `ResponsavelImportado`, `LinhaImportacaoAluno`
  (`erros`/`avisos`/`serie_nova`/`valido`), `PreviaImportacaoAlunos`,
  `ResultadoImportacaoAlunos`. Tudo **escopado por tenant**.
- **LLM:** usa a porta `LLMProvider` existente (sem novo SDK). O prompt leva o marcador
  `IMPORTACAO_ALUNOS_JSON_V1`; o `FakeLLMProvider` (demo sem chaves) reconhece o marcador e
  converte CSV/TSV em JSON, mantendo o fluxo demonstrável.
- **Rotas** em `app/interfaces/api/cadastro.py`: `POST /alunos/importar/previa`
  (corpo: `tenant_id`, `conteudo`) e `POST /alunos/importar/confirmar`
  (corpo: `tenant_id`, `linhas`, `criar_series_ausentes`). A confirmação **revalida no
  servidor** (não confia no cliente).
- **Painel:** `web/app/admin/alunos/` — card "Importar alunos em massa" → modal com upload
  (`.csv/.tsv/.txt`) ou colar texto → tabela de prévia (badge "nova" para séries, status por
  linha, criar séries ausentes) → resultado.

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
- **Número de WhatsApp por escola (`Tenant.whatsapp_numero`, E.164):** cada escola atende/dispara
  pelo seu próprio número (multi-tenant). `CriarEscola`/`AtualizarEscola` recebem o número,
  **normalizam** para E.164 (`normalizar_whatsapp`, aceita DDI internacional) e **validam a
  unicidade** entre escolas (`TenantRepository.por_whatsapp`; dois tenants com o mesmo número
  tornariam o inbound ambíguo). Vazio = usa o número padrão do canal (`META_PHONE_NUMBER_ID`).
  Migration `0009_tenant_whatsapp`. **Roteamento:** o outbound (`EnviarBroadcast`) sai do número
  da própria escola; o roteamento do inbound por escola depende do `meta_phone_number_id` — ver
  §9e.1. **Modelo operacional:** cada escola opera com um **número dedicado** à plataforma,
  **adquirido e registrado por nós** (o número antigo da secretaria segue livre para o
  atendimento manual) — ver §9e.3.
- **Telefone de contato por escola (`Tenant.telefone_contato`, E.164):** o número **público** que
  a secretaria já usa no dia a dia — apenas **informativo** (referência de contato). É
  **obrigatório** no cadastro/edição (`CriarEscola`/`AtualizarEscola` via
  `normalizar_telefone_contato`), mas **não roteia inbound**, **não é remetente do outbound** e
  **não exige unicidade** entre escolas (duas escolas podem compartilhá-lo). Migration
  `0011_tenant_telefone_contato`. Distinto de `whatsapp_numero` (o número operado pela plataforma).
- **Rotas** em `app/interfaces/api/admin.py` (guard `_exige_super_admin`): `/api/admin/escolas`
  (POST/GET), `/escolas/{tenant_id}` (GET/PUT/DELETE), `/escolas/{tenant_id}/conversas`,
  `/escolas/{tenant_id}/conversas/{conversa_id}` e `/escolas/{tenant_id}/broadcasts`. `EscolaEntrada`
  e `Escola(Resumo)Saida` carregam `whatsapp_numero` e `telefone_contato`.
- **Painel:** `web/app/admin/escolas/` (lista com campo de WhatsApp no cadastro/edição + detalhe por
  `[tenantId]`).

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

### 6g. Comunicação interna e atendimento — Onda 1 (cliente-âncora EM Rosa Cury)

Quatro features que reduzem a carga da secretaria e o atrito secretaria↔professor. **Não exigem
LLM novo:** reusam o RAG existente (que já chama o `LLMProvider`).

- **C1 · Respostas rápidas → RAG (`RespostaRapida`):** os "atalhos" da secretaria (chave +
  conteúdo), únicos por `(tenant_id, chave)`. Cada uma é **ingerida no RAG** (reusa
  `IngerirDocumento`; `fonte_id` liga à `FonteConhecimento` gerada) para o bot responder
  automaticamente; `ativo` controla a indexação. Casos de uso em
  `app/application/respostas_rapidas_use_cases.py` (criar/listar/obter/atualizar/remover; editar
  reindexa, remover/desativar apaga os trechos). Repositório `SqlRespostaRapidaRepository`
  (`repositories_conhecimento.py`). Rotas `app/interfaces/api/respostas_rapidas.py`
  (`/api/admin/respostas-rapidas`). Migration `0012_respostas_rapidas`. Seed com os 19 atalhos reais
  da Rosa Cury. Painel `web/app/admin/respostas-rapidas/`.
- **C2 · Aviso geral temporizado (`AvisoTemporizado`):** recado do dia com **janela de vigência**
  opcional (`inicia_em`/`expira_em`) e `ativo`. Enquanto **vigente** (`vigente_em`), é **anexado à
  resposta do bot** a quem inicia a conversa (integrado em `ReceberMensagemRecebida` **e**
  `AtenderConversa`, via `AvisoTemporizadoRepository` opcional) — "sem mexer no celular". Casos de
  uso em `app/application/avisos_use_cases.py`. Repositório `SqlAvisoTemporizadoRepository`
  (`repositories_comunicacao.py`). Rotas `app/interfaces/api/avisos.py` (`/api/admin/avisos`).
  Migration `0013_avisos_temporizados`. Painel `web/app/admin/avisos/`.
- **B1 · Fila de impressão (`SolicitacaoImpressao`):** o professor envia um arquivo com parâmetros
  (`copias`, `colorido`, `frente_verso`, `observacao`); cai numa fila (`status` ∈ {`pendente`,
  `em_processo`, `concluida`, `cancelada`}) para a secretaria processar. `professor_id` FK a
  `professores` (`ON DELETE SET NULL`). Casos de uso em `app/application/impressao_use_cases.py`.
  Repositório `SqlSolicitacaoImpressaoRepository`. Rotas `app/interfaces/api/impressao.py`
  (admin: `/api/admin/impressao`) e submissão pelo próprio professor em
  `/api/professor/impressao`. Migration `0014_solicitacoes_impressao`. Painel
  `web/app/admin/impressao/`.
- **A1 · Mural do professor (`Recado` + `LeituraRecado`):** a secretaria publica recados; o
  professor tem **login próprio** e **confirma a leitura** ("ticado"). A secretaria vê quem leu /
  quem não leu e **re-notifica por WhatsApp** os não-lidos (`ReNotificarRecadoNaoLido` via
  `MessageChannel`). **Autenticação do professor:** `Professor.senha_hash` (PBKDF2, definida pela
  secretaria em `CadastrarProfessor`/`AtualizarProfessor` via `senha`); `AutenticarProfessor` +
  `POST /api/professor/login` emite JWT com `papel="professor"`; a dependência
  `professor_autenticado` revalida no banco. Casos de uso em `app/application/mural_use_cases.py`.
  Repositório `SqlMuralRepository` (`repositories_comunicacao.py`). Rotas: admin
  `app/interfaces/api/mural.py` (`/api/admin/recados` + `.../leitura`, `.../renotificar`) e
  professor `app/interfaces/api/professor.py` (`/api/professor/recados`, `.../leitura`).
  Migration `0015_mural_professor` (adiciona `professores.senha_hash` + `recados` +
  `leituras_recado`). Painel: secretaria `web/app/admin/mural/`; portal do professor
  `web/app/professor/` (login + mural + solicitar impressão). Seed: professor demo com senha
  (`DEMO_PROFESSOR_SENHA`, default `prof123`) e um recado.

### 6h. Consolidação interna — Onda 2 (cliente-âncora EM Rosa Cury)

Quatro features que consolidam a comunicação interna e o ciclo de vida escolar. Nenhuma
exige LLM novo. Todas escopadas por `tenant_id`.

- **A2/A4 · Canal interno professor→secretaria + roteamento por assunto
  (`SolicitacaoInterna`):** o professor abre recados/pedidos pelo sistema (não pelo
  WhatsApp pessoal), com **`categoria`** ∈ {`secretaria`, `gestao`, `pedagogico`} que
  **roteia** o assunto (§A4) e **`status`** ∈ {`aberta`, `em_andamento`, `resolvida`,
  `cancelada`}. A escola responde no próprio registro (`resposta`/`respondido_em`) e pode
  **notificar o professor por WhatsApp** (`MessageChannel`). Casos de uso em
  `app/application/comunicacao_interna_use_cases.py`; repositório
  `SqlSolicitacaoInternaRepository` (`repositories_comunicacao.py`). Rotas: admin
  `app/interfaces/api/comunicacao_interna.py` (`/api/admin/solicitacoes-internas`) e
  professor em `professor.py` (`/api/professor/solicitacoes`). Migration
  `0016_solicitacoes_internas`. Painel: secretaria `web/app/admin/solicitacoes/`; professor
  em `web/app/professor/`.
- **A3 · Canal pai↔professor mediado (`MensagemMediada`):** o professor conversa com o
  responsável **sem expor o número pessoal** — ao responder, a mensagem sai pelo número da
  escola (`Tenant.whatsapp_numero` como `remetente` do `MessageChannel`) e é registrada; as
  mensagens do responsável entram pelo mesmo canal (`RegistrarMensagemDoResponsavel`, ponto
  de entrada para o webhook/secretaria) e aparecem no painel do professor. Uma "conversa" é
  o par (`professor_id`, `contato_telefone`). Casos de uso em
  `app/application/mediacao_use_cases.py`; repositório `SqlMediacaoRepository`. Rotas:
  professor `/api/professor/mensagens` (listar interlocutores/thread, enviar) e admin
  `app/interfaces/api/mediacao.py` (`/api/admin/mediacao` — registrar recebida + acompanhar).
  Migration `0017_mensagens_mediadas`. Painel: `web/app/professor/`.
- **B2 · Cota e relatório de impressões (`CotaImpressao`):** **franquia mensal por
  professor** (`limite_mensal`; `<= 0` = sem limite). O relatório mensal
  (`RelatorioImpressaoMensal`, competência `YYYY-MM`) agrega as `SolicitacaoImpressao` **não
  canceladas** por professor, cruza com a cota e sinaliza quem **excedeu** ("bateu a meta").
  Casos de uso em `app/application/impressao_use_cases.py` (estende a fila §B1); repositório
  `SqlCotaImpressaoRepository`. Rotas em `app/interfaces/api/impressao.py`
  (`/api/admin/impressao/cotas`, `/api/admin/impressao/relatorio`). Migration
  `0018_cota_impressao`. Painel: `web/app/admin/impressao/relatorio/`.
- **F1 · Progressão de série + ciclo de vida do responsável:** na virada de ano,
  `PromoverSerie`/`PromoverTurmas` movem os alunos **ativos** para a série seguinte (ou os
  marcam como ex-alunos na última série — `destino=None`), e
  `InativarResponsaveisSemAlunosAtivos` inativa (`Contato.ativo=False`) **apenas** os
  responsáveis cujos alunos já são **todos** ex-alunos (idempotente; preserva quem ainda tem
  aluno ativo ou nenhum vínculo). Casos de uso em
  `app/application/progressao_use_cases.py`. Rotas em `app/interfaces/api/progressao.py`
  (`/api/admin/progressao/promover`, `/api/admin/progressao/inativar-responsaveis`).
  Migrations `0019_contato_ativo` (flag `contatos.ativo`). Painel:
  `web/app/admin/progressao/`.
- **J1 · Acesso web por link:** princípio transversal já atendido pelo painel Next.js (App
  Router) e pelo **portal do professor** (`web/app/professor/`), acessíveis por link direto —
  sem dependência de app nativo. Reforçado nesta onda com as novas páginas web.
- **Seed:** o tenant demo ganha uma `SolicitacaoInterna` de exemplo e uma `CotaImpressao`
  (3.000 cópias/mês) para o professor demo.

### 6i. Digitalização documental — Onda 3 (cliente-âncora EM Rosa Cury)

Cinco features de digitalização e resiliência documental. Nenhuma exige LLM novo (D3 reusa
a porta `LLMProvider`, como a importação em massa). Todas escopadas por `tenant_id`.

- **I1 · Aviso de falta + chamada de eventual (`AvisoFalta`):** o professor avisa a falta
  pelo sistema (`RegistrarFaltaProfessor`; também via portal `POST /api/professor/faltas`);
  a secretaria dispara o pedido de **substituto** para uma lista de candidatos
  (`ChamarEventual` — envia texto pelo `MessageChannel`, a partir do número da escola, e
  registra `eventuais_chamados`), confirma quem cobre (`ConfirmarEventual` → `coberta`) ou
  cancela (`CancelarFalta`). `status` ∈ {`aberta`, `coberta`, `cancelada`}; `professor_id`
  FK a `professores` (`ON DELETE SET NULL`). Casos de uso em
  `app/application/falta_use_cases.py`; repositório `SqlAvisoFaltaRepository`
  (`repositories_onda3.py`); rotas admin `app/interfaces/api/faltas.py`
  (`/api/admin/faltas`). Migration `0020_avisos_falta`.
- **H1 · Exportar conversa para fins legais (`ConversaExportada`):** `ExportarConversaLegal`
  monta um **documento textual** de uma conversa (opcionalmente recortada por período) com
  cabeçalho institucional e marca de exportação, para anexar a processo/prontuário. Reusa
  `ConversaRepository` (`obter_conversa`/`mensagens`) + `TenantRepository`. Rota
  `GET /api/admin/escolas/{tenant_id}/conversas/{conversa_id}/exportar?inicio=&fim=`
  (`app/interfaces/api/exportacao.py`, guard `_exige_acesso_tenant`). Sem migration.
- **D1/D2/D3 · Ficha de matrícula digital (`FichaMatricula`):** ficha rica (frente + verso)
  1:1 com `Aluno`, com os campos **obrigatórios/sensíveis** (§D2): `cor_raca` (obrigatório,
  validado no caso de uso), Bolsa Família/NIS, deficiência/necessidade especial, laudo/CID,
  restrição alimentar, alergia; e as autorizações (van, retirada, imagem). Persistida como
  **JSON `conteudo`** (todos os campos, mais `dados_extra` para campos configuráveis por
  escola — §D1). CRUD em `app/application/ficha_use_cases.py` (`SalvarFichaMatricula` upsert,
  `ObterFichaMatricula`, `RemoverFichaMatricula`). **Leitura por IA (§D3):** fluxo
  prévia→confirmação — `PrevisualizarFichaMatricula` manda o texto/OCR à `LLMProvider`
  (marcador `FICHA_MATRICULA_JSON_V1`; o `FakeLLMProvider` o reconhece), **valida em código**
  e devolve para revisão; `ConfirmarFichaMatricula` persiste. Repositório
  `SqlFichaMatriculaRepository`; rotas `app/interfaces/api/fichas.py` (`/api/admin/fichas`,
  `.../importar/previa`, `.../importar/confirmar`). Migration `0021_ficha_matricula`.
- **E1 · Matrícula self-service pelo WhatsApp (`SolicitacaoMatricula`):** o responsável
  inicia a matrícula; `IniciarMatricula` cria a solicitação (idempotente por telefone) e
  `montar_mensagem_documentos` devolve a **lista de documentos exigidos** (reusa os atalhos
  de inscrição). `AnexarDocumentoMatricula` registra os arquivos enviados (`documentos` em
  JSON) e avança para `documentos_enviados`; `AtualizarStatusMatricula` conduz até
  `concluida`/`cancelada`. `status` ∈ {`iniciada`, `documentos_enviados`, `em_analise`,
  `concluida`, `cancelada`}. Casos de uso em `app/application/matricula_use_cases.py`;
  repositório `SqlSolicitacaoMatriculaRepository`; rotas `app/interfaces/api/matricula.py`
  (`/api/admin/matriculas`). Migration `0022_solicitacoes_matricula`.
- **G1 · Limite de caracteres na mensagem do pai:** `ReceberMensagemRecebida` recebe
  `max_chars` (config `MENSAGEM_PAI_MAX_CHARS`, default 1000; 0 desativa); acima do limite,
  o bot pede objetividade **sem acionar a LLM** (assunto de secretaria pede recado curto).
- **Seed:** o tenant demo ganha um `AvisoFalta` (professor demo), uma `FichaMatricula` do
  primeiro aluno demo (com `cor_raca`) e uma `SolicitacaoMatricula` de exemplo.
- **Remoção de tenant** (`SqlTenantRepository.remover`): a cascata explícita passa a apagar
  `fichas_matricula` e `solicitacoes_matricula` (antes dos alunos) e `avisos_falta` (antes
  dos professores), pois as FKs a `tenants` não têm `ON DELETE CASCADE`.

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

### 9c. Canal Meta WhatsApp Cloud API (implementação atual)

Adaptador oficial, selecionável por `MESSAGE_CHANNEL=meta`. É o **único canal real** do
produto: a Twilio, que existiu como atalho para operar sem a verificação de empresa da Meta,
foi **removida do código em 27/jul/2026** quando a verificação foi aprovada — ver §9e.

- **Outbound** (`app/infrastructure/channel/meta_channel.py`): `MetaMessageChannel` implementa
  `MessageChannel` sobre a Graph API (`/{phone_number_id}/messages`, `Authorization: Bearer`).
  Retorna o `wamid` como id externo, que é o que liga o envio ao status de entrega (§9b).
  Cobre texto livre (só dentro da janela de 24h), **template** (`nome` + `idioma` + parâmetros
  de body) e documento. Cota e throttling ficam nos casos de uso, não no adaptador.
- **Webhook** (`app/interfaces/api/webhook.py`, `/api/webhook/meta`): o `GET` responde ao
  handshake (`hub.challenge`) conferindo o `hub.verify_token`; o `POST` recebe os eventos e
  aplica os **status de entrega** aos destinatários dos broadcasts via `RegistrarStatusEntrega`.
  O **inbound de mensagens ainda não está implementado** — ver §9e.1.
- **Autenticidade do webhook:** todo `POST` é validado pelo **`X-Hub-Signature-256`**
  (HMAC-SHA256 do **corpo bruto** com o app secret, comparação em tempo constante — só stdlib,
  `app/infrastructure/security.py · validar_assinatura_meta`) quando
  `META_VALIDATE_SIGNATURE=true`. Assinatura ausente/ inválida → **403 seco**, sem processar e
  sem revelar a causa. Ver §9e.2 para o porquê disso ser bloqueante.
- **Config** (`.env`): `META_PHONE_NUMBER_ID` (fallback), `META_WABA_ID`, `META_ACCESS_TOKEN`
  (token de **usuário do sistema** — o da tela de Configuração da API expira em 24h),
  `META_WEBHOOK_VERIFY_TOKEN`, `META_DAILY_TIER_LIMIT`, `META_APP_SECRET` e
  `META_VALIDATE_SIGNATURE`. A fábrica `criar_canal` (`app/infrastructure/factories.py`)
  escolhe o adaptador pelo `MESSAGE_CHANNEL` (`demo` | `meta`).
- **Templates:** identificados por `nome` + `idioma`, que precisam bater com o template
  aprovado no WhatsApp Manager. Não há mais `content_sid` (era o `ContentSid` da Content API da
  Twilio; removido na migration `0023_remover_content_sid`).
- **Go-live em produção:** `docs/producao-whatsapp.md` traz o checklist completo (WABA de
  produção, número por escola, token permanente, webhooks, templates, limites/tiers).

---

### 9d. Landing page institucional (`site/`) — Cloudflare Pages

Site público em **`site/`** (`tiescolar.com.br`), **separado do painel**: projeto Next.js
próprio, sem imports de `web/`, sem chamadas de API e sem estado. Reusa os **mesmos design
tokens** do painel (marca Cobalt, Plus Jakarta Sans) copiados em `site/app/globals.css` +
`site/tailwind.config.ts`, de modo que site e produto compartilham a identidade sem acoplar
os projetos.

- **Por que existe:** além de apresentar o produto, a **verificação da empresa na Meta**
  exige um site público no ar com **razão social e CNPJ visíveis**, política de privacidade
  e termos de uso. A falta disso reprovou o envio de jul/2026 (o domínio não tinha registro
  A/CNAME — só o MX do Email Routing).
- **Build:** `output: "export"` (HTML/CSS/JS estáticos em `site/out/`) + `trailingSlash`.
  Sem servidor Node, sem adapter, sem Workers — a Cloudflare Pages serve os arquivos direto.
  Fontes via `next/font` (auto-hospedadas no build): a página **não faz nenhuma requisição a
  domínio externo** em runtime.
- **Dados institucionais em um único arquivo:** `site/lib/empresa.ts` (razão social, CNPJ,
  endereço, telefone, e-mail). Campos ainda não preenchidos ficam marcados como `PENDENTE` e
  o bloco correspondente **não é renderizado** — nada de placeholder no ar. Os valores
  precisam bater **caractere por caractere** com o Cartão CNPJ e com *Informações da empresa*
  no Business Manager.
- **Páginas:** `/` (hero, dores, funcionalidades, como funciona, segurança/LGPD, contato),
  `/privacidade/`, `/termos/`, 404, `robots.txt`, `sitemap.xml`. O rodapé carrega a
  identificação legal do controlador em todas elas.
- **Deploy:** `.github/workflows/site.yml` — push na `main` que toque em `site/**` faz
  build + publica em produção na Cloudflare Pages; PR gera **preview** com URL própria.
  Exige o projeto Pages criado (`ti-escolar-site`) e os secrets `CLOUDFLARE_API_TOKEN` /
  `CLOUDFLARE_ACCOUNT_ID`; sem eles o workflow só valida o build. Ver `site/README.md`.

### 9e. Migração para a Meta Cloud API direta — **[Roadmap: em execução]**

**Decisão (27/jul/2026):** com a **verificação da empresa aprovada** na Meta (portfólio
TiEscolar, business_id 940840332344260), o canal do produto passa a ser a **Meta Cloud API
direta**. A Twilio existia por um único motivo — o Sandbox operava **sem** a verificação de
empresa; com a verificação aprovada, o BSP intermediário só acrescentaria margem sobre o preço
da Meta. Por isso a Twilio foi **removida por inteiro** do código, da config e da documentação
nesta data (adaptador, webhook, testes, variáveis `TWILIO_*` e a coluna `templates.content_sid`,
que era o `ContentSid` da Content API deles — migration `0023_remover_content_sid`).

**Topologia multi-tenant escolhida:** **uma única WABA nossa** (não uma por escola), com o
**número de cada escola registrado como um `phone_number_id` distinto** dentro dela. Cada número
tem seu próprio **nome de exibição** (o nome da escola), sua própria **qualidade** e seu próprio
**tier de envio** — de modo que uma escola não contamina o limite da outra. Templates, cobrança e
credenciais ficam centralizados sob nossa conta, o que casa com o modelo de plano mensal/anual
por escola (§6e). A alternativa (Embedded Signup, cada escola dona da própria WABA) foi
descartada: transferiria a cobrança para a escola e inviabilizaria o onboarding assistido.

#### 9e.1 Mudanças necessárias para o multi-tenant funcionar

O adaptador atual é **single-tenant**: `MetaMessageChannel`
(`app/infrastructure/channel/meta_channel.py`) fixa o `phone_number_id` vindo da env no
construtor e **ignora o parâmetro `remetente`** da porta `MessageChannel` (o comentário no código
declara isso: na Meta a origem é fixada pela credencial). Com várias escolas, todo envio sairia
pelo número errado. São necessárias, nesta ordem:

1. **`Tenant.meta_phone_number_id`** (novo campo, migration `0024_tenant_meta_phone_number_id`
   encadeada no head `0023_remover_content_sid`): o identificador do número **na Meta**, que é
   o que a API exige na URL de envio. Não confundir com `Tenant.whatsapp_numero`, que é o E.164
   legível — os dois passam a coexistir, o E.164 para exibição/roteamento humano e o
   `phone_number_id` para a chamada da API. Deve ser **único entre escolas** (dois tenants com o
   mesmo id tornariam o inbound ambíguo), à semelhança do que `TenantRepository.por_whatsapp` já
   garante para o E.164.
2. **`MessageChannel.remetente` passa a ser honrado na Meta:** o `MetaMessageChannel` deixa de
   guardar um `phone_number_id` fixo e passa a **montar a URL por envio**
   (`/{phone_number_id}/messages`), usando o `remetente` recebido e caindo no
   `META_PHONE_NUMBER_ID` da env apenas como fallback. `EnviarBroadcast` **já** resolve o
   `Tenant` e repassa o remetente — a mudança é só do lado do adaptador, sem tocar em domínio
   ou casos de uso.
3. **Novo `TenantRepository.por_meta_phone_number_id`** para o roteamento inbound (ver abaixo).
4. **Inbound real no webhook da Meta** (hoje inexistente — `app/interfaces/api/webhook.py` só
   chama `RegistrarStatusEntrega`, e mensagens recebidas são descartadas). **É o que derruba o
   chatbot inteiro**: sem ele o produto só dispara, não atende. Pontos de atenção da API:
   - o payload é **JSON aninhado** (`entry[].changes[].value.messages[]`);
   - a Meta exige **`200 OK` imediato**; a resposta ao responsável **não vai no corpo do HTTP** e
     precisa ser **enviada ativamente** por uma segunda chamada à API, via
     `MessageChannel.enviar_texto` com o `remetente` da escola;
   - o **roteamento do tenant** sai de `value.metadata.phone_number_id`, resolvido pelo novo
     `por_meta_phone_number_id`. **Sem tenant de fallback:** número desconhecido deve ser
     **descartado com log**, nunca cair num tenant default (vazaria a conversa de uma escola
     para outra);
   - o mesmo POST carrega **mensagens e status de entrega** no mesmo envelope; os dois caminhos
     convivem no handler.
5. **Config** (`app/config.py`): `META_PHONE_NUMBER_ID` passa a ser **fallback**, não a fonte da
   verdade; `META_ACCESS_TOKEN` deve ser um token de **usuário do sistema** (o token da tela de
   Configuração da API expira em 24h e não serve para produção).

#### 9e.2 Autenticidade do webhook — ✅ implementado (27/jul/2026)

**A lacuna que existia:** o `POST /api/webhook/meta` **aceitava qualquer requisição**, sem
nenhuma verificação de origem. Com o endpoint público no Render a URL é descobrível, e qualquer
terceiro podia:

- **forjar status de entrega**, corrompendo a confirmação de recebimento (§9b) — uma não-entrega
  real mascarada como `delivered` **desliga justamente o alarme** que avisa a escola de que um
  aviso crítico não chegou;
- **forjar mensagens inbound** (assim que o item 4 acima existir), injetando conversas falsas em
  nome de qualquer telefone, poluindo o histórico/auditoria (§13) e **consumindo cota de LLM** de
  um tenant arbitrário.

**Como ficou** (`validar_assinatura_meta` em `app/infrastructure/security.py`, aplicado em
`app/interfaces/api/webhook.py`, coberto por `tests/test_seguranca.py`):

- valida o **`X-Hub-Signature-256`**: HMAC-SHA256 no formato `sha256=<hex>`, com o **app secret**
  da Meta como chave;
- calcula sobre os **bytes exatos** recebidos (`await request.body()`), **antes de qualquer parse
  de JSON** — reserializar o payload muda os bytes e invalidaria o HMAC. É o erro clássico dessa
  implementação;
- compara em **tempo constante** (`hmac.compare_digest`), nunca com `==`, para não vazar pelo
  tempo de resposta quantos bytes do prefixo estavam certos;
- só stdlib (`hmac`/`hashlib`), como o resto de `security.py`;
- configs **`META_APP_SECRET`** + **`META_VALIDATE_SIGNATURE`** (default `false` em dev,
  **`true` obrigatório em produção**);
- assinatura ausente ou inválida → **403 seco**, sem processar nada e **sem revelar a causa**
  (distinguir "faltou o cabeçalho" de "HMAC não bateu" ajudaria quem estivesse sondando).

O `GET` de verificação (`hub.challenge`) já compara o `hub.verify_token` com
`META_WEBHOOK_VERIFY_TOKEN` e está correto — mas o default `"changeme"` em `config.py`
**precisa ser trocado por um valor forte** em produção, senão o handshake é reproduzível por
qualquer um. O painel de §14 sinaliza esse caso.

#### 9e.3 Onboarding de uma nova escola (operação)

**Modelo adotado: a escola não configura nada.** Nós compramos o chip, colocamos num aparelho
nosso, recebemos o código de verificação e conduzimos todo o registro pelo nosso Business
Manager. A escola só recebe o número já operante. Isso elimina o principal ponto de atrito do
onboarding (depender da secretaria para ler um código que expira em minutos) e mantém a posse
do número — e portanto do canal — com a plataforma.

- **Uma escola nova NÃO exige uma WABA nova:** é mais um número na WABA existente. O limite
  documentado é de **20 números por WABA**; ao esgotar, cria-se **outra WABA sob o mesmo
  portfólio empresarial** (o portfólio comporta várias), sem trocar de conta nem refazer a
  verificação da empresa. Confira o limite vigente na documentação antes de planejar acima
  disso.
- **Qualidade e tier de envio são por número**, não por WABA: uma escola que gere bloqueios não
  derruba o limite das outras. É o que torna a WABA compartilhada segura.
- **Requisito duro do chip:** o número **não pode estar ativo em nenhum WhatsApp** (comum ou
  Business) no momento do registro, e depois de registrado na Cloud API **não volta** a
  funcionar no aplicativo. Por isso o chip é sempre **novo e dedicado**.
- **Caminho crítico do prazo:** o **nome de exibição** de cada número (o nome da escola, que os
  pais veem) passa por **revisão da Meta**, que é assíncrona. Dispare esse passo no início do
  onboarding, não no fim.
- **Automação (roadmap):** o registro de número é automatizável pela Graph API — criar/registrar
  o número na WABA, disparar o código de verificação e confirmá-lo, definir nome de exibição e
  assinar o webhook são todos endpoints da API, com o token de usuário do sistema. O que **não**
  é automatizável é o insumo físico: obter o chip e ler o SMS/ligação. Ou seja, dá para reduzir
  o onboarding a "cadastrar a escola no painel + digitar o código recebido", mas não a zero
  toque.

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
- [ ] Adaptador **Meta WhatsApp Cloud API** (outbound) com templates, cota e **fila**
  (throttling, retry com backoff e agendamento — §9a).
- [~] **Migração para a Meta Cloud API direta** (canal único desde 27/jul/2026, com a verificação
  da empresa aprovada). Ver §9e:
  - [x] **Validação de `X-Hub-Signature-256`** no webhook (§9e.2) — era **bloqueante para o
    go-live**: o endpoint aceitava qualquer POST, permitindo forjar status de entrega e
    (após o inbound) conversas falsas.
  - [x] Remoção completa da Twilio (adaptador, webhook, testes, `TWILIO_*`, `content_sid`).
  - [ ] `Tenant.meta_phone_number_id` + migration `0024` e
    `TenantRepository.por_meta_phone_number_id`.
  - [ ] `MetaMessageChannel` honrando o `remetente` (URL por envio) — hoje é single-tenant.
  - [ ] **Inbound** no `POST /api/webhook/meta` (hoje só trata status; o chatbot não atende)
    com resposta ativa e roteamento por `metadata.phone_number_id`.
  - [ ] Automação do registro de número na WABA pela Graph API (§9e.3).
- [x] **Canal Meta WhatsApp Cloud API** como canal único do produto, com a **assinatura
  `X-Hub-Signature-256`** validada no webhook. Ver §9c e §9e.2.
- [ ] **Inbound real do WhatsApp** pelo webhook da Meta (hoje só trata status de entrega) —
  sem ele o produto dispara mas não atende. Ver §9e.1.
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
  **back-end (FastAPI) → Render** (Auto-Deploy nativo no push à `main`);
  **painel admin (`web/`) → Vercel**, que consome a API do Render;
  **landing page (`site/`) → Cloudflare Pages**, via `.github/workflows/site.yml` (§9d).
  O CI (`.github/workflows/ci.yml`) roda **lint (ruff) + migrations (alembic upgrade head) +
  pytest** em PRs e na `main`, servindo de portão de qualidade antes do merge.
  > O `ruff` está fixado em `>=0.5,<0.16` no `backend/pyproject.toml`: sem teto, o CI
  > instalava a versão mais nova a cada execução e a 0.16.0 quebrou a build sem que o
  > código mudasse (358 dos 424 achados eram `B008`, o `Depends()` do FastAPI).

**Observabilidade / histórico** _(ver §13)_
- [x] **Histórico completo de mensagens em massa (broadcasts)** enviadas no admin da escola —
  lista os disparos com **template**, destinatários, **status de entrega** e data, e um detalhe
  por responsável (`ObterBroadcastDaEscola`, `web/app/admin/historico/disparos/`).
- [x] **Histórico completo de conversas do WhatsApp** (mensagens recebidas e respostas da LLM),
  consultável no admin da escola (`web/app/admin/historico/conversas/`).
- [x] **Log de auditoria de ações** — grava ações de **usuários logados** no painel (login,
  criação de usuário/grupo, disparo a grupo) **e** ações da **LLM** (cada atendimento), com
  quem/o quê/quando/payload. Base para rastreabilidade/compliance
  (`web/app/admin/historico/auditoria/`).

**Limpeza de UI (remoções)**
- [x] **Remover** a emissão de relatórios em **lista** de pais na seção "Salas e pais"
  (não faz sentido manter).
- [x] **Remover** o dropdown de seleção de escola dentro do **admin da escola**
  (tenant admin é amarrado a uma única escola — não faz sentido).

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
- [ ] **Histórico/ficha financeira da escola** no super admin:
  - Quando entrou (data de início).
  - Quando cancelou (se aplicável) e **motivo do cancelamento**.
  - Quanto pagou no **plano anual** e quanto paga no **plano mensal**.
  - **Métricas sugeridas (adicionais):** MRR/ARR e receita acumulada (LTV) por escola;
    plano atual e ciclo (mensal/anual); status de pagamento e histórico de faturas;
    data da próxima renovação; churn e motivo; uso vs. cota (broadcasts/mensagens no
    período); nº de usuários ativos, contatos e alunos; data do último acesso/atividade;
    health score (qualidade do número Meta + tier de envio).

---

## 13. Observabilidade / histórico (admin da escola)

Três visões consultáveis no painel da escola (e pelo super admin, via `_exige_acesso_tenant`),
sob a seção **HISTÓRICO** da sidebar (`web/app/admin/historico/`). Tudo escopado por `tenant_id`.

- **Histórico de conversas** (`/historico/conversas`): lista as conversas do WhatsApp e abre o
  diálogo completo (mensagens **recebidas** dos responsáveis + **respostas da LLM**, com as fontes
  RAG citadas). Reusa `ListarConversasDaEscola`/`ObterConversaDaEscola`
  (`GET /api/admin/escolas/{tenant_id}/conversas[/{conversa_id}]`).
- **Histórico de mensagens em massa** (`/historico/disparos`): lista os broadcasts com **template**,
  total de destinatários, **status de entrega** agregado e data; o detalhe mostra a entrega **por
  responsável** (nome, telefone, status `sent`/`delivered`/`read`/`failed`, atualizado em).
  `ListarBroadcastsDaEscola` resolve o nome do template em lote; `ObterBroadcastDaEscola` monta o
  detalhe (`GET /api/admin/escolas/{tenant_id}/broadcasts[/{broadcast_id}]`). Conecta-se à
  confirmação de recebimento (§9b: `.../nao-entregues`).
- **Auditoria de ações** (`/historico/auditoria`): log de **quem fez o quê e quando**, para
  rastreabilidade/compliance. A entidade `RegistroAuditoria` (`ator` ∈ {`usuario`, `llm`,
  `sistema`}, `acao`, `descricao`, `metadados` JSON) é persistida em `auditoria`
  (migration `0007_auditoria`) via porta `AuditLogRepository`. **Instrumentado:** ações de
  usuários logados no `app/interfaces/api/admin.py` (`login`, `usuario.criar`, `grupo.criar`,
  `broadcast.grupo.enviar`) e **ações da LLM** — `AtenderConversa` registra `llm.resposta` a cada
  atendimento (pergunta/resposta resumidas, fontes, documentos). Casos de uso
  `RegistrarAuditoria`/`ListarAuditoria` (`app/application/auditoria_use_cases.py`); auditar é
  **tolerante a falhas** (nunca derruba a ação auditada).
  Endpoint: `GET /api/admin/escolas/{tenant_id}/auditoria?limite=`.

---

## 14. Postura de segurança (auditoria interna do super admin)

Painel **exclusivo do super admin** (`/admin/seguranca`) que lista as **medidas protetivas** da
plataforma e o **status real de cada uma no ambiente em execução**. É material de **auditoria
interna** (sócios) — não é conteúdo para a escola nem peça de venda, e por isso a página
redireciona quem não é super admin.

- **Três status, não dois.** `ATIVA` (existe no código e a configuração não a enfraquece),
  `ATENCAO` (existe, mas está desligada ou com segredo default) e `PENDENTE` (ainda não
  implementada). A distinção é o ponto da tela: um relatório que só respondesse
  "implementado sim/não" esconderia exatamente o caso perigoso — a medida que existe no
  código e está desligada em produção.
- **Honestidade obrigatória.** Medida planejada e não implementada aparece como `PENDENTE`.
  Um painel de auditoria que dourasse a pílula não serviria para auditar nada. Hoje o
  `rate_limit_inbound` (limite de taxa por remetente no webhook) está nesse estado.
- **Cada medida declara o risco que cobre**, não só o que faz — é o que permite priorizar.
- **Nenhum segredo é exposto:** a API devolve apenas *se* um segredo continua com o valor de
  exemplo (`JWT_SECRET`, `META_WEBHOOK_VERIFY_TOKEN`), nunca o valor.

**Arquitetura.** O caso de uso `AvaliarPosturaSeguranca`
(`app/application/seguranca_use_cases.py`) **não lê variáveis de ambiente**: recebe um
`ConfiguracaoSeguranca` com sinais booleanos, montado na camada de interface a partir das
`Settings`. Assim a regra que classifica cada medida fica testável sem tocar em config, e o
domínio segue sem conhecer o framework. Value objects `MedidaSeguranca`/`PosturaSeguranca` +
enum `StatusMedida` em `entities.py`.

- **Endpoint:** `GET /api/admin/seguranca` (`app/interfaces/api/seguranca.py`, guarda
  `_exige_super_admin`).
- **Painel:** `web/app/admin/seguranca/` — contadores por status, faixa de veredito
  (`pronto_para_producao`) e as medidas agrupadas por categoria (Integridade de dados,
  Autenticação, Isolamento, Rastreabilidade, Exposição). Entrada na sidebar sob
  **ADMINISTRAÇÃO**, ao lado de "Escolas".
- **Testes:** `backend/tests/test_seguranca.py` cobre a validação de assinatura (incluindo
  corpo adulterado e segredo errado) e a classificação das medidas.
