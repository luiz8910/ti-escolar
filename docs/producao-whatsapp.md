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
| **Forma de pagamento** na WABA de produção | ✅ **Cartão adicionado** (10/ago/2026) |
| **Token de usuário do sistema** (`META_ACCESS_TOKEN`) | ✅ **Gerado e no Render** (10/ago/2026) — system user `ti_escolar_backend` (id `61592805104592`), Admin, **sem expiração**, com `whatsapp_business_messaging` + `whatsapp_business_management` |
| **Webhook apontado na Meta** (callback + campo `messages`) | ✅ **Configurado** (10/ago/2026) — callback `https://ti-escolar.onrender.com/api/webhook/meta`, handshake verificado, campo `messages` **Assinado** |
| **Canal ligado** (`MESSAGE_CHANNEL=meta` no Render) | ✅ **Ligado** (10/ago/2026) — `/health` responde `canal: meta`, que é o adaptador **efetivo** e portanto prova que o token está em uso |
| **Backend no Render atualizado** | ✅ Alcançou a `main` (09/ago/2026) — `/health/pronto` responde |
| **WABA inscrita no app** (`subscribed_apps`) | ✅ **Feita** (10/ago/2026) — sem interface no console, ver §5.1 |
| **Inbound real ponta a ponta** | ✅ **Funcionando** (10/ago/2026) — mensagem de WhatsApp real recebida, respondida pelo bot e registrada no histórico da escola |
| **Templates aprovados** | ⚠️ `retomada_atendimento` **submetido em 10/ago/2026, em análise**; `hello_world` ativo. Ver §7.1 |
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

O modelo é **uma WABA nossa com o número de cada escola dentro dela**.

