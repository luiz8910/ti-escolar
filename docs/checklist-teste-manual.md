# Checklist de teste manual — TI-Escolar

> Roteiro de teste **manual** de ponta a ponta. Cobre as telas do painel (`web/`), o portal do
> professor, as rotas que **só existem na API** (fichas, matrícula, faltas, exportação, mediação)
> e o caminho real do WhatsApp (webhook da Meta).
>
> **Legenda:** `[ ]` a testar · `[x]` passou · `[!]` falhou (anote o que aconteceu) ·
> `[-]` não aplicável neste ambiente.
>
> **Ordem sugerida:** faça o bloco 0 (preparação) e o bloco 1 (fumaça). Depois os blocos 2–13 em
> qualquer ordem. **Deixe os blocos 14 (isolamento) e 15 (segurança negativa) por último** — eles
> criam uma segunda escola e sujam a base de propósito.

---

## 0. Preparação do ambiente

Ambiente alvo deste roteiro: **local via docker-compose** (com `SEED_DEMO=true`), que é o único
onde é seguro criar, quebrar e apagar dados. Onde o teste **só faz sentido em homolog/produção**
(WhatsApp real, e-mail real), está marcado com **🌐**.

- [ ] **0.1** `cp .env.example .env` e conferir as chaves do bloco de demonstração
      (`SEED_DEMO=true`, `APP_ENV=development`, `LLM_PROVIDER=fake`, `MESSAGE_CHANNEL=demo`).
- [ ] **0.2** `docker compose up --build` sobe os três serviços (`db`, `backend`, `web`) sem erro.
- [ ] **0.3** No log do backend: `alembic upgrade head` roda **sem "multiple heads"**, o bootstrap
      cria o super admin e o seed de demonstração é executado.
- [ ] **0.4** Painel responde em `http://localhost:3000`; API em `http://localhost:8000`.
- [ ] **0.5** `http://localhost:8000/docs` lista todos os routers (admin, cadastro, atendimentos,
      documentos, fichas, matrículas, faltas, impressão, mural, professor, webhook…).

### Credenciais e ids do seed

| O quê | Valor |
|---|---|
| Super admin | `admin@tiescolar.test` / `troque-esta-senha` (`SUPER_ADMIN_*`) |
| Admin da escola demo | `admin@escola-demo.test` / `escola123` (`DEMO_ADMIN_*`) |
| Professor demo | telefone `+5511977770001` / `prof123` (`DEMO_PROFESSOR_SENHA`) |
| Tenant demo | `00000000-0000-0000-0000-000000000001` |
| Responsável demo (mediação) | `+5511955550001` |

### Token para os testes de API (curl)

```bash
API=http://localhost:8000
TENANT=00000000-0000-0000-0000-000000000001

TOKEN=$(curl -s -X POST $API/api/admin/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@escola-demo.test","senha":"escola123"}' | jq -r .access_token)

SUPER=$(curl -s -X POST $API/api/admin/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@tiescolar.test","senha":"troque-esta-senha"}' | jq -r .access_token)
```

- [ ] **0.6** Os dois logins devolvem `access_token`, `expira_em` e `usuario`.

---

## 1. Fumaça (smoke)

- [ ] **1.1** `GET /health` responde `200`.
- [ ] **1.2** O campo `canal` do `/health` reflete o canal **efetivo**. Em local com
      `MESSAGE_CHANNEL=demo` deve dizer `demo`.
- [ ] **1.3** **Armadilha silenciosa:** com `MESSAGE_CHANNEL=meta` e `META_ACCESS_TOKEN` vazio, o
      `/health` traz `canal: "demo"` + `canal_configurado` + `canal_alerta`, e o boot loga em
      `error`. (Teste alterando o `.env` e reiniciando o backend.)
- [ ] **1.4** `GET /health/pronto` responde `200` com o banco no ar e **falha** com o banco parado
      (`docker compose stop db`) — enquanto o `/health` continua `200`.
- [ ] **1.5** `http://localhost:3000/` redireciona para `/admin` (o chat de demonstração **não
      existe mais**; se aparecer um simulador de WhatsApp, é regressão).
- [ ] **1.6** `POST /api/chat/mensagens` responde **404** (rota removida).

---

## 2. Autenticação e sessão

- [ ] **2.1** Login do admin da escola em `/admin/login` entra no painel.
- [ ] **2.2** Login do super admin entra e a sidebar mostra a seção **ADMINISTRAÇÃO** (Escolas,
      Segurança, Logs) — que **não** aparece para o admin da escola.
- [ ] **2.3** Senha errada → mensagem de credenciais inválidas, sem dizer se o e-mail existe.
- [ ] **2.4** O `localStorage` guarda o **token**, nunca a senha.
- [ ] **2.5** Apagar o token do `localStorage` e recarregar → volta para o login.
- [ ] **2.6** Chamar uma rota admin sem `Authorization` → **401**.
- [ ] **2.7** Chamar com um token adulterado (troque um caractere) → **401**.
- [ ] **2.8** Desativar o próprio usuário no banco e recarregar o painel → acesso negado na
      requisição seguinte (o token é revalidado no banco a cada request).
- [ ] **2.9** **Rate limit do login:** 11+ tentativas erradas seguidas → **429** com cabeçalho
      `Retry-After` (`RATE_LIMIT_LOGIN_TENTATIVAS=10`).
