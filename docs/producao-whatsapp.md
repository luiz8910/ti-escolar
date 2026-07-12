# Produção — WhatsApp (Twilio) — Checklist de go-live

> Guia operacional para tirar o TI-Escolar do **Sandbox** e colocar o WhatsApp em
> **produção real** com números próprios das escolas, via **Twilio como BSP**.
> WhatsApp é o **único canal** do produto — não há fallback (SMS/e-mail) previsto.

---

## 0. O que a Meta exige (o que é inevitável × o que dá para adiar)

WhatsApp é da Meta; **qualquer** caminho (Twilio, Meta Cloud API, 360dialog…) passa por ela.
São **três coisas distintas** — não confundir "aprovação" com uma coisa só:

| Etapa | Precisa? | Trava o lançamento? |
|---|---|---|
| **Registrar o número como WhatsApp Sender** (cria/usa um WABA) | Sempre | Não — é o *self sign-up*, ~minutos |
| **Aprovação de _templates_** (cada modelo de mensagem) | Sim, p/ enviar fora da janela de 24h | Rápido (minutos a horas) — **não** é "aprovar a empresa" |
| **Business Verification** (Meta verifica o CNPJ/empresa) | Só p/ **escalar** volume e nº de números | **Não** — vai ao ar sem ela, com limites |

**Resumo:** dá para ir para produção **sem esperar a verificação do negócio**, usando o
*self sign-up* do Twilio, aceitando os limites de negócio **não verificado** (ver §6).
O que **não** dá para evitar: registrar o número e ter templates aprovados.

---

## 1. Pré-requisitos (antes de começar)

- [ ] **Conta Twilio** paga (upgrade da conta trial) com método de pagamento ativo.
- [ ] **Meta Business Account** (Facebook Business Manager — `business.facebook.com`) da
      empresa que opera a plataforma. Anote o **Business Manager ID**.
- [ ] Uma **conta pessoal do Facebook** com papel de **admin** no Business Manager (o
      *self sign-up* abre um pop-up que exige login no Facebook).
- [ ] **Um número de telefone por escola** que você controle e que:
  - **não** esteja ativo no **WhatsApp/WhatsApp Business** (app do celular). Se estiver,
    **apague a conta do WhatsApp** naquele número antes;
  - consiga **receber o código de verificação** por **SMS ou ligação** (pode ser fixo);
  - não precisa ser um número Twilio — pode ser um número da escola.
- [ ] **Domínio público com HTTPS** para o backend (o webhook do Twilio precisa alcançá-lo).
      No deploy atual do Render isso já existe.
- [ ] **Nome de exibição (display name)** por escola que **cumpra as regras da Meta**
      (ex.: "Colégio São José") — nada de termos genéricos/enganosos.

---

## 2. Self sign-up (Embedded Signup) — passo a passo

O *self sign-up* é o fluxo do Twilio que registra um número WhatsApp **sem abrir ticket**:
o Twilio entra como **Tech Provider/BSP** e o número é ligado ao **seu** Meta Business.

1. **Twilio Console → Messaging → Senders → WhatsApp senders**
   (os rótulos do console mudam de tempos em tempos; o âncora é *WhatsApp senders*).
2. Clique em **Create new sender** / **Connect a WhatsApp number**.
3. No pop-up **"Continue with Facebook"**, faça login com a conta pessoal que é **admin**
   do Business Manager.
4. **Selecione (ou crie) o Meta Business Account** e o **WhatsApp Business Account (WABA)**.
   - Dica: use **um WABA** para a plataforma e vá **adicionando os números das escolas**
     nele (respeitando o limite de números — ver §6).
5. **Adicione o número de telefone** da escola e informe o **display name**.
6. **Verifique o número** com o **código OTP** (SMS ou ligação) que a Meta envia.
7. Ao concluir, o número aparece como **WhatsApp Sender** no Twilio, com um `From`
   no formato `whatsapp:+55...`.
8. A Meta revisa o **display name** (pode levar de minutos a ~1 dia). Enviar já funciona;
   o nome "pendente" não bloqueia o funcionamento técnico.

