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
| **WABA de produção** com número real | ⬜ Pendente — só existe a *Test WhatsApp Business Account* |
| **Forma de pagamento** na WABA de produção | ⬜ Pendente |
| **Templates aprovados** | ⬜ Pendente |
| **App publicado** (sair de "Em desenvolvimento") | ⬜ Pendente — ver §1.1 |
| **Inbound do webhook** (chatbot atendendo) | ✅ Implementado (27/jul/2026) — CLAUDE.md §9e.1 |
| **Multi-tenant de envio** (número por escola) | ✅ Implementado — `Tenant.meta_phone_number_id` |
| **Assinatura do webhook** (`X-Hub-Signature-256`) | ✅ **Ligada em produção** (27/jul/2026) |
| **Variáveis do Render** (`META_APP_SECRET`, `APP_ENV`, verify token) | ✅ Configuradas |

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
- [ ] **App** em `developers.facebook.com` com o produto **WhatsApp** adicionado
      (app id **`3140942352961209`** — 16 dígitos).
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

### 1.1 Publicar o app (feito pela metade)

O app fica em **"Modo: Em desenvolvimento"** até ser publicado, e nesse estado só conversa com
**números de teste** — nenhuma escola real funciona. A publicação exige os campos de
*Configurações do app → Básico*, que estavam vazios ou apontando para `facebook.com`.

**Preenchidos em 27/jul/2026** (`https://developers.facebook.com/apps/3140942352961209/settings/basic/`):

| Campo | Valor |
|---|---|
| URL da Política de Privacidade | `https://tiescolar.com.br/privacidade/` |
| URL dos Termos de Serviço | `https://tiescolar.com.br/termos/` |
| Exclusão de dados do usuário | `https://tiescolar.com.br/privacidade/` |
| E-mail de contato | `contato@tiescolar.com.br` |
| Categoria | Educação |

- [ ] **Falta clicar em "Publicar".** Apontar qualquer um desses campos para `facebook.com` é o
      mesmo tipo de inconsistência que reprovou a verificação da empresa em jul/2026 — para uma
      plataforma que processa dados de menores, o fluxo de exclusão de dados tem que ser o nosso.

> O **`META_APP_SECRET`** vive nessa mesma tela ("Chave Secreta do Aplicativo" → **Mostrar**),
> e revelá-lo **exige a senha do Facebook**.

---

## 2. Criar a WABA de produção e registrar o número

O modelo é **uma WABA nossa com o número de cada escola dentro dela** (até 20 números por WABA;
ao esgotar, cria-se outra sob o mesmo portfólio). Qualidade e tier de envio são **por número**,
então uma escola não derruba o limite das outras.

1. `developers.facebook.com` → app **Ti-Escolar** → **WhatsApp → Configuração da API**.
2. No seletor "De", **Adicionar número de telefone**. É esse fluxo que cria a WABA real ao lado
   da de teste.
3. Preencher **nome de exibição**, categoria e descrição do negócio.
4. **Verificar o número** por SMS ou ligação. Nós compramos o chip, colocamos num aparelho nosso
   e lemos o código — a escola não participa (CLAUDE.md §9e.3).
5. Anotar o **`phone_number_id`** do número e **cadastrá-lo na escola** (painel do super admin →
   Escolas → campo *phone_number_id da Meta*). É ele — não o E.164 — que a API usa para enviar e
   que roteia o WhatsApp recebido para a escola certa. **Sem ele a escola não recebe mensagens.**

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

**Já configuradas no Render (27/jul/2026):** `APP_ENV`, `META_WEBHOOK_VERIFY_TOKEN` (valor
forte, o default `changeme` deixou de funcionar), `META_APP_SECRET` e
`META_VALIDATE_SIGNATURE=true`. Verificado de fora: `POST /api/webhook/meta` sem assinatura
responde **403** (antes respondia 200 e processava).

> ⚠️ O 403 prova que a validação está **ligada**, **não** que o app secret está **correto** —
> um segredo errado devolve o mesmo 403. A única confirmação real é o passo 5 do teste de fumaça
> (§9): se a mensagem não chegar e o log mostrar `assinatura X-Hub-Signature-256 inválida`, o
> secret foi copiado errado.

