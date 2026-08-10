# Produção — WhatsApp (Meta Cloud API) — Checklist de go-live

> Guia operacional para colocar o TI-Escolar em **produção real** na **Meta Cloud API direta**,
> com um número dedicado por escola. WhatsApp é o **único canal** do produto — não há fallback
> (SMS/e-mail) previsto.
>
> **Histórico:** até jul/2026 este documento descrevia o caminho via **Twilio como BSP**, que
> existia por um único motivo — o Sandbox operava **sem** a verificação de empresa da Meta. Com a
> **verificação aprovada em 27/jul/2026**, o intermediário só acrescentaria margem sobre o preço
> da Meta, e a Twilio foi removida do produto. Ver CLAUDE.md §9e.

---

## 0. Onde estamos

| Etapa | Situação |
|---|---|
| **Verificação da empresa** (Meta cruza CNPJ, site e dados do portfólio) | ✅ **Aprovada** (27/jul/2026) — portfólio TiEscolar, business_id `940840332344260` |
| **App publicado** ("Ao vivo") | ✅ **Publicado** (06/ago/2026) — ver §1.1 |
| **WABA de produção** | ✅ **Criada** (06/ago/2026) — id `2116419572321695`, nome de exibição `TI-Escolar` |
| **Número real registrado** | ✅ **Verificado e inscrito** (09/ago/2026) — `+55 15 99753-6978`, `phone_number_id` `1231892910008454` |
| **Número cadastrado na escola** (painel do super admin) | ✅ **Feito** (10/ago/2026) — `meta_phone_number_id` + `whatsapp_numero` preenchidos |
| **Forma de pagamento** na WABA de produção | ⬜ Pendente |
| **Token de usuário do sistema** (`META_ACCESS_TOKEN`) | ⬜ Pendente — **bloqueia ligar o canal**, ver §6.1.1 |
| **Webhook apontado na Meta** (callback + campo `messages`) | ⬜ Pendente |
| **Canal ligado** (`MESSAGE_CHANNEL=meta` no Render) | ⬜ Pendente — o serviço responde `canal: demo` |
| **Backend no Render atualizado** | ✅ Alcançou a `main` (09/ago/2026) — `/health/pronto` responde |
| **Templates aprovados** | ⬜ Pendente |
| **Inbound do webhook** (chatbot atendendo) | ✅ Implementado (27/jul/2026) — CLAUDE.md §9e.1 |
| **Multi-tenant de envio** (número por escola) | ✅ Implementado — `Tenant.meta_phone_number_id` |
| **Assinatura do webhook** (`X-Hub-Signature-256`) | ✅ Implementada — falta **ligar** em produção |

> ✅ **O produto atende e dispara pela Meta.** O webhook trata os dois caminhos do envelope:
> status de entrega e **mensagens recebidas**, roteadas para a escola dona do
> `phone_number_id` e respondidas pelo número dela.
>
> ⚠️ **Consequência operacional:** uma escola **sem `meta_phone_number_id` cadastrado** tem o
> inbound **descartado** — é proposital (não existe tenant de fallback, que jogaria a conversa
> de uma escola na outra), mas significa que cadastrar o id é parte obrigatória do onboarding.
> A lista de escolas no painel marca com ⚠ quem está nesse estado.

---

## 1. Pré-requisitos

- [ ] **Meta Business Account** verificada (feito) e uma **conta pessoal do Facebook** com papel
      de **admin** no portfólio.
- [ ] **App** em `developers.facebook.com` com o caso de uso **"Conectar-se com clientes pelo
      WhatsApp"** adicionado (app id **`3140942352961209`** — 16 dígitos; este doc registrava
      15, truncado, e a URL direta com o id errado silenciosamente redireciona para a lista de
      apps em vez de dar erro).