- [ ] **2.10** Login do professor em `/professor/login` com `+5511977770001` / `prof123` entra no
      portal; senha errada não entra; e o rate limit também vale aqui.

---

## 3. Super admin — escolas, licença e cobrança

- [ ] **3.1** `/admin/escolas` lista as escolas com totais (conversas, contatos, broadcasts).
- [ ] **3.2** **Criar escola** com nome, slug, WhatsApp, `meta_phone_number_id` e **telefone de
      contato** (este é obrigatório).
- [ ] **3.3** Slug duplicado é recusado.
- [ ] **3.4** **WhatsApp duplicado** entre escolas é recusado (tornaria o inbound ambíguo).
- [ ] **3.5** **`meta_phone_number_id` duplicado** é recusado; **vazio é permitido em mais de uma
      escola** (índice UNIQUE parcial).
- [ ] **3.6** Escola **sem `meta_phone_number_id`** aparece marcada com ⚠ na lista.
- [ ] **3.7** O WhatsApp é **normalizado para E.164** (digite `15 99753-6978` e confira o salvo).
- [ ] **3.8** Editar escola persiste as alterações; o detalhe `/admin/escolas/[tenantId]` reflete.
- [ ] **3.9** **Expediente** editável no cadastro (dias, início, fim, timezone) e o detalhe mostra
      a descrição legível.
- [ ] **3.10** **Bloquear escola** com motivo → badge muda; o admin daquela escola **não loga**
      (403 com o motivo); o super admin continua entrando.
- [ ] **3.11** Escola bloqueada **não dispara**: `/grupos/{id}/enviar` e `POST /api/broadcasts`
      recusam.
- [ ] **3.12** **Desbloquear** devolve o acesso.
- [ ] **3.13** **Cancelar escola** com motivo → mesmo bloqueio de acesso e disparo; `Reativar`
      desfaz.
- [ ] **3.14** **Definir licença** (plano mensal/anual, data de expiração, valores por ciclo) →
      badge mostra os dias para expirar.
- [ ] **3.15** Licença **expirada** aparece sinalizada.
- [ ] **3.16** **Ficha financeira** (detalhe da escola): dias de casa, MRR/ARR, receita acumulada,
      próxima renovação, uso (usuários/contatos/alunos/conversas/broadcasts) e health score.
- [ ] **3.17** **"Avisar vencimentos"** (`POST /api/admin/licencas/notificar-vencimento`) devolve a
      lista de escolas avisadas; com `EMAIL_PROVIDER=log` o e-mail aparece no log do backend.
- [ ] **3.18** 🌐 Com `EMAIL_PROVIDER=resend` + chave válida, o e-mail chega de verdade.
- [ ] **3.19** **Remover escola** apaga tudo em cascata (conversas, contatos, alunos, fichas,
      professores…) sem violar FK. Use uma escola de teste, **nunca a demo**.
- [ ] **3.20** Admin de escola tentando `GET /api/admin/escolas` → **403**.

---

## 4. Cadastro escolar

### 4.1 Pais / responsáveis e salas — `/admin/salas`

- [ ] **4.1.1** Criar sala ("6ª série C") e criar responsável (nome + telefone).
- [ ] **4.1.2** Telefone duplicado no mesmo tenant é recusado (único por `tenant_id + telefone`).
- [ ] **4.1.3** Vincular e desvincular responsável ↔ sala; um responsável pode estar em **mais de
      uma** sala.
- [ ] **4.1.4** **Relatório de pais da sala** abre e é **imprimível** (PDF pelo diálogo de
      impressão).
- [ ] **4.1.5** Editar e excluir responsável.
- [ ] **4.1.6** **Excluir sala com alunos** exige `mover_para` — a tela pede a série destino e
      permite **criar a série destino na hora**. Os alunos são **transferidos**, nunca apagados.
- [ ] **4.1.7** Excluir sala **vazia** funciona direto.
- [ ] **4.1.8** **Não existe** mais emissão de relatório em *lista* de pais (foi removida) — se
      aparecer, é regressão.

### 4.2 Cobertura de contatos (alerta + aviso ao professor)

- [ ] **4.2.1** A lista de turmas mostra o **badge ⚠** na turma que tem aluno sem responsável com
      telefone (o seed cria "Aluno Sem Contato" na primeira turma).
- [ ] **4.2.2** O detalhe da turma lista os alunos descobertos.
- [ ] **4.2.3** **Ex-alunos são ignorados** na cobertura: desative um aluno sem contato e o número
      cai.
- [ ] **4.2.4** Botão **"Notificar professor"** abre o modal, aceita WhatsApp + mensagem opcional e
      envia; em local (canal demo) confira no log/`DemoMessageChannel`.

### 4.3 Alunos — `/admin/alunos`

- [ ] **4.3.1** Cadastrar aluno com **série obrigatória**; sem série é recusado.
- [ ] **4.3.2** Vincular e desvincular responsáveis (N:N).
- [ ] **4.3.3** Filtrar por série.
- [ ] **4.3.4** Editar aluno (trocar série, mudar situação).
- [ ] **4.3.5** **"Excluir" é soft delete:** o aluno vira ex-aluno (`ativo=false`) com data e motivo
      — o registro **continua na base**.