**Faltam** `MESSAGE_CHANNEL=meta`, `META_ACCESS_TOKEN`, `META_WABA_ID` e `META_PHONE_NUMBER_ID`
— todos dependem da WABA de produção. Enquanto isso `/health` reporta `canal: demo`, que é o
estado honesto: sem token, a fábrica cai no canal demo mesmo que `MESSAGE_CHANNEL` diga `meta`.

Confira o resultado em **`/admin/seguranca`** no painel (super admin): a página lê a configuração
em execução e sinaliza segredo default, assinatura desligada e CORS liberado (CLAUDE.md §14).

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

1. `GET /health` responde `{"canal": "meta"}`.
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

## 10. Próximos passos para o WhatsApp funcionar 100%

**Já feito (não repetir):**

- [x] Verificação da empresa aprovada (27/jul/2026)
- [x] `Tenant.meta_phone_number_id` — multi-tenant de envio + roteamento do inbound
- [x] Inbound do webhook implementado (o chatbot atende)
- [x] `META_APP_SECRET` + `META_VALIDATE_SIGNATURE=true` no Render, **verificado em produção**
- [x] `META_WEBHOOK_VERIFY_TOKEN` forte (o default `changeme` já não funciona) e `APP_ENV`
- [x] Campos de privacidade/termos/exclusão/e-mail/categoria do app preenchidos (§1.1)

**Falta, nesta ordem** — os 3 primeiros são o caminho crítico porque destravam os demais:

1. [ ] **Publicar o app** (§1.1). Em "Em desenvolvimento" só há números de teste; nenhuma escola
       real funciona. Os campos que travavam isso já foram preenchidos.
2. [ ] **Criar a WABA de produção e registrar o número** (§2) — chip novo, nunca usado em
       WhatsApp, verificado por SMS/voz **por nós**. O **nome de exibição** passa por revisão
       assíncrona da Meta: **dispare este passo primeiro**, é o que dita o prazo.
3. [ ] **Forma de pagamento** na WABA de produção (§3). Sem cartão, o envio falha ao sair do
       volume gratuito.
4. [ ] **Token de usuário do sistema** (§4) → `META_ACCESS_TOKEN` no Render. O token da tela de
       Configuração da API expira em 24h e não serve.
5. [ ] **`MESSAGE_CHANNEL=meta`** + `META_WABA_ID` + `META_PHONE_NUMBER_ID` (fallback) no Render.
       Só depois do passo 4 — antes disso a fábrica cai no canal demo e o `/health` mentiria.
6. [ ] **Configurar o webhook** na Meta (§5): callback `https://ti-escolar.onrender.com/api/webhook/meta`,
       o verify token já cadastrado no Render, e **assinar o campo `messages`**.
7. [ ] **Cadastrar o `phone_number_id` na escola** (painel → Escolas). **Por escola.** Sem ele o
       inbound daquela escola é descartado de propósito — a lista marca com ⚠ quem está assim.
8. [ ] **Templates aprovados** no WhatsApp Manager, categoria *utility*, com **nome e idioma
       idênticos** aos do banco (§7).
9. [ ] **Teste de fumaça** completo (§9), incluindo o teste de duas escolas — é o que pega um
       `phone_number_id` cadastrado na escola errada.
10. [ ] **`/admin/seguranca` sem itens em Atenção** (CLAUDE.md §14).

**Higiene que não bloqueia o WhatsApp, mas não deve ir para escola real:**

- [ ] **`python -m app.seed` roda em toda subida de produção** (está no `CMD` do Dockerfile) e as
      variáveis `SUPER_ADMIN_*`/`DEMO_ADMIN_*` **não estão definidas no Render** — ou seja, os
      administradores são garantidos com as **senhas default do código**. Defina as variáveis ou
      condicione o seed a ambiente não-produtivo.
- [ ] **Rate limiting** no `POST /api/admin/login` e no webhook inbound (CLAUDE.md §15, item 5) —
      hoje não existe teto de tentativas contra as senhas de admin, nem de custo de LLM por
      remetente.

---

## Referências

- Cloud API — Introdução: <https://developers.facebook.com/docs/whatsapp/cloud-api>
- Webhooks e assinatura de payload:
  <https://developers.facebook.com/docs/graph-api/webhooks/getting-started>
- Limites de mensagens e qualidade:
  <https://developers.facebook.com/docs/whatsapp/messaging-limits>
- Templates: <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates>