- [ ] **Um chip novo por escola**, que:
  - **não** esteja ativo no **WhatsApp/WhatsApp Business**. Se estiver, apague a conta naquele
    número antes — isso **destrói o histórico** dele;
  - consiga receber o código de verificação por **SMS ou ligação** (fixo serve, a Meta dita o
    código por voz);
  - depois de registrado na Cloud API, **não volta** a funcionar no app comum.
- [ ] **Domínio público com HTTPS** para o backend (o webhook precisa alcançá-lo). O deploy no
      Render já atende.
- [ ] **Nome de exibição** por escola que cumpra as regras da Meta (ex.: "EM Rosa Cury") — nada
      genérico ou enganoso. **Passa por revisão assíncrona: dispare cedo, é o caminho crítico.**

### 1.1 Publicar o app — bloqueante para o inbound

O app precisa estar **publicado** ("Ao vivo"), não em "Modo: Em desenvolvimento". A própria tela
de webhooks da Meta declara o motivo:

> "Os apps só poderão receber webhooks de **teste** enviados do painel de apps enquanto o app não
> for publicado. **Não serão fornecidos dados de produção**, incluindo dados de administradores,
> desenvolvedores e testadores do app, a menos que o app tenha sido publicado."

Ou seja: **com o app não publicado, o `POST /api/webhook/meta` não recebe mensagem real nenhuma** —
o chatbot não atende e nenhum status de entrega chega, mesmo com número verificado, token válido e
assinatura configurada. É um passo silencioso: nada dá erro, simplesmente não chega nada.

Caminho: app → **Publicar** (menu lateral) → botão **Publicar** no rodapé. Os requisitos que
travavam a publicação (política de privacidade, termos, exclusão de dados, e-mail de contato,
categoria) já estão preenchidos e apontam para `tiescolar.com.br` — a tela mostra *"Todas as
configurações necessárias do app foram concluídas"*.

**Publicar é reversível** (o mesmo rodapé passa a oferecer **"Tirar do ar"**) e é **ortogonal ao
número**: o estado de publicação é do *app*, não da WABA nem do `phone_number_id`. Trocar de número
depois não desfaz a publicação, nem os templates, nem o webhook — só muda o
`Tenant.meta_phone_number_id` daquela escola. Publicar não inicia cobrança e não dispara análise
da Meta.

---

## 2. Criar a WABA de produção e registrar o número

O modelo é **uma WABA nossa com o número de cada escola dentro dela** (até 20 números por WABA;
ao esgotar, cria-se outra sob o mesmo portfólio). Qualidade e tier de envio são **por número**,
então uma escola não derruba o limite das outras.

O console não usa mais a lista de "Produtos": o WhatsApp vive sob **Casos de uso**.

1. `developers.facebook.com` → app **Ti-Escolar** → **Casos de uso** → "Conectar-se com clientes
   pelo WhatsApp" → **Personalizar**.
2. **Etapa 2. Configuração de produção** — a Meta guia os 4 sub-passos: configurar webhooks ·
   registrar número · forma de pagamento · enviar mensagem. (Etapa 1 "Experimente" e Etapa 3
   "Verificação da empresa" já estão concluídas.)
3. Em "Registre seu número de telefone do WhatsApp" → **Adicionar novo número**. É esse fluxo que
   cria a WABA real ao lado da de teste. O assistente tem 3 etapas:
   - **Perfil**: nome de exibição, **fuso** (já vem `America/Sao_Paulo`), **categoria**
     (`Educação`) e descrição. Nada é persistido até o fim — fechar o diálogo no meio perde tudo e
     recomeça em branco.
   - **Adicionar número**: o seletor de país **começa em `US +1`** — trocar para `BR +55` antes de
     digitar, senão o número é interpretado como americano.
   - **Verificar número**: código de 6 dígitos por SMS ou ligação.
4. **Verificar o número.** Nós compramos o chip, colocamos num aparelho nosso e lemos o código — a
   escola não participa (CLAUDE.md §9e.3). Ver §2.1: no Brasil este é o passo que trava.