- [ ] **4.3.6** **Reativar** aluno desfaz.
- [ ] **4.3.7** Desativar duas vezes **não reescreve** a data de saída.
- [ ] **4.3.8** Aluno de outra escola não é acessível pelo id (404/403).

### 4.4 Importação de alunos em massa

- [ ] **4.4.1** Card "Importar alunos em massa" → **upload** de `.csv` ou **colar texto**.
- [ ] **4.4.2** A **prévia** aparece em tabela e **nada é gravado** ainda (confira a lista de
      alunos antes de confirmar).
- [ ] **4.4.3** Telefones são normalizados para **E.164**.
- [ ] **4.4.4** Série inexistente vem com badge **"nova"**.
- [ ] **4.4.5** Linha inválida (sem nome, telefone impossível) vem marcada com erro.
- [ ] **4.4.6** Confirmar **sem** "criar séries ausentes" → as linhas de série nova são **ignoradas**
      e o resultado diz isso.
- [ ] **4.4.7** Confirmar **com** "criar séries ausentes" → as séries são criadas e os alunos entram.
- [ ] **4.4.8** **Dedupe:** um responsável cujo telefone já existe é **reaproveitado**, não duplicado.
- [ ] **4.4.9** Reimportar a mesma planilha não cria alunos em duplicidade sem aviso.

### 4.5 Professores — `/admin/professores`

- [ ] **4.5.1** Cadastrar professor (nome + telefone + senha do portal).
- [ ] **4.5.2** Telefone duplicado no tenant é recusado.
- [ ] **4.5.3** **Atribuir professor a uma série**; trocar o professor da série.
- [ ] **4.5.4** Uma série tem **no máximo um** professor; um professor pode ter **várias** séries
      (confira em "séries do professor").
- [ ] **4.5.5** Remover professor **desvincula** as séries (`professor_id` → `NULL`) e **não apaga**
      as séries.
- [ ] **4.5.6** Editar a senha do professor e conferir que o novo login funciona.

---

## 5. Conhecimento, instruções e conteúdo do bot

### 5.1 Base de conhecimento — `/admin/conhecimento`

- [ ] **5.1.1** Subir um documento (arquivo `.txt` ou colar texto) → aparece na lista de fontes.
- [ ] **5.1.2** O conteúdo é **fragmentado e indexado** (verifique a tabela `conhecimento`, ou
      pergunte algo do documento pelo inbound no bloco 8).
- [ ] **5.1.3** **Remover a fonte** apaga também os trechos indexados (a resposta do bot deixa de
      citá-la).
- [ ] **5.1.4** O conhecimento de uma escola **não** aparece para outra (ver bloco 14).

### 5.2 Instruções da escola — `/admin/prompt`

- [ ] **5.2.1** Editar e salvar o system prompt do tenant.
- [ ] **5.2.2** O texto salvo é recarregado ao voltar na página.
- [ ] **5.2.3** O prompt influencia a resposta do assistente (teste com uma instrução marcante,
      ex.: "sempre termine com 'Atenciosamente, Secretaria'").

### 5.3 Respostas rápidas — `/admin/respostas-rapidas`

- [ ] **5.3.1** A lista traz os **19 atalhos do seed**.
- [ ] **5.3.2** Criar atalho (chave + conteúdo); chave duplicada é recusada.
- [ ] **5.3.3** Editar um atalho **reindexa** (a resposta do bot passa a refletir o texto novo).
- [ ] **5.3.4** **Desativar** um atalho remove os trechos do índice.
- [ ] **5.3.5** Remover apaga o atalho e o conhecimento gerado por ele.

### 5.4 Avisos do dia — `/admin/avisos`

- [ ] **5.4.1** Criar aviso **sem janela** (ativo) → é anexado à resposta do bot para quem inicia
      conversa.
- [ ] **5.4.2** Aviso com `inicia_em` **no futuro** → **não** aparece.
- [ ] **5.4.3** Aviso com `expira_em` **no passado** → **não** aparece.
- [ ] **5.4.4** Aviso **inativo** → não aparece.
- [ ] **5.4.5** Editar e excluir aviso.

---

## 6. Disparos (outbound) e cota

### 6.1 Grupos e disparo — `/admin`

- [ ] **6.1.1** A página lista os grupos do seed ("Turma 5º A", "Pais do Fundamental I").
- [ ] **6.1.2** Criar grupo; adicionar e remover contatos.
- [ ] **6.1.3** **Barra de cota** mostra o consumo do dia (`GET /api/broadcasts/quota/{tenant}`).
- [ ] **6.1.4** **Disparar para o grupo** com o template do seed (`aviso_reuniao`) → resultado com o
      total de destinatários.
- [ ] **6.1.5** O disparo aparece em `/admin/historico/disparos`.
- [ ] **6.1.6** Escola **bloqueada/cancelada** não dispara (403).
- [ ] **6.1.7** Ao **estourar a cota diária** (`META_DAILY_TIER_LIMIT` baixo, ex.: `2`, e
      reiniciar), os excedentes ficam **enfileirados/recusados** conforme a política — e a barra
      acusa.