> Repita os passos 2–7 **para cada escola/número**. Cada número vira um Sender independente
> e recebe seu próprio webhook (§4).

---

## 3. Templates (mensagens fora da janela de 24h)

Todo disparo **iniciado pela escola** (broadcast/aviso) fora da janela de 24h exige um
**template aprovado**. Dentro da janela de 24h (resposta a uma mensagem do pai) pode ser
texto livre.

- [ ] Criar os templates no **Twilio Content Template Builder** (Content API) — cada um gera
      um **`ContentSid`** (ex.: `HXxxxxxxxx`).
- [ ] Escolher a **categoria** certa:
  - **utility** → avisos, lembretes, boletim, reunião (melhor entrega/preço, aprovação fácil) —
    **use isto para a maioria dos casos da escola**;
  - **marketing** → divulgação/captação (mais restrito);
  - **authentication** → OTP (não é o caso aqui).
- [ ] Definir as **variáveis** do template (`{{1}}`, `{{2}}`…) e um **exemplo** de preenchimento.
- [ ] Submeter e aguardar **aprovação da Meta** (normalmente minutos a horas).
- [ ] Escrever em **pt-BR, tom institucional** (padrão do produto).

---

## 4. Configuração no TI-Escolar

### 4.1 Variáveis de ambiente (produção)

```env
MESSAGE_CHANNEL=twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
# Número PADRÃO (fallback quando a escola não tem número próprio cadastrado):
TWILIO_WHATSAPP_FROM=whatsapp:+55...
# Callback público de status de entrega (mesmo endpoint do webhook):
TWILIO_STATUS_CALLBACK_URL=https://SEU_DOMINIO/api/webhook/twilio
# Tenant de fallback do inbound quando o "To" não casa com nenhuma escola:
TWILIO_DEFAULT_TENANT_ID=<uuid-da-escola-fallback>
# LIGAR em produção (valida X-Twilio-Signature nos webhooks):
TWILIO_VALIDATE_SIGNATURE=true
```

- [ ] Preencher todas as variáveis acima no ambiente de produção (Render).
- [ ] **`TWILIO_VALIDATE_SIGNATURE=true`** em produção (o webhook rejeita chamadas sem
      assinatura HMAC válida).

### 4.2 Número por escola (multi-tenant)

- [ ] No painel do super admin (**Escolas → cadastrar/editar**), preencher o
      **WhatsApp (E.164)** de cada escola com o número registrado no Sender (§2), ex.:
      `+5511999998888`.
  - O sistema **normaliza** para E.164 e **impede número duplicado** entre escolas.
  - **Vazio** = a escola usa o `TWILIO_WHATSAPP_FROM` padrão.
- Efeito automático (já implementado):
  - **Inbound:** o webhook roteia pelo número de destino (`To`) → a escola dona daquele número
    (`Tenant.whatsapp_numero`); sem correspondência, cai no `TWILIO_DEFAULT_TENANT_ID`.
  - **Outbound:** o broadcast sai do **número da própria escola** (`From`).

### 4.3 Webhook de cada Sender no Twilio

Para **cada** WhatsApp Sender, no Twilio Console (Sender → Configuration):

- [ ] **Incoming message** → `https://SEU_DOMINIO/api/webhook/twilio` (HTTP **POST**).
- [ ] **Status callback** → `https://SEU_DOMINIO/api/webhook/twilio` (HTTP **POST**).

O endpoint já trata **mensagens recebidas** (responde em TwiML) **e status de entrega**
(`sent`/`delivered`/`read`/`failed`, casando pelo `MessageSid`).

---

## 5. Envio por template aprovado (`ContentSid`) — ✅ implementado

A Meta **rejeita texto livre** em mensagens **iniciadas pela escola fora da janela de 24h**;
é obrigatório usar **template aprovado** via **Content API** do Twilio.

**Já feito no código:** `MessageTemplate` carrega `content_sid` (migration
`0010_template_content_sid`) e `TwilioMessageChannel.enviar_template`:
- **com `content_sid`** → envia via `ContentSid` + `ContentVariables` ({{1}},{{2}}… viram
  `{"1":…,"2":…}`) — caminho de **produção**;