5. **Inscrever o número (`Registrar`) com um PIN de 6 dígitos.** Verificar **não** é registrar:
   depois do código o número passa de *Não verificado* para **"Não registrado"**, e o botão vira
   **Registrar**. Esse passo pede um **PIN de 6 dígitos** (verificação em duas etapas do número),
   que a Meta **não exibe de novo** e que é exigido para **reinscrever o número no futuro**
   (troca de WABA, re-registro após incidente). Anote no gerenciador de senhas — ele **não** vai
   para `.env` nem para o git: a aplicação não o usa, só o console da Meta. Concluído o registro,
   o status vira **"Inscrito"**.
6. Anotar o **`phone_number_id`** do número e **cadastrá-lo na escola** (painel do super admin →
   Escolas → campo *phone_number_id da Meta*). É ele — não o E.164 — que a API usa para enviar e
   que roteia o WhatsApp recebido para a escola certa. **Sem ele a escola não recebe mensagens.**

### 2.1 Quando a verificação do número não chega (Brasil)

> **Desfecho (09/ago/2026): resolvido esperando.** Três dias depois das tentativas frustradas de
> 06/ago, uma **única tentativa por SMS** no mesmo chip Vivo entregou o código na hora, sem trocar
> nada — nem operadora, nem aparelho, nem método. Ou seja, o que travava era **transitório**
> (provavelmente o bloqueio por excesso de reenvios descrito abaixo, somado à instabilidade da rota
> A2P internacional), não uma incompatibilidade da linha. **A lição operacional é a regra de não
> insistir:** depois de duas tentativas falhas, o movimento certo é **parar por algumas horas** e
> tentar de novo, não trocar de chip. A verificação não expira e o número fica esperando.

Aprendido no primeiro registro real (06/ago/2026), com chip **Vivo pré-pago** novo:

- **O código da Meta é tráfego internacional de entrada** — SMS A2P internacional ou ligação
  internacional. Isso é uma categoria diferente do SMS e da ligação comuns.
- Sintoma observado: **SMS nacional chegava e ligação nacional completava**, mas **nem o SMS nem a
  ligação da Meta chegaram** — nem como chamada perdida no registro do aparelho. Linha já
  regularizada (CPF + selfie + CNH) e com a recarga que vinha no chip.
- **O diagnóstico decisivo é o registro de chamadas:** se a ligação da Meta aparece como perdida,
  a rota funciona e o problema é filtro de "silenciar desconhecidos" no aparelho; se **não aparece
  nada**, o tráfego internacional não está alcançando a linha e não há nada a configurar na Meta.
- **Não insista nas tentativas.** A Meta trava a verificação por horas depois de alguns reenvios
  falhos, e é justamente a tentativa seguinte que se perde. A verificação **não expira**: o número
  fica "Não verificado" na WABA e é retomável por *Gerenciador do WhatsApp → Números de telefone →
  engrenagem na linha*.
- **Sobre o método:** a rota de SMS A2P internacional para o Brasil é instável, mas **não é
  inviável** — foi por SMS que a verificação passou em 09/ago. Trocar de método é uma alternativa
  se o SMS falhar repetidamente, **não** a primeira reação a uma falha isolada; **esperar** é.
  Cuidado com a mecânica da tela: trocar o método já dispara a nova tentativa — clicar em
  "Reenviar código" depois disso duplica a solicitação e ajuda a queimar a franquia.
- Se o número for trocado, apagar a linha não verificada pelo ícone de lixeira e recadastrar; o
  **perfil da WABA** (nome de exibição, categoria, fuso) permanece e não é refeito.
- **Consequência de processo:** registre o **primeiro** número como o nosso (nome de exibição
  `TI-Escolar`), não o da escola-âncora. Descobrir qual operadora entrega a verificação da Meta é
  aprendizado que não deve acontecer no número do cliente — e trocar o chip depois de verificado
  custa a identidade do canal.

---

## 3. Forma de pagamento