- [ ] **6.1.8** `POST /api/broadcasts` **sem token** → 401 (era rota pública, é regressão se voltar).
- [ ] **6.1.9** `POST /api/broadcasts` com token de **outra escola** no `tenant_id` → 403.
- [ ] **6.1.10** `GET /api/broadcasts/quota/{tenant}` de outra escola → 403.

### 6.2 Confirmação de recebimento (não-entrega)

- [ ] **6.2.1** `GET /api/admin/escolas/{tenant}/broadcasts/{id}/nao-entregues` responde sem erro.
- [ ] **6.2.2** Destinatário em `FALHOU` aparece imediatamente.
- [ ] **6.2.3** Destinatário em `ENVIADO` há mais de `apos_minutos` (use `?apos_minutos=0`) aparece.
- [ ] **6.2.4** Destinatário `ENTREGUE`/`LIDO` **não** aparece.
- [ ] **6.2.5** 🌐 Com o canal real, o webhook de `statuses` atualiza o status por `wamid`
      (§9b) — confira o detalhe do disparo mudando de `sent` para `delivered`/`read`.

### 6.3 Templates

- [ ] **6.3.1** O seed cria `aviso_reuniao` **aprovado** e `retomada_atendimento` **pendente**.
- [ ] **6.3.2** 🌐 Enviar com template **não aprovado** é recusado com erro explícito (não some).
- [ ] **6.3.3** `/admin/templates` lista os templates, marcando cada um como **Global** ou
      **Da escola**, com o status vindo da Meta.
- [ ] **6.3.4** **Novo template** → preencher nome (o nome *exato* na Meta, ex.:
      `retomada_atendimento`), idioma `pt_BR`, categoria e corpo → **Enviar para aprovação**.
      O template aparece na lista como pendente.
- [ ] **6.3.5** **Sincronizar com a Meta** atualiza os status sem precisar do webhook — é a
      saída quando o `message_template_status_update` não está assinado no console.
- [ ] **6.3.6** O status é **por conta (WABA)**, não global: um template aprovado na conta A
      não aparece como aprovado para uma escola cuja conta é a B. Ver §9a-ter.
- [ ] **6.3.7** **Excluir** remove o template daqui **e da Meta** — confirme na Meta, porque
      um "removido" que só apaga o registro local deixa lixo na conta.
- [ ] **6.3.8** 🌐 **Replicar** um template global espalha-o pelas contas cadastradas.
- [ ] **6.3.9** A tela de disparo (§6.1.4) oferece **apenas os aprovados na conta daquela
      escola**, com um campo por variável do corpo — e o número de campos bate com o número
      de `{{n}}` do template.

---

## 7. Portal do professor — `/professor`

- [ ] **7.1** **Mural:** os recados da secretaria aparecem; **confirmar leitura** ("ticado")
      funciona e não desfaz sozinho ao recarregar.
- [ ] **7.2** **Solicitar impressão:** enviar com cópias, colorido, frente e verso e observação →
      aparece na fila da secretaria (`/admin/impressao`).
- [ ] **7.3** **Falar com a escola:** abrir solicitação escolhendo a categoria (`secretaria`,
      `gestao`, `pedagogico`) → aparece em `/admin/solicitacoes` com a categoria certa.
- [ ] **7.4** A lista "minhas solicitações" mostra o **status** e a **resposta** da escola quando ela
      responde.
- [ ] **7.5** **Mensagens dos responsáveis (mediação):** a thread com `+5511955550001` abre;
      responder envia **pelo número da escola** e registra a mensagem.
- [ ] **7.6** O número pessoal do professor **não** aparece em nenhum lugar da conversa do
      responsável.
- [ ] **7.7** **Avisar falta** (`POST /api/professor/faltas`) cria o aviso — confira via API
      (`GET /api/admin/faltas/tenant/{tenant}`), pois ainda **não há tela** para faltas.
- [ ] **7.8** Professor **sem token** em `/api/professor/*` → 401.
- [ ] **7.9** Professor de uma escola **não** vê recado/solicitação de outra.

---

## 8. WhatsApp inbound (webhook da Meta)

Em local, simule o webhook com curl (com `META_VALIDATE_SIGNATURE=false`). O `phone_number_id`
deve ser o cadastrado na escola demo.

```bash
curl -s -X POST $API/api/webhook/meta -H 'Content-Type: application/json' -d '{
 "entry":[{"changes":[{"value":{
   "metadata":{"phone_number_id":"SEU_PHONE_NUMBER_ID"},
   "messages":[{"id":"wamid.TESTE1","from":"5511955550001","type":"text",
                "text":{"body":"Qual o horário da secretaria?"}}]
 }}]}]}'
```

- [ ] **8.1** **Handshake:** `GET /api/webhook/meta?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=123`
      devolve `123`; com token errado, **não** devolve.
- [ ] **8.2** Mensagem de texto é atendida: a resposta aparece em `/admin/historico/conversas`.
- [ ] **8.3** O `from` sem `+` é **normalizado para E.164** — a mensagem cai na **mesma conversa**
      do contato já cadastrado, não numa conversa nova.
- [ ] **8.4** **Roteamento por escola:** um `phone_number_id` **desconhecido** é **descartado com
      log** e **não** cai em nenhum tenant.
