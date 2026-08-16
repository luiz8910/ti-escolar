# Canal de mensagens — Meta WhatsApp Cloud API

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

## 9. Canal de mensagens

A porta **`MessageChannel`** cobre **inbound** (receber/responder) e **outbound** (disparo ativo).

- **Único canal real:** adaptador **Meta WhatsApp Cloud API**, cobrindo **inbound** pelo
  webhook (§9c, §9e.1) e **outbound** por template (§9a).
- **`DemoMessageChannel`:** registra os envios em memória. É o canal de **desenvolvimento
  local e de teste** — sem token, sem rede —, e o fallback silencioso de `criar_canal` que
  `canal_efetivo` existe para acusar (§9c). Não é mais o canal de nenhuma tela.

---

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
  `MessageChannel` sobre a Graph API (`Authorization: Bearer`). A URL é montada **por envio**
  (`/{phone_number_id}/messages`) a partir do `remetente` recebido — é assim que cada escola
  dispara pelo **seu** número (§9e.1) —, com o `META_PHONE_NUMBER_ID` da env só como fallback.
  Retorna o `wamid` como id externo, que é o que liga o envio ao status de entrega (§9b).
  Cobre texto livre (só dentro da janela de 24h), **template** (`nome` + `idioma` + parâmetros
  de body) e documento. Cota e throttling ficam nos casos de uso, não no adaptador.
- **Webhook** (`app/interfaces/api/webhook.py`, `/api/webhook/meta`): o `GET` responde ao
  handshake (`hub.challenge`) conferindo o `hub.verify_token`. O `POST` trata os **três**
  caminhos que a Meta empacota no mesmo envelope: os **status de entrega**, aplicados aos
  destinatários dos broadcasts via `RegistrarStatusEntrega`; as **mensagens recebidas**,
  roteadas para o chatbot por `ProcessarInboundMeta` — a escola sai do
  `value.metadata.phone_number_id` e a resposta é **enviada ativamente** por uma nova chamada à
  API (a Meta não aceita resposta no corpo do webhook); e a **revisão de template**
  (`message_template_status_update` / `template_category_update`), aplicada ao catálogo por
  `AtualizarStatusTemplateMeta` (§9a-bis). Esta última é a **única leitura do produto que
  ignora `tenant_id`** — templates são da WABA e o evento não traz escola nenhuma —, e pode
  fazê-lo porque o remetente já foi provado pela assinatura HMAC. Ver §9e.1.
- **Autenticidade do webhook:** todo `POST` é validado pelo **`X-Hub-Signature-256`**
  (HMAC-SHA256 do **corpo bruto** com o app secret, comparação em tempo constante — só stdlib,
  `app/infrastructure/security.py · validar_assinatura_meta`) quando
  `META_VALIDATE_SIGNATURE=true`. Assinatura ausente/ inválida → **403 seco**, sem processar e
  sem revelar a causa. Ver §9e.2 para o porquê disso ser bloqueante.
- **Config** (`.env`): `META_PHONE_NUMBER_ID` (fallback), `META_ACCESS_TOKEN`
  (token de **usuário do sistema** — o da tela de Configuração da API expira em 24h),
  `META_WEBHOOK_VERIFY_TOKEN`, `META_DAILY_TIER_LIMIT`, `META_APP_SECRET` e
  `META_VALIDATE_SIGNATURE`. A fábrica `criar_canal` (`app/infrastructure/factories.py`)
  escolhe o adaptador pelo `MESSAGE_CHANNEL` (`demo` | `meta`).
- **`MESSAGE_CHANNEL=meta` exige `META_ACCESS_TOKEN`.** Sem o token, `criar_canal` devolve o
  `DemoMessageChannel` **sem erro nenhum** — o processo sobe e o WhatsApp não está no ar. É a
  falha mais perigosa do go-live porque é muda nas duas pontas: o inbound é roteado, chama a
  LLM (custo real) e marca `RegistroAtendimento` como `concluida`, mas a resposta vai para
  uma lista em memória e o responsável nunca é atendido — sem erro no painel de Logs; e o
  outbound grava `demo-N` como id externo, que jamais casa com um `wamid`, deixando todo
  destinatário preso em `ENVIADO` e fazendo a não-entrega reativa (§9b) acusar a escola
  inteira. Por isso **`canal_efetivo(settings)` é a fonte única** de qual adaptador está em
  uso: `criar_canal` decide por ela, o `/health` e o `/admin/seguranca` reportam por ela
  (§14, §16), e o boot loga em `error` quando o pedido diverge do efetivo.
