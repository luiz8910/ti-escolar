# Esteiras de deploy — homolog e produção

> Escrito em 02/set/2026, quando o deploy dos back-ends deixou de ser manual. A topologia
> dos ambientes está em §12a ([`docs/guia/roadmap.md`](guia/roadmap.md)); a receita da Fly,
> em [`producao-fly.md`](producao-fly.md).

## O modelo de branches

```
feature/…  ─PR─▶  develop  ──▶ HOMOLOG    (Render + Vercel)
                     │
                     └─PR─▶  main  ──▶ PRODUÇÃO  (Fly.io + Cloudflare Pages)
```

Duas branches de longa vida, uma por ambiente. **A branch é o ambiente**: o que está na
`develop` é o que a escola-cobaia vê no homolog, e o que está na `main` é o que a Rosa Cury
vê. Não há branch de release nem cherry-pick — o caminho de um commit até a produção passa
obrigatoriamente pelo homolog, e é isso que dá sentido a ter dois ambientes.

Trabalho novo sai da `develop`; a promoção para produção é um PR `develop → main`. A
`develop` nasceu da `main` em 02/set/2026, então as duas partem do mesmo lugar.

> **Ao abrir o PR de promoção, confira o `baseRefName`.** Um PR aberto por engano de
> `feature → develop` quando devia ser `develop → main` merga verde e não publica nada em
> produção — o mesmo tipo de silêncio que já deixou o Render dias atrás da `main`.

## O que roda em cada evento

| Evento | Workflow | O que acontece |
|---|---|---|
| PR para `develop` ou `main` | `ci.yml` | ruff, cadeia de migrations, `alembic upgrade head`, seed, pytest, typecheck e build de `web/` e `site/` |
| PR que toca `site/` | `site.yml` | build + **preview** na Cloudflare Pages, com a URL comentada no PR |
| PR que toca `web/` | `web.yml` | build e typecheck, **sem** preview (ver abaixo) |
| push na `develop` | `deploy-homolog.yml` | CI → deploy no Render → confirma o commit no ar → prontidão → postura (observação) |
| push na `main` | `deploy-producao.yml` | CI → `fly deploy` → confirma o commit no ar → prontidão → canal → postura (**estrita**) |
| push na `main` que toca `web/`/`site/` | `web.yml` / `site.yml` | publica o front na Cloudflare Pages |
| segunda, 9h | `lgpd.yml` | postura dos dois ambientes, sem depender de deploy |

O `ci.yml` não tem gatilho de `push`: nas branches de ambiente quem o executa são as
esteiras, por `workflow_call`. Assim a suíte roda **uma vez** por push, e o deploy é
literalmente o mesmo run que testou — não um run paralelo que talvez tenha passado.

O painel não tem preview de PR de propósito: o CORS da API de produção só libera
`https://app.tiescolar.com.br`, então um painel em `*.pages.dev` abriria sem carregar nada.

## Como a esteira sabe que publicou

Esta é a parte que não existia. Quando o deploy **não** acontece, o ambiente continua
respondendo `200 ok` no `/health` — "publiquei" e "achei que publiquei" são
indistinguíveis de fora, e foi assim que o Render ficou dias atrás da `main` com
`/health/pronto` respondendo 404 (09/ago/2026).

Agora o `/health` ecoa **o commit da imagem** no campo `versao`, e a esteira espera até que
ele seja o commit que ela acabou de publicar ([`scripts/aguarda_deploy.sh`](../scripts/aguarda_deploy.sh)):

```json
{"status": "ok", "llm": "anthropic", "canal": "meta", "versao": "81858b8…"}
```

De onde vem o valor em cada ambiente:

- **Render:** injeta `RENDER_GIT_COMMIT` sozinho, em tempo de execução — nada a fazer.
- **Fly:** entra na imagem como build-arg (`fly deploy --build-arg GIT_SHA=…`), porque não
  existe equivalente automático.
- **Local / compose:** ninguém passa nada e o campo responde `desconhecida`. A esteira
  distingue os três casos: commit certo (passa), **outro** commit (reprova — o deploy não
  chegou) e `desconhecida` (avisa, não reprova; só acontece na imagem anterior a este
  mecanismo).

Depois disso a produção ainda confere duas coisas que o `/health` sozinho não garante:
`/health/pronto` (a aplicação alcança o banco) e a **ausência de `canal_alerta`** — com
`MESSAGE_CHANNEL=meta` e sem `META_ACCESS_TOKEN` a aplicação sobe falando pelo canal demo,
sem erro nenhum, e o WhatsApp fica fora do ar em silêncio (§9c).

## O que cadastrar no repositório

**Settings → Secrets and variables → Actions.** Sem eles as esteiras rodam, avisam no
resumo e **pulam o deploy** — em vez de falhar por um motivo que não é de código.

| Nome | Tipo | Onde conseguir |
|---|---|---|
| `RENDER_DEPLOY_HOOK_URL` | secret | Render → serviço → Settings → **Deploy Hook** |
| `FLY_API_TOKEN` | secret | `fly tokens create org` (o mesmo de `~/.config/ti-escolar/segredos/fly.env`) |
| `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` | secrets | já exigidos por `web.yml` e `site.yml` |
| `HOMOLOG_BASE_URL` | variable | URL da API no Render (ex.: `https://ti-escolar.onrender.com`) |
| `PRODUCAO_BASE_URL` | variable | `https://api.tiescolar.com.br` |

**Ambientes do GitHub** (Settings → Environments): os jobs de deploy declaram `homolog` e
`producao`. Criá-los é opcional — o job roda mesmo sem —, mas é ali que se pendura *required
reviewer* para segurar a publicação em produção atrás de um clique humano, sem tocar no YAML.

### Três ajustes de uma vez só, fora do git

1. **Render → o serviço aponta para `develop`.** O deploy hook publica o commit passado em
   `?ref=`, mas o painel e um deploy manual seguem a branch configurada no serviço; deixá-la
   na `main` faria o homolog receber produção.
2. **Vercel → *Production Branch* = `develop`.** O painel de homolog continua lá, com
   integração própria com o git; nenhuma esteira daqui o toca (duplicar isso exigiria um
   token da Vercel no repositório sem ganhar nada).
3. **Proteção de branch na `main`**: exigir o status check do CI e PR. É o que impede um
   push direto de publicar em produção sem revisão.

## O que continua manual, e por quê

- **Migration de banco não tem rollback automático.** O `release_command` da Fly aborta o
  deploy se a migration falhar, mas voltar a imagem **não** desfaz o schema — o
  [`runbook-rollback.md`](runbook-rollback.md) continua sendo o caminho.
- **Ligar o canal do WhatsApp em produção** (`MESSAGE_CHANNEL=meta` no `fly.toml` + segredos
  `META_*`): a Meta aceita uma única URL de webhook por app, e apontá-la para a produção tira
  o inbound do homolog do ar no mesmo instante. É uma decisão, não um passo de esteira.
- **Segredos**: ficam na Fly e no Render, nunca no repositório. O `FLY_API_TOKEN` do CI dá
  acesso de deploy; trate-o como credencial de produção.

## Rollback

```bash
# Produção — volta para uma imagem já publicada (não desfaz migration)
fly releases --app ti-escolar
fly deploy --image registry.fly.io/ti-escolar:deployment-XXXX

# Ou pela esteira: reverta o commit na `main` (git revert) e deixe o push publicar.
```

Reverter pelo git é preferível quando dá: mantém a `main` igual ao que está no ar, que é a
premissa de todo o resto deste documento. `fly deploy --image` é o caminho quando a pressa
não deixa esperar um CI.
