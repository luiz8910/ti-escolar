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
| **App publicado** ("Ao vivo") | ⬜ **Pendente e bloqueante** — ver §1.1 |
| **WABA de produção** | ✅ **Criada** (06/ago/2026) — id `2116419572321695`, nome de exibição `TI-Escolar` |
| **Número real registrado** | ⚠️ Cadastrado (`+55 15 99753-6978`) mas **"Não verificado"** — ver §2.1 |
| **Forma de pagamento** na WABA de produção | ⬜ Pendente |
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

Caminho: app → **Publicar** (menu lateral). Os requisitos que travavam a publicação (política de
privacidade, termos, exclusão de dados, e-mail de contato, categoria) já estão preenchidos e
apontam para `tiescolar.com.br` — a tela deve mostrar *"Todas as configurações necessárias do app
foram concluídas"*.

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
5. Anotar o **`phone_number_id`** do número e **cadastrá-lo na escola** (painel do super admin →
   Escolas → campo *phone_number_id da Meta*). É ele — não o E.164 — que a API usa para enviar e
   que roteia o WhatsApp recebido para a escola certa. **Sem ele a escola não recebe mensagens.**

### 2.1 Quando a verificação do número não chega (Brasil)

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
- **Prefira "Ligação telefônica" a SMS**: a rota de SMS A2P internacional para o Brasil é
  notoriamente instável. Trocar o método na tela de verificação já dispara a nova tentativa —
  clicar em "Reenviar código" depois disso duplica a solicitação.
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

## 10. Checklist consolidado

- [x] Verificação da empresa aprovada
- [ ] **App publicado ("Ao vivo")** — sem isso o webhook não recebe dado de produção nenhum (§1.1)
- [x] WABA de produção criada (id `2116419572321695`)
- [ ] Número da escola registrado e **verificado** (chip nosso) — ver §2.1 se o código não chegar
- [ ] Nome de exibição aprovado
- [ ] Forma de pagamento na WABA de produção
- [ ] Token de usuário do sistema gerado e no Render
- [ ] Webhook configurado e campo `messages` assinado
- [ ] `META_APP_SECRET` + `META_VALIDATE_SIGNATURE=true`
- [ ] `JWT_SECRET` e `META_WEBHOOK_VERIFY_TOKEN` trocados
- [ ] `/admin/seguranca` sem itens em Atenção
- [ ] Templates aprovados com nome/idioma batendo com o banco
- [x] **`Tenant.meta_phone_number_id` implementado** (multi-tenant de envio + roteamento inbound)
- [x] **Inbound do webhook implementado** (chatbot atendendo)
- [ ] **`phone_number_id` cadastrado na escola** (por escola — sem ele o inbound é descartado)
- [ ] Teste de fumaça por escola

---

## Referências

- Cloud API — Introdução: <https://developers.facebook.com/docs/whatsapp/cloud-api>
- Webhooks e assinatura de payload:
  <https://developers.facebook.com/docs/graph-api/webhooks/getting-started>
- Limites de mensagens e qualidade:
  <https://developers.facebook.com/docs/whatsapp/messaging-limits>
- Templates: <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates>