- [ ] **8.5** **Idempotência:** reenviar o **mesmo `wamid`** não gera segunda resposta nem segunda
      chamada de LLM (confira `inbound_atendimento` e `/admin/logs`).
- [ ] **8.6** **Rate limit do inbound:** mais de `RATE_LIMIT_INBOUND_MENSAGENS` do mesmo telefone na
      janela → mensagem descartada, mas o webhook **continua respondendo 200** (nunca 429 para a
      Meta).
- [ ] **8.7** **Mensagem + status no mesmo envelope** são tratados os dois.
- [ ] **8.8** **Limite de caracteres (§G1):** mensagem acima de `MENSAGEM_PAI_MAX_CHARS` (1000) →
      o bot pede objetividade **sem** chamar a LLM.
- [ ] **8.9** **Aviso do dia** vigente é anexado à resposta de quem inicia conversa.
- [ ] **8.10** A resposta **cita a fonte** quando veio do RAG.
- [ ] **8.11** **Áudio** é ignorado com log (não quebra o webhook).
- [ ] **8.12** A ação da LLM é auditada (`llm.resposta`) em `/admin/historico/auditoria`.

### 8.13 Assinatura do webhook (com `META_VALIDATE_SIGNATURE=true`)

- [ ] **8.13.1** `POST` **sem** `X-Hub-Signature-256` → **403 seco**, sem processar.
- [ ] **8.13.2** `POST` com assinatura **inválida** → 403, e a resposta **não diz** qual foi o
      problema.
- [ ] **8.13.3** `POST` com assinatura **válida** (HMAC-SHA256 do corpo bruto com o app secret) →
      processa normalmente.
- [ ] **8.13.4** Corpo **adulterado** depois de assinado → 403.

---

## 9. Atendimento humano — `/admin/atendimentos`

- [ ] **9.1** **O assistente nunca encaminha na primeira mensagem** — mande uma pergunta difícil
      logo de cara e confirme que ele tenta responder.