- **sem `content_sid`** → renderiza o corpo como **texto livre** — Sandbox / dentro das 24h.

**O que ainda falta (dado, não lógica de envio):**
- [ ] **Cadastrar o `content_sid`** de cada template aprovado no registro do `MessageTemplate`
      do tenant. Hoje não há tela de administração de templates (roadmap), então isso é feito
      via **seed/atualização no banco** — ou pela futura tela de templates. Sem o `content_sid`
      preenchido, o disparo cai em texto livre (que a Meta bloqueia fora das 24h).

> Estado atual: **inbound e respostas dentro de 24h funcionam**; para broadcast em produção
> basta **preencher o `content_sid`** do template aprovado — a lógica de envio já está pronta.

---

## 6. Limites, tiers e Business Verification

- **Negócio NÃO verificado** (dá para ir ao ar assim):
  - ~**250** conversas iniciadas pela escola / 24h por número;
  - até **2 números** de telefone no WABA.
- **Negócio verificado** (Business Verification na Meta):
  - libera os tiers **1K → 10K → 100K → ilimitado** de destinatários únicos/24h, escalando
    conforme a **qualidade** do número;
  - permite **mais números** por WABA (necessário se você quer **um número por escola** em
    escala — com 2 números só dá para poucas escolas).
- [ ] Como o produto é **um número por escola**, planejar a **Business Verification** cedo
      (é o que destrava ter muitos Senders).
- [ ] Ajustar `META_DAILY_TIER_LIMIT` (cota diária usada por `MessageQuota`/`QuotaPolicy`)
      ao tier real do número.
- [ ] Cuidar da **qualidade do número** (evitar spam/altas taxas de bloqueio) — a Meta rebaixa
      o tier automaticamente se a qualidade cai.

---

## 7. Teste de fumaça pós go-live (por escola)

- [ ] Enviar uma mensagem **do celular de um pai** para o número da escola → deve chegar uma
      **resposta do bot** e a conversa aparecer no **Histórico → Conversas** daquela escola
      (roteamento por `To` correto).
- [ ] Disparar um **broadcast** de teste (template aprovado) para 1–2 contatos → conferir
      status `sent`/`delivered`/`read` no **Histórico → Mensagens em massa**.
- [ ] Confirmar que o broadcast saiu **com o número da própria escola** como remetente.
- [ ] Forçar uma **não-entrega** (número inválido) e conferir o relatório de não-entregues.
- [ ] Validar que uma chamada ao webhook **sem assinatura** é **rejeitada** (403).

---

## 8. Checklist consolidado (resumo)

**Operacional (Twilio/Meta)**
- [ ] Conta Twilio paga + Meta Business Account + admin no Facebook.
- [ ] Um número por escola (sem WhatsApp app ativo) + OTP.
- [ ] Self sign-up de cada número (Sender criado).
- [ ] Display name aprovado por escola.
- [ ] Templates (utility) criados e aprovados, com `ContentSid`.
- [ ] (Planejar) Business Verification para escalar números/volume.

**Configuração (TI-Escolar)**
- [ ] Env de produção preenchida (`MESSAGE_CHANNEL=twilio`, credenciais, callbacks).
- [ ] `TWILIO_VALIDATE_SIGNATURE=true`.
- [ ] `whatsapp_numero` cadastrado em cada escola.
- [ ] Webhook (incoming + status) apontado para o domínio em cada Sender.

**Código / dados (bloqueante para broadcast)**
- [x] Envio por `ContentSid` (Content API) no `TwilioMessageChannel` + campo `MessageTemplate.content_sid`.
- [ ] `content_sid` do template aprovado **preenchido** no tenant (seed/DB ou futura tela de templates).

**Validação**
- [ ] Teste de fumaça de inbound e outbound por escola (§7).

---

## Referências

- Twilio — WhatsApp senders / self sign-up (Embedded Signup) e Content Template Builder.
- Meta — WhatsApp Business Platform: business verification, messaging limits (tiers), políticas
  de template e de nome de exibição.

> Nota: os rótulos exatos do Twilio Console e os números de limite podem mudar; confirme
> sempre na documentação oficial no momento do go-live.
