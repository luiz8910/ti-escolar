# Produção na Fly.io — back-end

> O **homolog continua no Render** e não foi tocado. Este documento é só sobre o ambiente
> de **produção**, criado em 20/ago/2026. A topologia das três camadas está em §12a
> ([`docs/guia/roadmap.md`](guia/roadmap.md)).

| | |
|---|---|
| App | `ti-escolar` (org `personal` / Luiz Fernando Sanches) |
| Região | `gru` (São Paulo) |
| Config | [`backend/fly.toml`](../backend/fly.toml) |
| Host interno | `ti-escolar.fly.dev` |
| Host público | `api.tiescolar.com.br` |
| IPs | IPv4 **compartilhado** `66.241.124.139` (grátis) + IPv6 dedicado `2a09:8280:1::179:2635:0` |
| Máquina | 1 × `shared-cpu-1x` / 512 MB / swap 512 MB — ~US$ 3,2/mês |

## Deploy

```bash
export FLY_API_TOKEN=...        # ~/.openclaw/fly/credenciais.env (Organization Token)
cd backend && fly deploy        # o contexto do build é backend/, não a raiz
```

**Deploy é manual, como no Render** — mergear na `main` não publica nada. A diferença é que
aqui o comando existe: `fly deploy` faz build, sobe a imagem, roda o `release_command` e
troca a máquina.

> **`--ha=false` no primeiro deploy de um grupo novo.** O `flyctl` cria **duas** máquinas por
> conta própria ("Creating a second machine for high availability"), e nem
> `min_machines_running = 1` nem `[[vm]]` no `fly.toml` o impedem — foi o que aconteceu em
> 21/ago/2026, corrigido depois com `fly scale count 1`. Duas máquinas aqui não duplicam
> disparo (o `pg_try_advisory_lock` da retomada segura), mas metade dos disparos manuais
> deixa de sair na hora: o cutucão é um `asyncio.Event` em memória. Confira com
> `fly machine list` depois de cada deploy que mexa em grupo de processos.

Três coisas que o `fly.toml` faz de propósito, e que quebram se alguém "simplificar":

1. **`release_command` roda as migrations**, não o `CMD`. No Render o `alembic upgrade head`
   está no `CMD` e roda a cada restart — o que desfaz sozinho um `downgrade` de rollback
   (§ [`runbook-rollback.md`](runbook-rollback.md)). Aqui a migration roda uma vez, numa
   máquina temporária, e **um erro nela aborta o deploy** antes de qualquer tráfego chegar.
   O `[processes]` sobrescreve o `CMD` justamente para tirar o alembic do boot.
2. **Uma máquina só, que não dorme.** O cutucão que faz o disparo manual sair na hora é um
   `asyncio.Event` em memória: com duas máquinas, metade dos disparos esperaria a próxima
   passada da retomada. E `auto_stop_machines = false` porque o processo tem trabalho de
   fundo (gravador de logs, retomada de disparos) e o webhook da Meta não espera cold start.
3. **O contexto do build é `backend/`.** O `Dockerfile` faz `COPY pyproject.toml ./`; com o
   `fly.toml` na raiz do repositório o build falha na primeira camada.

## Segredos

Ficam na Fly (`fly secrets`), nunca no repositório. A Fly **não mostra o valor depois de
gravado** — só o digest —, então os que foram gerados aqui estão em
`~/.openclaw/fly/ti-escolar-producao.env` (permissão 600), na mesma pasta do token.

```bash
fly secrets list --app ti-escolar                    # nomes e digests
grep -v '^#' arquivo.env | fly secrets import --app ti-escolar
```

| Segredo | Estado |
|---|---|
| `DATABASE_URL` | Neon de produção (nasce vazio; o bootstrap cria só o super admin) |
| `JWT_SECRET` | gerado |
| `META_WEBHOOK_VERIFY_TOKEN` | gerado |
| `SUPER_ADMIN_EMAIL` / `_SENHA` / `_NOME` | gerados — **troque a senha no primeiro login** |
| `META_ACCESS_TOKEN`, `META_APP_SECRET`, `META_PHONE_NUMBER_ID` | **pendentes** — só ao ligar o canal |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` + `LLM_PROVIDER` | **pendentes** — sem eles o bot responde com o provider `fake` |

O que **não** é segredo (`APP_ENV`, `MESSAGE_CHANNEL`, CORS…) mora no `[env]` do `fly.toml`,
versionado, porque esconder configuração de ambiente num painel é como o deploy do Render
ficou atrás da `main` sem ninguém perceber.

## O canal do WhatsApp entra desligado

`MESSAGE_CHANNEL=demo` no primeiro deploy, **de propósito**: a Meta aceita **uma única URL de
webhook por app**, e apontá-la para cá tiraria o inbound do homolog do ar no mesmo instante.
Para ligar, na ordem:

1. `api.tiescolar.com.br` respondendo com certificado válido (abaixo);
2. `fly secrets import` com `META_ACCESS_TOKEN`, `META_APP_SECRET` e `META_PHONE_NUMBER_ID`;
3. `MESSAGE_CHANNEL = "meta"` no `fly.toml` + `fly deploy`;
4. no app da Meta, webhook → `https://api.tiescolar.com.br/webhook/meta`, com o
   `META_WEBHOOK_VERIFY_TOKEN` de produção;
5. conferir `GET /health`: o campo `canal` é o adaptador **efetivo**. Se voltar `demo` com a
   env em `meta`, falta token — o processo sobe igual e as mensagens somem em silêncio
   (§9c). O corpo traz `canal_alerta` explicando.

## DNS e certificado

O certificado já foi criado na Fly (`fly certs list --app ti-escolar`) e fica *Awaiting
configuration* até os registros existirem na zona `tiescolar.com.br` (Cloudflare):

| Tipo | Nome | Valor | Proxy |
|---|---|---|---|
| CNAME | `api` | `8wxg2m8.ti-escolar.fly.dev` | **DNS only** (nuvem cinza) |
| CNAME | `_acme-challenge.api` | `api.tiescolar.com.br.8wxg2m8.flydns.net` | DNS only |

O proxy da Cloudflare **precisa ficar desligado**: com a nuvem laranja o desafio ACME não
chega na Fly e o certificado nunca é emitido. Depois:

```bash
fly certs check api.tiescolar.com.br --app ti-escolar
```

## Rollback

```bash
fly releases --app ti-escolar          # lista as versões
fly deploy --image registry.fly.io/ti-escolar:deployment-XXXX   # volta para uma imagem
fly machine restart <id> --app ti-escolar
```

Voltar a imagem **não desfaz a migration**. Para banco, o
[`runbook-rollback.md`](runbook-rollback.md) continua valendo — e aqui ele funciona de
verdade, porque o `alembic upgrade head` saiu do boot.

## Custo

~US$ 3,2/mês da máquina + IPv4 compartilhado e IPv6 grátis. **A Fly não tem teto de gasto
nem alerta de cobrança**; quem vigia é o cron `fly-gasto` (seg-sex, 9h), que projeta o mês e
avisa no WhatsApp. Ele lê o que está provisionado — se aparecer uma segunda máquina, um
volume ou um IPv4 dedicado, o número sobe no dia seguinte. O builder remoto
(`fly-builder-*`) aparece na lista de apps e só é cobrado enquanto está ligado.