- **Templates:** identificados por `nome` + `idioma`, que precisam bater com o template
  aprovado no WhatsApp Manager. Não há mais `content_sid` (era o `ContentSid` da Content API da
  Twilio; removido na migration `0023_remover_content_sid`).
- **Go-live em produção:** `docs/producao-whatsapp.md` traz o checklist completo (WABA de
  produção, número por escola, token permanente, webhooks, templates, limites/tiers).

---

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

#### 9e.1 Inbound real + multi-tenant de envio — ✅ implementado (27/jul/2026)

**O que existia:** o produto **disparava mas não atendia**. O `POST /api/webhook/meta` só
chamava `RegistrarStatusEntrega` e **descartava as mensagens recebidas**; e o
`MetaMessageChannel` fixava o `phone_number_id` da env no construtor, **ignorando o
`remetente`** da porta `MessageChannel` — com várias escolas, todo envio sairia pelo mesmo
número. Como ficou:

1. **`Tenant.meta_phone_number_id`** (migration `0024_tenant_meta_phone_number_id`): o
   identificador do número **na Meta**, que é o que a Graph API exige na URL de envio e o que o
   webhook devolve em `value.metadata.phone_number_id`. Coexiste com `Tenant.whatsapp_numero`
   (o mesmo número em E.164 legível, para exibição). **Único entre escolas** — duas escolas com
   o mesmo id tornariam o inbound ambíguo —, validado em `CriarEscola`/`AtualizarEscola`
   (`normalizar_meta_phone_number_id` + `_validar_meta_phone_number_id_unico`) e no banco por um
   **índice UNIQUE parcial** (`WHERE meta_phone_number_id <> ''`): o default é `''`, e um UNIQUE
   simples só permitiria **uma** escola ainda sem número registrado.
2. **`Tenant.remetente_canal`** (propriedade de domínio): resolve o `remetente` que vai para o
   canal — o `meta_phone_number_id` tem precedência, o E.164 é o fallback de quem ainda não tem
   id. É o que `EnviarBroadcast`, `ChamarEventual` (§I1) e a mediação pai↔professor (§A3) passam
   ao `MessageChannel`.
3. **`MetaMessageChannel` honra o `remetente`:** a URL é montada **por envio**
   (`/{phone_number_id}/messages`), com o `META_PHONE_NUMBER_ID` da env só como fallback. Um
   `remetente` em E.164 (escola sem id cadastrado) **não** vira caminho de URL: cai no padrão e
   **loga um aviso**, porque nesse estado o disparo sai do número errado.
4. **`TenantRepository.por_meta_phone_number_id`** — a busca que roteia o inbound.
5. **Inbound real** (`ProcessarInboundMeta`, `app/application/inbound_use_cases.py`), chamado
   pelo webhook **depois** da validação de assinatura (§9e.2):
   - percorre o envelope aninhado (`entry[].changes[].value.messages[]`) e **convive** com o
     caminho de status de entrega, que chega no mesmo POST;
   - **roteia pelo `value.metadata.phone_number_id`**. **Sem tenant de fallback:** um número
     sem escola cadastrada é **descartado com log** — cair num tenant default jogaria a conversa
     de um responsável na caixa de outra escola;
   - **normaliza o `from`** para E.164 com `+` (a Meta o entrega sem), senão cada mensagem
     abriria uma `Conversa` nova e não casaria com o `Contato` cadastrado;
   - delega ao `Atendedor` — hoje `AtenderConversa` (tool use), herdando o limite de
     caracteres (§G1), os avisos temporizados (§C2) e o encaminhamento à secretaria (§6j);
   - **responde ativamente**: a Meta exige `200 OK` e não aceita a resposta no corpo do webhook,
     então a resposta sai por uma **segunda chamada** à API (`MessageChannel.enviar_texto`), a
     partir do número da própria escola;
   - **idempotência por `wamid`** (`RegistroAtendimento`, tabela `inbound_atendimento`,
     migration `0026`): a Meta reenvia o evento quando o `200` demora, e sem isso o mesmo recado
     seria atendido — e cobrado na LLM — duas vezes. Desde 29/jul/2026 a reserva é **durável e
     compartilhada**: guarda **estado** (`em_atendimento` × `concluida`), não um booleano, porque
     a reentrega chega justamente *durante* a espera pela LLM e, com mais de uma réplica, quase
     sempre em outro processo. A reserva é feita num único `INSERT ... ON CONFLICT` antes da
     chamada à LLM; falha ou recusa por limite de taxa **liberam** a reserva, senão a mensagem
     ficaria travada e a reentrega — que é a chance de acertar — seria descartada. Reserva
     abandonada há mais de 3 min é retomável. **[Roadmap]** fila/worker, para o `200` não
     depender da latência da LLM.
   - **mídia**: `image` e `document` são baixados pela Graph API e guardados como
     `DocumentoRecebido` (§6k). Áudio segue ignorado com log — exigiria transcrição.
