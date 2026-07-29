# Runbook — rollback de produção

> Item 9 do checklist de pré-deploy (§15). O que fazer quando um deploy quebra produção:
> onde clicar, o que esperar e o que **não** volta sozinho.
>
> **Este runbook nunca foi executado em produção.** Ele descreve o caminho correto a
> partir da arquitetura do projeto e da documentação dos provedores. A primeira execução
> deve ser um **ensaio agendado** (§ "Ensaio obrigatório"), não a estreia durante um
> incidente.

---

## 0. A regra que dita tudo: rollback de aplicação **não** desfaz migration

As três camadas voltam com um clique. O **banco não**. Alembic é o único componente que
avança o estado de forma que o rollback do provedor não enxerga.

| Camada | Onde | Reversível por clique? |
|---|---|---|
| Back-end (FastAPI) | Render | Sim |
| Painel (`web/`) | Vercel | Sim |
| Landing page (`site/`) | Cloudflare Pages | Sim |
| **Schema do banco** | **Neon (via Alembic)** | **Não — exige `alembic downgrade`** |

Consequência prática: se o deploy ruim rodou uma migration destrutiva (`DROP COLUMN`,
`DROP TABLE`), voltar só a aplicação deixa o **schema à frente do código**. O código
antigo faz `SELECT` de uma coluna que não existe mais e quebra em toda requisição — um
estado pior que o do bug original.

**Antes de reverter, responda:** *o deploy ruim rodou migration?*

```bash
# No repositório, compare o head atual com o do deploy anterior:
git log --oneline -- backend/alembic/versions | head -5
```

Se as duas versões apontam para a mesma migration, siga direto para o passo 1 e ignore o
passo 3.

---

## 1. Back-end — Render

**Quando usar:** erro 500 generalizado, `/health/pronto` respondendo `degradado`, ou o
painel de Logs (`/admin/logs`) acusando pico de erros logo após um deploy.

1. Acesse <https://dashboard.render.com> → selecione o serviço do back-end.
2. Abra a aba **Events** (ou **Deploys**, conforme a versão da interface).
3. Localize o **último deploy com status `Live`/`Succeeded` anterior ao problema**.
   Confira o hash do commit — ele precisa bater com o que você espera.
4. No menu **⋯** da linha desse deploy, escolha **Rollback to this deploy**
   (em algumas versões: **Redeploy**).
5. Confirme.

**Resultado esperado:** um novo deploy entra em `Building` → `Live` em ~2–5 min (o
container reconstrói). O `CMD` roda `alembic upgrade head` + `python -m app.bootstrap`
antes de subir a API — ou seja, **o rollback tenta aplicar migrations de novo**; com o
banco já no head, isso é no-op e sai como "Running upgrade ... nothing to do".

**Verificação:**

```bash
curl -s https://<seu-servico>.onrender.com/health/pronto
# esperado: {"status":"ok","banco":"ok"}
```

E, no painel, `/admin/logs` deve parar de acumular linhas `ERROR`.

> ⚠️ **O Auto-Deploy vai desfazer o seu rollback.** O Render está com Auto-Deploy ligado
> na `main`: o próximo push (de qualquer pessoa) reconstrói a versão quebrada. O rollback
> é **paliativo** — o passo definitivo é reverter o commit:
>
> ```bash
> git revert <hash-do-commit-ruim>   # ou git revert <hash-do-merge> -m 1
> git push origin main
> ```
>
> Se o incidente for longo, desligue o Auto-Deploy em **Settings → Build & Deploy →
> Auto-Deploy: No** enquanto investiga, e religue depois.

---

## 2. Painel — Vercel

**Quando usar:** tela branca, erro de runtime no navegador, build publicada com bug de
interface. O back-end não é afetado.

1. Acesse <https://vercel.com> → projeto do painel → aba **Deployments**.
2. Localize o deploy anterior marcado como **Ready** e que estava em produção.
3. No menu **⋯** → **Instant Rollback** (ou **Promote to Production**).
4. Confirme.

**Resultado esperado:** a troca é quase instantânea (segundos) — a Vercel apenas repõe um
build já existente, sem reconstruir. Recarregue o painel com cache limpo
(`Ctrl+Shift+R`) e confirme que a versão antiga voltou.

Vale o mesmo aviso do Render: o próximo push na `main` republica a versão quebrada.
Reverta o commit.

---

## 3. Banco — o passo que ninguém lembra

Só necessário se o deploy ruim **rodou migration**. Duas situações, muito diferentes:

### 3a. Migration aditiva (`ADD COLUMN`, `CREATE TABLE`, `CREATE INDEX`)

**Não faça nada.** Uma coluna a mais que o código antigo ignora é inofensiva. Reverter
aqui só cria risco. As migrations `0025`, `0026`, `0027` e `0028` são todas aditivas.

### 3b. Migration destrutiva (`DROP COLUMN`, `DROP TABLE`)