Adicionar cartão **na WABA de produção** (a de teste não gera cobrança e não precisa).

- Cobrança em **USD**: no fluxo atual da Meta o Real não é ofertado, então a fatura vem em dólar
  e o cartão brasileiro soma IOF de compra internacional + spread do emissor. Considere isso na
  precificação do plano por escola.
- Conferir **razão social, endereço e fuso** (`America/Sao_Paulo`) nas informações comerciais —
  devem bater com o Cartão CNPJ usado na verificação.

---

## 4. Token permanente (usuário do sistema)

O token exibido na tela de Configuração da API **expira em 24h** e não serve para produção.

1. Business Manager → **Usuários do sistema** → criar um system user com papel **admin**.
2. Atribuir a ele o **app** e a **WABA de produção**, com controle total.
3. Gerar token com as permissões **`whatsapp_business_messaging`** e
   **`whatsapp_business_management`**.
4. Guardar na hora — o valor não é exibido de novo. Vai para `META_ACCESS_TOKEN` no Render.

---

## 5. Webhook

Em **WhatsApp → Configuração → Webhooks**:

- **Callback URL**: `https://<backend-no-render>/api/webhook/meta`
- **Verify token**: o mesmo valor de `META_WEBHOOK_VERIFY_TOKEN`
- **Assinar o campo `messages`** — traz mensagens recebidas *e* status de entrega no mesmo
  envelope.

O `GET` de verificação já está implementado e responde ao `hub.challenge`.

**Segurança (obrigatório):** copiar o **app secret** (Meta for Developers → Configurações →
Básico) para `META_APP_SECRET` e ligar `META_VALIDATE_SIGNATURE=true`. Sem isso o endpoint
aceita qualquer POST e um terceiro pode forjar status de entrega — mascarando como `delivered`
um aviso que a escola precisa saber que **não** chegou. Ver CLAUDE.md §9e.2.

---

## 6. Configuração no TI-Escolar

### 6.1 Variáveis de ambiente (produção)

```bash
MESSAGE_CHANNEL=meta

META_PHONE_NUMBER_ID=          # fallback; cada escola tem o seu
META_WABA_ID=
META_ACCESS_TOKEN=             # token do usuário do sistema (§4)
META_WEBHOOK_VERIFY_TOKEN=     # valor forte, NÃO "changeme"
META_DAILY_TIER_LIMIT=1000     # tier inicial de negócio verificado

META_APP_SECRET=               # app secret (§5)
META_VALIDATE_SIGNATURE=true   # OBRIGATÓRIO em produção

JWT_SECRET=                    # valor forte, NÃO o do .env.example
APP_ENV=production
```

Confira o resultado em **`/admin/seguranca`** no painel (super admin): a página lê a configuração
em execução e sinaliza segredo default, assinatura desligada e CORS liberado (CLAUDE.md §14).

**Estado do serviço no Render, medido de fora em 09/ago/2026** (`https://ti-escolar.onrender.com`):

| Sinal | Medido | Leitura |
|---|---|---|
| `GET /health` | `{"canal": "demo"}` | **`MESSAGE_CHANNEL` ainda é `demo`** — nada sai pela Meta enquanto não virar `meta`, mesmo com número inscrito |
| `GET /api/webhook/meta` com `verify_token=changeme` | `403` | `META_WEBHOOK_VERIFY_TOKEN` já foi trocado pelo valor de exemplo ✅ |
| `POST /api/webhook/meta` sem `X-Hub-Signature-256` | `403` | `META_VALIDATE_SIGNATURE=true` ligado ✅ |
| `GET /health/pronto` | `200 {"banco":"ok"}` | **o deploy alcançou a `main`** ✅ — esse endpoint entrou em 29/jul (CLAUDE.md §16); com ele no ar, o painel de Logs e o rate limiting também estão |