6. **Painel:** o `meta_phone_number_id` é editável no cadastro/edição de escola do super admin
   (`web/app/admin/escolas/`), e a lista marca com ⚠ a escola **sem id** — que é exatamente a
   que tem o inbound descartado.
7. **Config** (`app/config.py`): `META_PHONE_NUMBER_ID` é **fallback**, não a fonte da verdade;
   `META_ACCESS_TOKEN` deve ser um token de **usuário do sistema** (o da tela de Configuração da
   API expira em 24h).

Cobertura: `tests/test_inbound_meta.py` (roteamento, descarte sem vazamento entre escolas,
remetente correto, mensagem + status no mesmo envelope, idempotência) e
`tests/test_meta_channel.py` (montagem da URL e resolução do remetente no broadcast).

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

- **Uma escola nova NÃO exige uma WABA nova:** é mais um número na WABA existente.
- **⚠️ O teto de números é do PORTFÓLIO, não da WABA** (conferido na doc da Meta em
  13/ago/2026, e ao contrário do que esta seção afirmou até então). São **2 números por
  portfólio**, elevados automaticamente para **20** com a verificação da empresa — que já
  temos. Criar outra WABA **não** aumenta esse teto: a 21ª escola exige pedir aumento ao
  Direct Support ou abrir **outro portfólio**, com verificação de empresa própria. O limite
  de **20 WABAs por portfólio** existe, mas não é o gargalo.
  **Consequência de produto:** o teto prático é de ~20 escolas por portfólio, e não 400
  como a leitura antiga sugeria. Vale confirmar com o Direct Support antes de vender o 21º
  contrato.
- **⚠️ O limite diário de envio é do portfólio e COMPARTILHADO** entre todos os números
  ("Messaging limits are calculated and set at the business portfolio level and are shared
  by all business phone numbers within a portfolio" — mudança de out/2025). A afirmação
  anterior aqui, de que o tier era por número e por isso a WABA compartilhada era segura,
  **está errada hoje**: uma escola em campanha pode consumir a capacidade diária das
  outras. O `MessageQuota` por tenant (§9a) é contabilidade **nossa**, não o limite real da
  Meta — e as duas podem divergir. **[Roadmap]** medir a cota no nível do portfólio.
- **Os números reais, conferidos em 14/ago/2026** no Gerenciador do WhatsApp e pela API —
  e os dois são **menores** do que esta seção supunha:

  | Teto | Valor real hoje | Como sobe |
  |---|---|---|
  | Destinatários únicos / 24h | **250** (`messaging_limit_tier: TIER_250`) | verificação da empresa → 2.000; depois **um nível a cada 6h**, com qualidade alta e metade do limite usada em 7 dias. **Sem abrir chamado** — a doc da Meta diz que não é preciso contatar suporte |
  | Números por portfólio | **2** ("1 de 2 adicionados") | verificação da empresa, ou 2.000 conversas; acima de 20, só por Direct Support |

  **250 é o número que governa o produto hoje**, e é o que `META_DAILY_TIER_LIMIT` deve
  dizer. Configurar acima do real não "libera" nada: o disparo manda até o teto da Meta e o
  excedente vira **falha**, que conta contra a qualidade — justamente o que precisa estar
  alto para o limite subir. Com o valor certo, o excedente fica bloqueado pela cota e
  espera a janela seguinte (§9a-quinquies).
  **Conversas iniciadas pelo responsável não contam**: o inbound e as respostas de
  atendimento são livres. O teto pesa só no aviso em massa.
- **Qualidade continua sendo por número**, então uma escola que gere bloqueios não derruba
  a reputação das outras — mas derruba, sim, a capacidade de envio compartilhada.
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
