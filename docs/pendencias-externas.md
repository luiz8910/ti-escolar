# Pendências externas — o que só você pode destravar

> Este arquivo existe porque a mesma pergunta se repetiu: *"onde a gente parou mesmo?"* — e
> a resposta, mais de uma vez, foi **fora do terminal**. Nada aqui é código. São ações que
> exigem navegador, cartão, chip, senha do Facebook ou um clique no painel de um provedor —
> coisas que o Claude Code não pode fazer por você, e que travam trabalho já pronto.
>
> **Regra do arquivo:** um item entra aqui quando existe **código pronto esperando por ele**.
> Ideia sem código não é pendência externa — é roadmap (§12a). Item resolvido sai daqui e
> vira uma linha no documento do assunto; este arquivo não é histórico.
>
> Cada item traz **o que está travado**, **o que só você faz** e **como conferir que caiu** —
> essa última coluna é o que impede o item de ficar "mais ou menos resolvido" para sempre.

---

## 1. Esteira de deploy — código pronto, sem push, sem PR  ⛔ **maior bloqueio hoje**

**Estado:** a branch **`feat/pipelines-homolog-producao`** (commit `4090235`, escrito em
02/set/2026) ficou **três dias só na máquina** — sem push, sem PR. Foi publicada em
06/set e está no **[PR #87](https://github.com/luiz8910/ti-escolar/pull/87)**, aguardando
merge. Ela traz `deploy-homolog.yml`, `deploy-producao.yml`, `postura.yml`, o `/health`
ecoando o **commit da imagem** (`versao`), `scripts/aguarda_deploy.sh` e `docs/pipelines.md`.

**O que está travado:** enquanto o PR não entrar, continua valendo o aviso do índice —
*mergear na `main` não publica nada*. Foi exatamente esse silêncio que deixou o Render dias
atrás da `main` em 09/ago, com `/health/pronto` respondendo 404 em produção. **E o merge
sozinho não basta:** sem os segredos abaixo a esteira entra no ar e pula o deploy.

**O que só você faz** (Settings → Secrets and variables → Actions):

| Nome | Tipo | Onde conseguir | Já existe? |
|---|---|---|---|
| `RENDER_DEPLOY_HOOK_URL` | secret | Render → serviço → Settings → **Deploy Hook** | ❌ |
| `FLY_API_TOKEN` | secret | `fly tokens create org` (o mesmo de `~/.openclaw/fly/credenciais.env`) | ❌ |
| `HOMOLOG_BASE_URL` | variable | `https://ti-escolar.onrender.com` | ❌ |
| `PRODUCAO_BASE_URL` | variable | `https://api.tiescolar.com.br` | ❌ |
| `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` | secrets | já cadastrados (21/ago e 26/jul) | ✅ |

E três ajustes nos painéis, fora do git:

1. **Render → o serviço aponta para `develop`.** O hook publica o commit do `?ref=`, mas o
   painel e um *Manual Deploy* seguem a branch configurada no serviço: deixá-la na `main`
   faz o **homolog receber produção**.
2. **Vercel → *Production Branch* = `develop`.**
3. **Proteção de branch na `main`**: exigir PR e o status check do CI — é o que impede um
   push direto de publicar em produção.

**Como conferir que caiu:** um push na `develop` termina com o `/health` do Render devolvendo
o **mesmo `versao`** do commit empurrado. Sem os segredos a esteira **não falha** — ela avisa
no resumo e **pula o deploy**, de propósito, para não reprovar por motivo que não é de código.

> **Ordem que importa:** mergear o PR #87 **e** cadastrar os quatro itens acima. Segredo sem
> a esteira no repositório não faz nada; esteira sem segredo publica nada.

---

## 2. Arquivos no S3 — os buckets existem, o usuário IAM não

**Estado:** `ti-escolar-190446415519-sa-east-1-an` (produção) e
`ti-escolar-homolog-190446415519-sa-east-1-an` (homolog) estão criados em `sa-east-1`, com
acesso público bloqueado, ACLs desligadas, `aws:SecureTransport = false` negado e lifecycle
(`rede-de-seguranca-doc-395d`, `rede-de-seguranca-impressao-180d`). O adaptador `S3ArquivoStorage`
está escrito e testado.

**O que está travado:** **nada disso tem efeito.** Sem credencial, `ARQUIVO_STORAGE` continua
em `postgres` e os bytes seguem no `bytea` — inclusive a foto do aluno, que nasce lá para ser
migrada depois.

**O que só você faz:** criar **um usuário IAM por ambiente** no console da AWS e colar a
chave nos segredos da Fly (produção) e do Render (homolog): `ARQUIVO_STORAGE=s3`,
`S3_BUCKET_DOCUMENTOS`, `AWS_REGION=sa-east-1`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.

> **A armadilha do IAM com SSE-KMS:** policy só com `s3:PutObject`/`GetObject` **não basta** —
> o `PutObject` falha com `AccessDenied` na hora de gerar a chave de dados. Precisa de
> `kms:GenerateDataKey` e `kms:Decrypt`, restritos por `kms:ViaService = s3.sa-east-1.amazonaws.com`.

**Como conferir que caiu:** subir um documento pelo WhatsApp e ver o objeto aparecer no bucket
sob `doc/{tenant}/…` — e o download pelo painel continuar funcionando (ele nunca é URL pública).

Detalhe em [`plano-correcoes-teste-10-08.md`](plano-correcoes-teste-10-08.md), Fase 0.

---

## 3. Meta — o outbound nunca foi provado em real

**Estado:** verificação da empresa **aprovada**, WABA de produção `2116419572321695` criada,
inbound funcionando em produção desde 10/ago. O onboarding de número está automatizado no
painel (`/admin/escolas/whatsapp`).

**O que está travado:** o **disparo (outbound)** — templates e broadcast. Custa dinheiro por
mensagem, então não dá para provar sem cartão.

**O que só você faz:**
1. **Forma de pagamento na WABA** — o país de cobrança ainda está em **"Índia"**; precisa
   virar Brasil **antes** do cartão.
2. **Perfil da WABA**: endereço, moeda e fuso (`America/Los_Angeles` → `America/Sao_Paulo`).
3. **Submeter os templates** e esperar a aprovação da Meta.
4. **Chip da Rosa Cury** — comprar, pôr num aparelho, ler o código de verificação e guardar o
   **PIN de duas etapas no gerenciador de senhas** (ele não é persistido de propósito: guardar
   num banco multi-tenant o segredo que reassume o canal de todas as escolas trocaria um passo
   manual por um alvo).

> **Teto do portfólio: 2 números, 1 ocupado** pela Escola Demonstração.

**Como conferir que caiu:** um broadcast por template chega no celular de verdade, e o
histórico do painel mostra `entregue` — não `enfileirado`.

Roteiro em [`producao-whatsapp.md`](producao-whatsapp.md).

---

## 4. Revisão jurídica de `/privacidade` e `/termos`

Os textos no ar em `site/` foram redigidos a partir do funcionamento real do produto e
**valem** para a Meta e para o usuário — mas ainda **não passaram por advogado**, e é como
instrumento contratual com escola pagante que eles vão ser lidos. Não bloqueia código;
bloqueia assinar contrato.

---

## O que **não** está aqui, de propósito

Coisa que é trabalho meu e está na fila normal: fila/worker para o webhook não depender da
latência da LLM, `expira_em` na solicitação de impressão, teste cruzado entre duas escolas.
Isso é roadmap (§12a) — misturar com o que depende de você é o jeito mais rápido de perder
os dois.