O `/health/pronto` respondia `404` na primeira medição do dia e passou a responder `200` na
segunda. **Não foi sozinho:** o Render deste serviço **não tem Auto-Deploy** — todo evento na
aba *Events* diz *"Manually triggered by you via Dashboard"*. O que entrou no ar foi um deploy
manual do PR #36, disparado no meio do dia.

É a explicação de por que o serviço vive atrás da `main`, e a razão de **mergear não ser
publicar** neste projeto: depois de todo merge é preciso ir ao painel → **Manual Deploy** →
*Deploy latest commit*. **Confirme o commit em execução no Render antes de configurar o webhook
na Meta** — apontar o webhook para um serviço atrasado esconde o problema, porque o handshake
passa e o inbound cai numa versão antiga do código.

Restou, portanto, **uma única variável a mexer no Render**: `MESSAGE_CHANNEL`. E ela tem uma
ordem obrigatória, abaixo.

#### 6.1.1 `META_ACCESS_TOKEN` antes de `MESSAGE_CHANNEL=meta` — falha silenciosa

`criar_canal` (`app/infrastructure/factories.py`) só devolve o `MetaMessageChannel` quando
**`MESSAGE_CHANNEL=meta` *e* `META_ACCESS_TOKEN` está preenchido**. Faltando o token, ele **cai
no `DemoMessageChannel` sem erro nenhum** — o processo sobe normalmente. Ligar o canal antes de
ter o token (§4) produz o pior estado possível do go-live:

- o **inbound é atendido e cobrado**: `ProcessarInboundMeta` roteia a mensagem, chama a LLM e
  marca o `RegistroAtendimento` como `concluida` — mas a resposta sai pelo canal demo e **nunca
  chega ao responsável**. Para o painel de Logs (§16) a saúde continua verde: zero erro, zero
  atendimento falho;
- o **outbound grava id externo falso**: o demo devolve `demo-N` como id da mensagem, que jamais
  casa com um `wamid` de webhook. Todos os destinatários ficam presos em `ENVIADO` sem
  confirmação e a não-entrega reativa (§9b) passa a acusar **a escola inteira** como não
  recebida.

Por isso a ordem é **§4 (token) → §5 (webhook) → `MESSAGE_CHANNEL=meta`**, e não o contrário.
Desde 09/ago/2026 o `/health` devolve o canal **efetivo** (o adaptador que foi realmente
instanciado), não o valor da env: se ele disser `"canal": "demo"` com a env em `meta`, o token
está faltando. O painel `/admin/seguranca` sinaliza o mesmo caso.

### 6.2 Número por escola (multi-tenant)

Cada escola tem **dois** campos de número, e eles não são intercambiáveis:

| Campo | O que é | Para que serve |
|---|---|---|
| `Tenant.whatsapp_numero` | o número em **E.164** (`+5515333330000`) | exibição e referência humana |
| `Tenant.meta_phone_number_id` | o **id do número na Meta** (só dígitos) | **envia** (URL da Graph API) e **roteia o inbound** |

Ambos são únicos entre escolas. O `MetaMessageChannel` monta a URL de envio por mensagem, com o
id da escola resolvido por `Tenant.remetente_canal`; o `META_PHONE_NUMBER_ID` da env é apenas
**fallback** para quem ainda não tem id cadastrado (nesse caso o log do backend avisa que o
disparo saiu pelo número padrão).

---

## 7. Templates (mensagens fora da janela de 24h)

Fora da janela de 24h só se envia **template aprovado**. Criar no **WhatsApp Manager**:

- categoria **utility** para avisos escolares (marketing é mais caro e tem opt-out mais
  agressivo);
- o **nome** do template no WhatsApp Manager precisa bater com `MessageTemplate.nome` no banco,
  e o idioma com `MessageTemplate.idioma` — é assim que `enviar_template` o identifica;
- parâmetros posicionais (`{{1}}`, `{{2}}`…) mapeiam para a lista `parametros` do caso de uso.

---

## 8. Limites, tiers e qualidade