É o caso da `0023_remover_content_sid`, que faz `DROP COLUMN`. Aqui o `downgrade` é
obrigatório — e **o dado apagado não volta com ele**: o `downgrade` recria a coluna
vazia. Recuperar o conteúdo exige o passo 4 (restauração do banco).

Como executar:

```bash
# Opção A — pelo Shell do Render (Dashboard → serviço → aba "Shell"):
alembic current            # confirme em que revisão o banco está
alembic downgrade -1       # volta uma migration
alembic current            # confirme que voltou

# Opção B — da sua máquina, apontando para o banco de produção:
cd backend
DATABASE_URL="<connection string do Neon>" .venv/bin/alembic current
DATABASE_URL="<connection string do Neon>" .venv/bin/alembic downgrade -1
```

**Resultado esperado:** a saída indica `Running downgrade <head> -> <anterior>`. Depois
disso, `alembic current` mostra a revisão anterior.

> ⚠️ **Ordem importa.** Faça o `downgrade` **depois** de reverter a aplicação, nunca
> antes: entre um e outro, a aplicação nova estaria rodando contra um schema antigo.
> A janela de indisponibilidade é inevitável nesse caminho — este projeto não é
> blue-green.

> ⚠️ **Cuidado com o `CMD`.** O container roda `alembic upgrade head` ao subir. Se você
> fizer `downgrade` e o serviço reiniciar (deploy, restart, escala), a migration é
> **reaplicada**. Por isso o `downgrade` só é seguro depois que a aplicação já foi
> revertida para uma versão cujo head seja a revisão de destino.

---

## 4. Restaurar dado perdido — Neon

Para quando o problema não é código, e sim dado: uma migration que apagou coluna, um
`DELETE` errado, uma remoção de escola executada por engano (a cascata de
`SqlTenantRepository.remover` apaga mensagens, conversas, alunos e fichas).

1. Acesse <https://console.neon.tech> → projeto `ti-escolar`.
2. **Branches** → **Create branch** → escolha **Time travel / From a point in time** e
   informe o instante **imediatamente anterior** ao incidente.
3. A branch nova nasce com os dados daquele momento e ganha sua própria connection
   string.
4. **Não aponte a produção para a branch ainda.** Conecte-se a ela primeiro e confirme
   que o dado está lá:

   ```bash
   psql "<connection string da branch>" -c "SELECT count(*) FROM alunos;"
   ```

5. Com o dado conferido, escolha:
   - **Recuperação cirúrgica** (preferível): exporte só o que se perdeu da branch e
     insira na produção — não descarta o que foi criado depois do incidente.
   - **Troca completa**: aponte `DATABASE_URL` do Render para a branch restaurada.
     **Descarta tudo que aconteceu depois do ponto de restauração.**

**A janela de retenção depende do plano do Neon.** Confirme o valor atual em
**Settings → Storage / History retention** do projeto **antes** de precisar dela — ver
`docs/backup.md`.

---

## 5. Landing page — Cloudflare Pages

Baixo risco (site estático, sem dado), mas o caminho existe:

1. <https://dash.cloudflare.com> → **Workers & Pages** → projeto `ti-escolar-site`.
2. Aba **Deployments** → localize o deploy anterior.
3. **⋯ → Rollback to this deployment** → confirmar.

**Resultado esperado:** propagação em segundos. Confirme em <https://tiescolar.com.br>
com cache limpo.

---

## 6. Ordem de execução num incidente real

1. **Estancar** — rollback da camada afetada (Render e/ou Vercel).
2. **Confirmar** — `/health/pronto` em `ok` e `/admin/logs` sem novos `ERROR`.
3. **Impedir a volta** — `git revert` do commit ruim + push (ou desligar o Auto-Deploy).
4. **Só então** avaliar o banco: precisa de `downgrade`? Precisa de restauração?
5. **Registrar** — anote no post-mortem o id de correlação de um dos erros
   (`X-Request-Id`); ele localiza a linha exata no painel de Logs.

---

## Ensaio obrigatório

O item 9 do checklist **continua em dívida enquanto este runbook não for executado uma
vez em condições controladas**. Roteiro sugerido, em horário de baixo uso:

1. Faça um commit inócuo (mudar um texto de tela) **acompanhado de uma migration
   aditiva** — para o ensaio exercitar o caso que dá medo, não o trivial.
2. Deixe subir para produção normalmente.
3. Execute o passo 1 (Render) e o passo 2 (Vercel).
4. Cronometre: **quanto tempo até o serviço voltar?** Esse número é o seu RTO real, e é o
   que você vai poder prometer à escola.
5. Rode `alembic downgrade -1` e depois `alembic upgrade head`, confirmando que os dois
   caminhos funcionam.
6. Anote aqui o que divergiu deste documento — a interface dos provedores muda.

**Resultado do último ensaio:** _(nunca executado)_