> ⚠️ **Corrigido em 13/ago/2026** — esta seção dizia "até 20 números por WABA; ao esgotar,
> cria-se outra sob o mesmo portfólio", e dizia que qualidade e tier eram por número. A doc
> da Meta diz outra coisa:
>
> - o teto de **20 números é do portfólio**, não da WABA ("Meta Business Accounts are
>   initially limited to 2 registered business phone numbers, but this limit can be
>   increased to up to 20"). Abrir outra WABA **não** aumenta o teto — passar de 20 escolas
>   exige aumento via Direct Support ou **outro portfólio**;
> - o **limite diário de envio é do portfólio e compartilhado** por todos os números
>   ("shared by all business phone numbers within a portfolio", mudança de out/2025), de modo
>   que uma escola em campanha **consome** a capacidade das outras.
>
> O que continua por número é a **qualidade**. Confirme os dois com o Direct Support antes de
> planejar acima de 20 escolas.

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
   O primeiro clique em *Adicionar* pede o **aceite da Política de Não Discriminação** da Meta,
   em nome da empresa — é um passo só, mas é um aceite legal, não um diálogo de UI.
2. Atribuir a ele o **app** e a **WABA de produção**, com controle total. As duas WABAs aparecem
   na mesma lista: escolher **`TI-Escolar`**, não a *Test WhatsApp Business Account*.
3. Gerar token com as permissões **`whatsapp_business_messaging`** e
   **`whatsapp_business_management`**. Existe também `whatsapp_business_manage_events`, que o
   produto **não usa** — deixar desmarcada.
4. Guardar na hora — o valor não é exibido de novo. Vai para `META_ACCESS_TOKEN` no Render.

**Expiração: escolhemos `Nunca`** (a Meta sugere 60 dias). O motivo é o formato do produto: o
WhatsApp é o **canal único**, não há rotação de token automatizada e **não há alerta ativo**
(item 8 do checklist §15 segue ⚠️). Um token de 60 dias seria uma quebra agendada que ninguém
seria avisado de que chegou — o erro apareceria só no painel de Logs, que ninguém abre sem
motivo. O preço dessa escolha é que um token vazado vale para sempre: a única revogação é o
botão **Anular tokens** na tela do usuário do sistema. Guardar no gerenciador de senhas, junto
com o PIN de 6 dígitos do número (§2, passo 5).

> **Feito em 10/ago/2026:** system user `ti_escolar_backend`, id `61592805104592`, Admin, com o
> app `3140942352961209` e a WABA `2116419572321695` atribuídos.

---

## 5. Webhook

Caminho no console: app → **Casos de uso** → *Conectar no WhatsApp* → **Etapa 2. Configuração de
produção** → **Configurar webhooks**.

- **Callback URL**: `https://<backend-no-render>/api/webhook/meta`
- **Verify token**: o mesmo valor de `META_WEBHOOK_VERIFY_TOKEN` → **Verificar e salvar**
- **Assinar o campo `messages`** — traz mensagens recebidas *e* status de entrega no mesmo
  envelope.
- **Assinar `message_template_status_update`** — é o que fecha o ciclo de submissão de
  template sem polling (§7.2). A revisão da Meta é assíncrona e este evento é o único aviso
  de que ela terminou; sem ele o template fica "Em análise" no painel para sempre, mesmo
  depois de aprovado, e o disparo continua recusado. Assine junto `template_category_update`,
  que avisa quando a Meta reclassifica um `utility` em `marketing` — mudança que altera o
  preço do disparo e que, sem o evento, só aparece na fatura.

O `GET` de verificação já está implementado e responde ao `hub.challenge`. Quando o handshake
passa, o sub-passo *Configurar webhooks* fica ✅ verde.

**A assinatura é um segundo passo, e ele mente.** A lista *Campos do webhook* só aparece depois
de salvar a URL, e nela o toggle de `messages` **muda de cor sem necessariamente salvar**: em
10/ago o primeiro clique acendeu o botão e **nenhuma requisição saiu** — depois de recarregar, o
campo estava de volta em *Cancelou a assinatura*. No clique que funcionou houve um
`POST /async/webhooks/fields/edit/` com `200` e o rótulo virou **Assinado**.

Como isso importa: URL salva **sem** o campo assinado deixa a tela verde e o endpoint mudo —
não chega mensagem nem status de entrega, e nada dá erro. **Sempre recarregue a página e confira
que `messages` está como "Assinado"**; ver o toggle azul logo após o clique não é prova.

> **Feito em 10/ago/2026** para `https://ti-escolar.onrender.com/api/webhook/meta` — handshake
> verificado e `messages` **Assinado**, confirmado após reload.

### 5.1 Inscrever a WABA no app — o passo que não está no console

**Assinar o campo `messages` não basta.** São duas coisas diferentes, e só a primeira tem
interface:

| | O que declara | Onde |
|---|---|---|
| Assinar o campo `messages` | *este app quer eventos desse tipo* | console (§5) |
| **Inscrever a WABA no app** | *esta conta manda os eventos dela para este app* | **só pela Graph API** |

Faltando a segunda, a Meta **não envia nada e não reporta erro em lugar nenhum**: console todo
verde, webhook configurado, número Conectado, e o endpoint nunca é chamado. É o mesmo padrão
silencioso do app não publicado (§1.1) e do canal sem token (§6.1.1) — a terceira vez que ele
aparece neste go-live.

```bash
# conferir (pode devolver "(#200) Provide valid app ID" mesmo estando tudo bem — o GET é
# menos confiável que o POST aqui; não conclua nada por ele)
curl -s "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps" \
  -H "Authorization: Bearer $(cat ~/.meta_token)"

# inscrever — é esta chamada que resolve
curl -s -X POST "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps" \
  -H "Authorization: Bearer $(cat ~/.meta_token)"
# {"success":true}
```

Use o `META_ACCESS_TOKEN` (o do system user); é a permissão `whatsapp_business_management` que
autoriza. Guarde-o num arquivo (`~/.meta_token`, `chmod 600`) em vez de passar na linha de
comando — assim ele não fica no histórico do shell.

**É por WABA.** Ao abrir uma segunda WABA, repita a chamada, senão as escolas daquela conta
nascem sem inbound. Dois outros passos acompanham a conta nova: **cadastrá-la** em
Administração → Contas WhatsApp (senão não há onde criar template para as escolas dela) e
clicar em **Replicar templates globais** (senão elas ficam sem nenhum template aprovado).

> **Feito em 10/ago/2026** na WABA `2116419572321695` → `{"success":true}`.

#### Diagnóstico: o botão *Teste* separa as causas

Cada campo na lista *Campos do webhook* tem um link **Teste** → *Enviar para meu servidor*, que
dispara um POST assinado com um payload de exemplo. Vale mais do que parece, porque **separa
"nosso código está errado" de "a Meta não está enviando"**:

- **chega no log** → URL, `META_APP_SECRET` e o parsing estão certos. O payload de exemplo traz
  `phone_number_id: "123456123"`, então o esperado é `Inbound Meta descartado: nenhuma escola
  cadastrada com o phone_number_id` — um descarte limpo prova o caminho inteiro;
- **não chega** → o problema está antes de nós: assinatura da WABA (§5.1), campo não assinado
  ou URL errada.

Foi assim que se achou o §5.1 em 10/ago: o teste chegou com `200`, a mensagem real não chegava.

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
# Não há META_WABA_ID: a conta (WABA) é cadastro, no painel — ver §7.3
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
| `GET /health` | `{"canal": "meta"}` **(10/ago)** | ✅ canal ligado. Antes era `demo`. Como o campo é o adaptador **efetivo** (§6.1.1), `meta` aqui prova que o `META_ACCESS_TOKEN` está presente e válido o bastante para instanciar o canal — não é só o eco da env |
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

Em 10/ago/2026 o `META_ACCESS_TOKEN` e o `MESSAGE_CHANNEL=meta` entraram no Render, nessa ordem,
e o `/health` passou a responder `canal: meta`. **Salvar uma variável no Render dispara redeploy
automático** — é a única automação de deploy que este serviço tem; o push à `main`, não.

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

### 7.1 `retomada_atendimento` — obrigatório para o atendimento humano

O atendimento humano (CLAUDE.md §6j) esbarra na janela de 24h de um jeito muito concreto: o
responsável escreve sexta às 20h, a secretaria só vê na segunda de manhã, e aí o texto livre
**já não pode mais sair**. O template que reabre essa conversa é:

| Campo | Valor |
|---|---|
| Nome | `retomada_atendimento` |
| Categoria | **utility** |
| Idioma | `pt_BR` |
| Corpo | `Olá! Aqui é a secretaria da {{1}}. Sobre a sua mensagem: {{2}} Se precisar de algo mais, é só responder por aqui.` |

> ⚠️ **A Meta recusa template que termine em variável** ("As variáveis não podem estar no
> início ou no fim do modelo"). O corpo original terminava em `{{2}}` e foi recusado no
> formulário; a frase final existe para satisfazer essa regra, não por estilo. A ordem dos
> parâmetros não mudou — `EnviarTemplate` segue passando `[nome_da_escola, resposta]`.

**Amostras exigidas na submissão** (só para a revisão; não vão ao responsável):
`{{1}}` = `EM Rosa Cury`, `{{2}}` = `a declaração de escolaridade já está pronta e pode ser
retirada na secretaria.`

Depois de **aprovado** pela Meta, basta **sincronizar** (§7.2) — o status vem da própria
Meta, casando por (nome, idioma). **Não é preciso mexer no Render:**
`TEMPLATE_RETOMADA_ATENDIMENTO` já tem `retomada_atendimento` como default. Preencher só
serve para apontar outro nome, ou para **desligar** a retomada (valor vazio).

Enquanto isso não acontecer, o comportamento é **recusar com erro explícito** no painel
("a janela de 24h expirou e não há template de retomada aprovado"). É proposital: o modo de
falha alternativo — deixar a chamada morrer na Graph API — faria a secretaria acreditar que
respondeu um responsável que nunca recebeu nada. O seed cria o template como `pendente` pela
mesma razão.

### 7.2 Catálogo de templates no painel (`/admin/templates`)

Criar template deixou de ser passo manual no WhatsApp Manager **mais** `INSERT` no banco. O
painel cria, submete e acompanha; a API usada é a **WhatsApp Business Management**
(`/{waba_id}/message_templates`), que exige o escopo **`whatsapp_business_management`** no
token de usuário do sistema — diferente do `whatsapp_business_messaging` usado no envio.

> **Conferido em 12/ago/2026:** a permissão está habilitada no caso de uso do app
> ("Conectar-se com clientes pelo WhatsApp" → *Permissões e recursos*, status *Pronto para
> teste*), e o usuário do sistema `ti_escolar_backend` é **Admin** com **acesso total** ao app
> e à conta do WhatsApp. O que o console **não** mostra é com quais escopos um token **já
> gerado** foi emitido; se a criação de template devolver erro de permissão, gere um token
> novo marcando `whatsapp_business_management` e troque o `META_ACCESS_TOKEN` no Render.

**Dois escopos:**

| | Quem cria | Nome | Para quê |
|---|---|---|---|
| **Global** | só super admin | como digitado | o caso comum — nome da escola em `{{1}}`, aprovado uma vez, servindo todas |
| **Da escola** | admin da escola | prefixado pelo slug (`rosacury_festa_junina`) | o que é mesmo específico dela |

O global existe porque um `aviso_geral` por escola seriam N revisões do mesmo texto e N
chances de rejeição num ativo compartilhado. O prefixo do escopo por escola é o que evita
colisão de nome na mesma conta.

**Template é aprovado por conta (WABA)** — e desde 13/ago/2026 o produto modela isso
(§9a-ter do CLAUDE.md): o texto é um só no catálogo, mas a submissão e o status são **por
conta**. Um global aprovado na conta A **não existe** na conta B; quem libera o disparo de
uma escola é a aprovação **na conta dela**. Na tela de templates, o selo mostra o pior
status entre as contas, e a lista por conta aparece a partir da segunda.

**A submissão não é a aprovação.** O `POST` devolve `PENDING`; quem muda para aprovado é o
webhook `message_template_status_update` (§5). Se ele falhar, `POST /api/admin/templates/sincronizar`
(super admin) reconcilia lendo a Meta — é a rede de segurança, porque webhook perdido é
indistinguível de revisão ainda em curso.

**Validação local antes de submeter.** Não é preciosismo: rejeição conta contra a conta, que
várias escolas compartilham. O painel recusa, antes de gastar uma submissão, corpo que
começa ou termina em variável (a recusa que já levamos), corpo que é só variável, numeração
fora de sequência, falta de exemplo e categoria `authentication`.

---

### 7.3 A conta (WABA) é cadastro, não variável de ambiente

O id da conta mora no banco e é editável em **Administração → Contas WhatsApp**. Não existe
`META_WABA_ID` — uma env não comporta a segunda conta, e o teto de números do portfólio
(§2) garante que ela vai existir.

São dois caminhos para preencher o id, e o segundo costuma dispensar o primeiro:

1. **Digitar na tela.** O id está no WhatsApp Manager, em Configurações da conta
   (hoje: `2116419572321695`).
2. **Deixar o webhook reconhecer.** Todo evento traz a conta no `entry[].id`; ao receber
   um id desconhecido, havendo **exatamente uma** conta sem id cadastrada, a aplicação
   confirma esse id contra a Graph API (`GET /{id}?fields=id,name`) e só então o grava —
   junto com o nome que a Meta usa. A confirmação existe porque a documentação da Meta
   **não afirma** que `entry[].id` é a WABA: os exemplos mostram o número, a referência
   não descreve o campo. Quem decide é a resposta da Meta, não a nossa leitura do payload.

Enquanto o id estiver vazio, criar template falha com a causa por extenso ("A conta do
WhatsApp Business (WABA) desta escola está sem o id da Meta"), e o painel de segurança
sinaliza as escolas afetadas.

---

## 8. Limites, tiers e qualidade

> ⚠️ **Corrigido em 13/ago/2026:** o limite deixou de ser por número. A doc da Meta diz que
> "messaging limits are calculated and set at the business portfolio level and are shared by
> all business phone numbers within a portfolio" (mudança de out/2025) — ou seja, uma escola
> em campanha consome a capacidade das outras. O que segue por número é a **qualidade**.
> Ver §2 e o CLAUDE.md §9e.3.

- O limite é de **destinatários únicos por 24h**, medido **no portfólio**: 1K → 10K → 100K → ilimitado.
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

> **Passo 5 executado com sucesso em 10/ago/2026** — primeira conversa real do produto pelo
> WhatsApp: mensagem enviada ao número da escola, **respondida pelo bot** e registrada em
> `/admin/historico/conversas`. O ciclo inbound completo (webhook → assinatura → roteamento por
> `phone_number_id` → RAG/LLM → resposta pelo número da escola → histórico) está **provado em
> ambiente real**, não só em teste.
>
> Faltam do roteiro os passos **2 e 3** (broadcast por template), que dependem da forma de
> pagamento (§3) e de templates aprovados (§7); e o **6**, que só faz sentido com uma segunda
> escola cadastrada.

---

## 10. Checklist consolidado

- [x] Verificação da empresa aprovada
- [x] **App publicado ("Ao vivo")** — sem isso o webhook não recebe dado de produção nenhum (§1.1)
- [x] WABA de produção criada (id `2116419572321695`)
- [ ] **Id da WABA preenchido no painel** (Administração → Contas WhatsApp) e conta
      escolhida em cada escola — sem isso o disparo por template é recusado, porque não há
      onde conferir a aprovação. **Não há env para isso**: a migration `0042` cria a conta
      sem id, e ele é digitado na tela ou reconhecido sozinho no primeiro evento do webhook
      (conferido contra a Graph API antes de ser gravado)
- [x] Número registrado, **verificado e inscrito** (chip nosso) — `phone_number_id`
      `1231892910008454`; PIN de 6 dígitos guardado fora do repositório (§2, passo 5)
- [x] Backend no Render **atualizado** com a `main` (`/health/pronto` responde)
- [ ] Nome de exibição aprovado
- [ ] Forma de pagamento na WABA de produção
- [x] Token de usuário do sistema gerado e no Render (10/ago — `ti_escolar_backend`, sem
      expiração; ver §4 para o porquê de `Nunca`)
- [x] Webhook configurado e **campo `messages` assinado** (10/ago) — salvar a URL **não**
      inscreve em nada, e o toggle acende sem salvar: confira após recarregar (§5)
- [x] **WABA inscrita no app** via `POST /{waba-id}/subscribed_apps` (10/ago) — passo **sem
      interface no console** e sem o qual a Meta não envia nada, calada (§5.1). Repetir a cada
      WABA nova
- [x] **`MESSAGE_CHANNEL=meta` no Render** (10/ago) — `/health` responde `canal: meta`
- [x] `META_APP_SECRET` + `META_VALIDATE_SIGNATURE=true` (medido de fora: `POST` sem assinatura → 403)
- [ ] `JWT_SECRET` trocado · [x] `META_WEBHOOK_VERIFY_TOKEN` trocado (`changeme` → 403)
- [ ] `/admin/seguranca` sem itens em Atenção
- [ ] Templates aprovados com nome/idioma batendo com o banco
- [x] **`Tenant.meta_phone_number_id` implementado** (multi-tenant de envio + roteamento inbound)
- [x] **Inbound do webhook implementado** (chatbot atendendo)
- [x] **`phone_number_id` cadastrado na escola** (10/ago/2026 — `1231892910008454`, junto com o
      `whatsapp_numero` `+55 15 99753-6978`). Continua sendo **por escola**: cada nova escola
      precisa do seu, senão o inbound dela é descartado
- [~] Teste de fumaça por escola — **inbound provado em real** (10/ago: mensagem recebida,
      respondida e no histórico). Falta a parte de **outbound**, que depende de pagamento e
      templates, e o teste cruzado entre duas escolas (§9)

---

## Referências

- Cloud API — Introdução: <https://developers.facebook.com/docs/whatsapp/cloud-api>
- Webhooks e assinatura de payload:
  <https://developers.facebook.com/docs/graph-api/webhooks/getting-started>
- Limites de mensagens e qualidade:
  <https://developers.facebook.com/docs/whatsapp/messaging-limits>
- Templates: <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates>