- O limite é de **destinatários únicos por 24h**, **por número**: 1K → 10K → 100K → ilimitado.
- Empresa **verificada** (nosso caso) começa em **1.000/24h**; a escala é automática conforme a
  **qualidade** do número.
- Qualidade cai com bloqueios e denúncias dos pais — por isso opt-in, conteúdo útil e frequência
  moderada são requisito operacional, não boas maneiras.
- `META_DAILY_TIER_LIMIT` precisa refletir o tier real; a cota é aplicada nos casos de uso
  (`QuotaPolicy`), que enfileiram ou recusam ao atingir o limite.

---

## 9. Teste de fumaça pós go-live (por escola)

1. `GET /health` responde `{"canal": "meta"}`. É o canal **efetivo**, então `demo` aqui com a env
   em `meta` significa `META_ACCESS_TOKEN` faltando (§6.1.1) — faça este passo **antes** dos
   demais, senão eles falham sem dizer por quê.
2. Enviar um **broadcast de teste** para um número próprio → chega pelo número **da escola**.
3. Conferir em `/admin/historico/disparos` o status evoluindo para `delivered`/`read`.
4. Forçar um webhook com assinatura inválida → deve responder **403** (valida §5).
5. Mandar uma mensagem **para o número da escola** pelo WhatsApp → a resposta do bot deve chegar
   em segundos e a conversa aparecer em `/admin/historico/conversas`, **no tenant certo**.
6. Repetir o passo 5 a partir do número de **outra** escola e conferir que cada conversa ficou na
   sua — é o teste que pega um `phone_number_id` cadastrado na escola errada.
7. Nos logs, `webhook.meta` não deve mostrar `Inbound Meta descartado`; se mostrar, o
   `phone_number_id` daquele número não está cadastrado em nenhuma escola.

---

## 10. Checklist consolidado

- [x] Verificação da empresa aprovada
- [x] **App publicado ("Ao vivo")** — sem isso o webhook não recebe dado de produção nenhum (§1.1)
- [x] WABA de produção criada (id `2116419572321695`)
- [x] Número registrado, **verificado e inscrito** (chip nosso) — `phone_number_id`
      `1231892910008454`; PIN de 6 dígitos guardado fora do repositório (§2, passo 5)
- [x] Backend no Render **atualizado** com a `main` (`/health/pronto` responde)
- [ ] Nome de exibição aprovado
- [ ] Forma de pagamento na WABA de produção
- [ ] Token de usuário do sistema gerado e no Render **(antes de ligar o canal — §6.1.1)**
- [ ] Webhook configurado e campo `messages` assinado
- [ ] **`MESSAGE_CHANNEL=meta` no Render** — o último passo, depois do token
- [x] `META_APP_SECRET` + `META_VALIDATE_SIGNATURE=true` (medido de fora: `POST` sem assinatura → 403)
- [ ] `JWT_SECRET` trocado · [x] `META_WEBHOOK_VERIFY_TOKEN` trocado (`changeme` → 403)
- [ ] `/admin/seguranca` sem itens em Atenção
- [ ] Templates aprovados com nome/idioma batendo com o banco
- [x] **`Tenant.meta_phone_number_id` implementado** (multi-tenant de envio + roteamento inbound)
- [x] **Inbound do webhook implementado** (chatbot atendendo)
- [x] **`phone_number_id` cadastrado na escola** (10/ago/2026 — `1231892910008454`, junto com o
      `whatsapp_numero` `+55 15 99753-6978`). Continua sendo **por escola**: cada nova escola
      precisa do seu, senão o inbound dela é descartado
- [ ] Teste de fumaça por escola

---

## Referências

- Cloud API — Introdução: <https://developers.facebook.com/docs/whatsapp/cloud-api>
- Webhooks e assinatura de payload:
  <https://developers.facebook.com/docs/graph-api/webhooks/getting-started>
- Limites de mensagens e qualidade:
  <https://developers.facebook.com/docs/whatsapp/messaging-limits>
- Templates: <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates>