- [ ] **9.2** Depois de ≥2 respostas do assistente, ao desistir ele **oferece** ("quer que eu chame
      alguém da secretaria?") — e o atendimento fica em `oferecido`, **não** na fila.
- [ ] **9.3** O responsável diz **"sim"** → o atendimento entra na fila (`aberto`) e aparece no
      painel.
- [ ] **9.4** **Pedido explícito** ("quero falar com uma pessoa") pula a oferta.
- [ ] **9.5** Com atendimento na fila, o assistente **cala**: a mensagem seguinte do responsável é
      só registrada, **sem resposta automática** (conta como `silenciadas` nos logs, não como falha).
- [ ] **9.6** **Assumir** o atendimento; um **segundo atendente** é recusado no mesmo caso.
- [ ] **9.7** **Responder** pelo painel → a mensagem sai pelo número da escola e entra na mesma
      conversa como autor `atendente` com o nome de quem respondeu.
- [ ] **9.8** **Resolver** e **reabrir** funcionam.
- [ ] **9.9** **Badge de contagem** na sidebar reflete a fila (atualiza em ~20s).
- [ ] **9.10** **Fora do expediente:** mande mensagem fora do horário da escola → o atendimento
      **entra na fila mesmo assim**, com selo de fora do expediente, e o que se promete ao
      responsável é o **próximo dia útil**.
- [ ] **9.11** **A armadilha do sábado:** fora do expediente numa sexta à noite, o assistente não
      promete "amanhã".
- [ ] **9.12** **Janela de 24h:** o contador aparece na tela; com a última mensagem do responsável
      há mais de 24h, responder **exige template**.
- [ ] **9.13** Sem `TEMPLATE_RETOMADA_ATENDIMENTO` aprovado, a resposta fora da janela é **recusada
      com erro explícito** (não some silenciosamente).
- [ ] **9.14** **Oferta vencida:** oferta com mais de `OFERTA_VALIDA_HORAS` (24) vira `descartado` e
      **não** autoriza encaminhamento direto depois.
- [ ] **9.15** As ações da secretaria (`atendimento.assumir` / `.responder` / `.resolver`) aparecem
      na auditoria.
- [ ] **9.16** Atendimento de uma escola **não** aparece para a outra.

---

## 10. Documentos recebidos — `/admin/documentos`

Simule pelo webhook um envelope de `image` ou `document` (com `media_id`).

- [ ] **10.1** Imagem enviada pelo responsável aparece na lista com status **"recebido"**.
- [ ] **10.2** PDF idem.
- [ ] **10.3** O arquivo entra **no fio da conversa** — e continua aparecendo lá mesmo se o
      download falhar (simule derrubando a Graph API/token).
- [ ] **10.4** A **confirmação** "recebemos o seu arquivo" é enviada **mesmo com a conversa em
      atendimento humano**.
- [ ] **10.5** **Dedupe por `media_id`:** o mesmo arquivo reentregue não vira dois registros.
- [ ] **10.6** **MIME fora da allowlist** (ex.: `.exe`, `.zip`) é recusado — nada entra no banco.
- [ ] **10.7** **Arquivo acima de 16 MB** é recusado (tanto pelo `content-length` declarado quanto
      pelo tamanho real).
- [ ] **10.8** **Áudio** não vira documento.
- [ ] **10.9** A **categoria sugerida** aparece a partir da legenda ("segue o atestado" → atestado)
      e fica **separada** da confirmada.
- [ ] **10.10** **Classificar** o documento (categoria + vincular a um aluno + status
      `processado`/`descartado`).
- [ ] **10.11** O filtro padrão da tela é **"a conferir"**.
- [ ] **10.12** **Baixar** o arquivo funciona, responde com `no-store` e **exige token** (abrir a URL
      sem sessão não entrega o arquivo).
- [ ] **10.13** O download aparece na auditoria como `documento.baixar`.
- [ ] **10.14** **Expurgo** (`POST /api/admin/documentos/expurgar`, super admin) apaga **bytes e
      metadado** dos vencidos.
- [ ] **10.15** Baixar um documento **já expurgado** dá erro tratado (não 500).
- [ ] **10.16** Documento de uma escola não é acessível pela outra.
- [ ] **10.17** A **política de privacidade** (`site/privacidade/`) declara a categoria e o prazo de
      retenção.

---

## 11. Comunicação interna e impressão (secretaria)

### 11.1 Canal do professor — `/admin/solicitacoes`

- [ ] **11.1.1** As solicitações abertas pelo professor aparecem com **categoria** e **status**.
- [ ] **11.1.2** Filtrar por categoria e por status.
- [ ] **11.1.3** Responder a solicitação → o professor vê a resposta no portal.
- [ ] **11.1.4** Mudar o status (`em_andamento`, `resolvida`, `cancelada`).
- [ ] **11.1.5** **Notificar o professor por WhatsApp** dispara pelo canal (confira no log em local).

### 11.2 Mural — `/admin/mural`

- [ ] **11.2.1** Publicar recado → aparece no portal do professor.
- [ ] **11.2.2** A tela mostra **quem leu / quem não leu**.
- [ ] **11.2.3** **Re-notificar não-lidos** envia WhatsApp só para quem não leu.
- [ ] **11.2.4** Excluir recado.

### 11.3 Fila de impressão — `/admin/impressao`

- [ ] **11.3.1** A solicitação do professor chega na fila como `pendente`, com cópias/cor/frente e
      verso/observação.
- [ ] **11.3.2** Avançar o status: `em_processo` → `concluida`.
- [ ] **11.3.3** `cancelada` funciona e sai das contas do relatório.
- [ ] **11.3.4** Excluir solicitação.

### 11.4 Cotas e relatório — `/admin/impressao/relatorio`

- [ ] **11.4.1** Definir a **franquia mensal** do professor (o seed cria 3.000).
- [ ] **11.4.2** `limite_mensal <= 0` significa **sem limite** e a tela mostra isso.
- [ ] **11.4.3** O relatório por competência (`YYYY-MM`) agrega as solicitações **não canceladas**
      por professor.
- [ ] **11.4.4** Quem passou da franquia é sinalizado como **excedido**.
- [ ] **11.4.5** Trocar a competência muda os números.
- [ ] **11.4.6** Remover a cota de um professor.

---

## 12. Progressão de série — `/admin/progressao`

> Faça **por último** dentro do bloco de cadastro: ele muda a série de todos os alunos.

- [ ] **12.1** **Prévia/execução** de `promover` move os alunos **ativos** para a série seguinte.
- [ ] **12.2** Alunos da **última série** com `destino=None` viram **ex-alunos**.
- [ ] **12.3** **Ex-alunos não são promovidos** de novo.
- [ ] **12.4** `inativar-responsaveis` inativa **apenas** quem tem **todos** os alunos como
      ex-alunos.
- [ ] **12.5** Responsável com **ao menos um aluno ativo** continua ativo.
- [ ] **12.6** Responsável **sem nenhum vínculo** não é tocado.
- [ ] **12.7** Rodar duas vezes é **idempotente** (não muda nada na segunda).

---

## 13. Funcionalidades sem tela (só API)

> Estas existem no back-end e **não têm página no painel**. Testar por curl/`/docs`.
> Se alguma ganhar tela, mover para o bloco correspondente.

### 13.1 Ficha de matrícula (`/api/admin/fichas`)

- [ ] **13.1.1** `POST /api/admin/fichas` grava a ficha do aluno (upsert 1:1).
- [ ] **13.1.2** **`cor_raca` é obrigatório** — sem ele, é recusado.
- [ ] **13.1.3** Os campos sensíveis persistem: NIS/Bolsa Família, deficiência, laudo/CID,
      restrição alimentar, alergia, autorizações (van, retirada, imagem).
- [ ] **13.1.4** `dados_extra` aceita campos livres da escola.
- [ ] **13.1.5** `GET /fichas/aluno/{aluno_id}` devolve; `DELETE` remove.
- [ ] **13.1.6** **Leitura por IA:** `POST /fichas/importar/previa` com um texto de ficha devolve os
      campos estruturados **sem persistir**; `.../confirmar` grava.
- [ ] **13.1.7** A prévia é **validada em código** — um campo inventado pela LLM não passa.
- [ ] **13.1.8** Ficha de aluno de outra escola → 403/404.

### 13.2 Matrícula self-service (`/api/admin/matriculas`)

- [ ] **13.2.1** `POST /matriculas/iniciar` cria a solicitação e devolve a **lista de documentos
      exigidos**.
- [ ] **13.2.2** É **idempotente por telefone** (chamar de novo não duplica).
- [ ] **13.2.3** `POST /{id}/documentos` registra os anexos e move para `documentos_enviados`.
- [ ] **13.2.4** `PUT /{id}/status` conduz até `concluida` / `cancelada`.
- [ ] **13.2.5** Listagem por tenant não vaza para outra escola.

### 13.3 Faltas e eventual (`/api/admin/faltas`)

- [ ] **13.3.1** `POST /faltas` (ou pelo portal do professor) cria com status `aberta`.
- [ ] **13.3.2** `POST /{id}/chamar-eventual` envia o texto **pelo número da escola** para os
      candidatos e registra `eventuais_chamados`.
- [ ] **13.3.3** `POST /{id}/confirmar` → `coberta`.
- [ ] **13.3.4** `POST /{id}/cancelar` → `cancelada`.
- [ ] **13.3.5** Remover o professor **não apaga** a falta (`professor_id` → `NULL`).

### 13.4 Exportação legal de conversa

- [ ] **13.4.1** `GET /api/admin/escolas/{tenant}/conversas/{id}/exportar` devolve o documento com
      **cabeçalho institucional** e marca de exportação.
- [ ] **13.4.2** `?inicio=&fim=` recorta o período.
- [ ] **13.4.3** Exportar conversa de **outra escola** → 403.

### 13.5 Mediação pelo admin (`/api/admin/mediacao`)

- [ ] **13.5.1** `POST` registra mensagem **recebida do responsável** e ela aparece no portal do
      professor.
- [ ] **13.5.2** `GET` acompanha a thread pelo admin.

---

## 14. Multi-tenant — isolamento entre escolas

> Crie uma **segunda escola** (com admin próprio) antes deste bloco.

- [ ] **14.1** Admin da escola A **não** lista pais, salas, alunos, professores da escola B.
- [ ] **14.2** Trocar o `tenant_id` na URL/corpo para o da escola B → **403** (não 200 vazio).
- [ ] **14.3** Conversas, atendimentos, documentos e disparos não cruzam.
- [ ] **14.4** Base de conhecimento e system prompt não cruzam — o bot da escola A **não** responde
      com o conhecimento da B.
- [ ] **14.5** Auditoria e histórico são escopados por escola.
- [ ] **14.6** O **super admin** enxerga as duas.
- [ ] **14.7** Editar um usuário **não** permite mudar `papel` nem `tenant_id` (um admin de escola
      não se promove a super admin).

---

## 15. Segurança, erros e resiliência

### 15.1 Painel de segurança — `/admin/seguranca` (super admin)

- [ ] **15.1.1** Abre para o super admin e **redireciona** quem não é.
- [ ] **15.1.2** Mostra os quatro status (`ATIVA`, `ATENCAO`, `PENDENTE`, `NAO_APLICAVEL`) e os
      contadores.
- [ ] **15.1.3** **Nenhum segredo é exposto** — só *se* continua com o valor de exemplo.
- [ ] **15.1.4** Com `JWT_SECRET` default → medida em `ATENCAO`.
- [ ] **15.1.5** Com `META_WEBHOOK_VERIFY_TOKEN=changeme` → `ATENCAO`.
- [ ] **15.1.6** Com `SEED_DEMO=true` + `APP_ENV=production` → `seed_producao` em `ATENCAO`.
- [ ] **15.1.7** Com `MESSAGE_CHANNEL=meta` sem token → `canal_efetivo` em `ATENCAO`; rodando em
      `demo` de propósito → `ATIVA` (não é alarme falso).
- [ ] **15.1.8** Com `BACKEND_CORS_ORIGINS=*` → CORS sinalizado.
- [ ] **15.1.9** O **checklist de pré-deploy** aparece com a numeração 1–10 da §15 do CLAUDE.md,
      **na mesma ordem**.
- [ ] **15.1.10** `pronto_para_producao` só é verdadeiro quando **medidas e checklist** estão ok.

### 15.2 Logs — `/admin/logs` (super admin)

- [ ] **15.2.1** Abre só para super admin.
- [ ] **15.2.2** Resumo traz erros, alertas, requisições, taxa de erro, latência média e **p95**,
      rotas mais lentas e erros mais frequentes.
- [ ] **15.2.3** A **fila de inbound** mostra respondidas / em atendimento / falhas.
- [ ] **15.2.4** Listagem paginada com filtro por **nível**, **módulo** e **texto**.
- [ ] **15.2.5** O **traceback** expande.
- [ ] **15.2.6** Provoque um erro (rota inexistente do backend, ou derrube o banco) e confirme que
      ele **aparece** no painel.
- [ ] **15.2.7** `saudavel` fica **falso** com atendimento falho, mesmo sem erro HTTP.
- [ ] **15.2.8** **Conhecido / ⚠️:** não existe **alerta ativo** — ninguém é avisado sem abrir a
      tela. Confirmar que a tela não promete o contrário.

### 15.3 Erros e correlação

- [ ] **15.3.1** Rota inexistente no painel → tela **404 própria** (`not-found.tsx`).
- [ ] **15.3.2** Erro de runtime no front → tela de erro própria com **código de correlação** para o
      suporte (a mensagem técnica vai só para o console).
- [ ] **15.3.3** Erro 500 na API devolve o **id de correlação** no corpo **e** no cabeçalho.
- [ ] **15.3.4** O `X-Request-Id` enviado pelo cliente é **herdado**, não substituído.
- [ ] **15.3.5** **Nenhum traceback** vaza no corpo da resposta.
- [ ] **15.3.6** Com o banco fora do ar, o painel mostra erro tratado — não tela branca.

### 15.4 Entrada e injeção

- [ ] **15.4.1** Enviar `'; DROP TABLE alunos; --` como nome de aluno → é gravado como **texto**, nada
      quebra.
- [ ] **15.4.2** Enviar `<script>alert(1)</script>` em um campo e conferir que aparece **escapado**
      na tela (sem alerta).
- [ ] **15.4.3** UUID inválido na URL → 422 tratado, não 500.
- [ ] **15.4.4** Campo obrigatório ausente → 422 com a mensagem do Pydantic.

### 15.5 CORS

- [ ] **15.5.1** Requisição de uma origem **não listada** em `BACKEND_CORS_ORIGINS` é bloqueada
      (o header `Access-Control-Allow-Origin` **não** ecoa a origem forjada).
- [ ] **15.5.2** Com `*`, `allow_credentials` fica **desligado**.

---

## 16. Interface (transversal)

- [ ] **16.1** Sidebar: todas as entradas navegam para a página certa e o item **ativo** é
      destacado.
- [ ] **16.2** Não existe mais o **dropdown de escola** dentro do admin da escola (é regressão se
      voltar).
- [ ] **16.3** Não existe mais o link **"Ver demo do chat"**.
- [ ] **16.4** Em **mobile** (≤ 400px) o menu abre/fecha e nenhuma tela **rola na horizontal**.
- [ ] **16.5** Tabelas largas (alunos, logs, disparos) rolam **dentro do próprio contêiner**.
- [ ] **16.6** Toasts de sucesso e de erro aparecem nas ações principais.
- [ ] **16.7** Estados **vazios** têm mensagem (não tabela em branco).
- [ ] **16.8** Estados de **carregando** aparecem nas listagens.
- [ ] **16.9** **Paginação** funciona em conversas, disparos, auditoria, logs, alunos, pais e
      atendimentos (avançar, voltar e o total).
- [ ] **16.10** Tema claro e escuro legíveis (se aplicável).

---

## 17. Landing page — `site/` 🌐

- [ ] **17.1** `tiescolar.com.br` no ar (apex e `www`).
- [ ] **17.2** Páginas `/`, `/privacidade/`, `/termos/` e a 404 abrem.
- [ ] **17.3** **Razão social e CNPJ** visíveis no rodapé de todas as páginas.
- [ ] **17.4** A política de privacidade cita a categoria de dado sensível e o **prazo de retenção**
      dos documentos.
- [ ] **17.5** A página **não faz requisição a domínio externo** (aba Network do DevTools: zero
      terceiros — fontes são auto-hospedadas).
- [ ] **17.6** `robots.txt` e `sitemap.xml` respondem.
- [ ] **17.7** Nenhum campo institucional aparece como `PENDENTE` na tela.

---

## 18. Produção / homolog (pré-deploy) 🌐

- [ ] **18.1** CI verde na `main` nos três jobs (backend, `web/`, `site/`).
- [ ] **18.2** **Render:** deploy manual disparado após o merge (o serviço **não** tem auto-deploy)
      e o commit publicado é o da `main`.
- [ ] **18.3** `GET /health` e `GET /health/pronto` respondem `200` em homolog.
- [ ] **18.4** `/health` reporta `canal: "meta"` — não `demo`.
- [ ] **18.5** `META_VALIDATE_SIGNATURE=true` e `POST` no webhook sem assinatura → **403**.
- [ ] **18.6** `META_WEBHOOK_VERIFY_TOKEN` **não** é `changeme`.
- [ ] **18.7** `JWT_SECRET` trocado.
- [ ] **18.8** `SEED_DEMO=false` em produção — e as **senhas do `.env.example` não autenticam**.
- [ ] **18.9** `BACKEND_CORS_ORIGINS` com o domínio real do painel, sem `*`.
- [ ] **18.10** A **WABA está inscrita no app** (`POST /{waba-id}/subscribed_apps`) — sem isso o
      inbound não chega e nada dá erro.
- [ ] **18.11** O app está **"Ao vivo"** na Meta (app não publicado só recebe webhook de teste).
- [ ] **18.12** **Conversa real de ponta a ponta:** mandar WhatsApp para o número da escola →
      resposta chega → a conversa aparece em `/admin/historico/conversas`.
- [ ] **18.13** **Outbound real:** pagamento configurado na WABA + template aprovado → disparo
      chega no celular e o status vira `delivered`.
- [ ] **18.14** O `postura_ambiente.py` (workflow LGPD) roda sem regressão.
- [ ] **18.15** **Ensaio de rollback** conforme `docs/runbook-rollback.md` — incluindo o caso da
      migration (lembrar que o `CMD` roda `alembic upgrade head` a cada restart).

---

## Registro de execução

| Data | Ambiente | Quem testou | Blocos cobertos | Falhas encontradas |
|---|---|---|---|---|
|  |  |  |  |  |
