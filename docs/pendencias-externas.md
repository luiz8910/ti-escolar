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

## 2. Arquivos no S3 — falta publicar o adaptador e colar as envs

**Estado:** `ti-escolar-190446415519-sa-east-1-an` (produção) e
`ti-escolar-homolog-190446415519-sa-east-1-an` (homolog) estão criados em `sa-east-1`, com
acesso público bloqueado, ACLs desligadas, `aws:SecureTransport = false` negado e lifecycle
(`rede-de-seguranca-doc-395d`, `rede-de-seguranca-impressao-180d`). O adaptador
`S3ArquivoStorage` **está na `develop`** desde 16/set/2026, com `listar_chaves` para o
varredor de órfãos, e a fábrica `criar_arquivo_storage`/`storage_efetivo` escolhe o adaptador
pela env. Testado contra MinIO de verdade (compose + CI), não contra mock.

> Antes disso ele passou **um mês numa branch que nunca foi mergeada** (`feat/arquivos-no-s3`,
> 17/ago/2026): estava "escrito e testado" e, ao mesmo tempo, ausente do código que roda. Foi
> o terceiro caso do mesmo padrão, junto do §1 e da documentação do §0 — e é por isso que
> **"está pronto" só conta quando está na `develop`**.

**Usuários IAM criados em 18/set/2026**, e não mais no console: o template
[`infra/aws/s3-usuarios-iam.yaml`](../infra/aws/s3-usuarios-iam.yaml) cria **um por
ambiente**, uma stack cada (`ti-escolar-s3-usuario-prod` → usuário `ti-escolar-prod-s3`;
`ti-escolar-s3-usuario-homolog` → `ti-escolar-homolog-s3`). Sem acesso ao console, política
em linha restrita ao bucket **daquele** ambiente, e o bloco KMS preso por `kms:ViaService`.

Provado com a chave real, não só no simulador de políticas: `put`/`get`/`list`/`delete`
passam no próprio bucket e o objeto sai `aws:kms`; o bucket do outro ambiente,
`PutObjectAcl`, `DeleteBucket` e a política do bucket dão `AccessDenied`.

> **A chave de acesso não é recurso da stack, de propósito.** O `SecretAccessKey` de um
> `AWS::IAM::AccessKey` só sai por `!GetAtt`, isto é, por um Output — legível para sempre
> por quem tiver `cloudformation:DescribeStacks`. Ela foi gerada pela CLI direto para
> `~/.config/ti-escolar/segredos/s3-{prod,homolog}.env` (0600, fora do repositório), já no
> formato de `fly secrets import`. Guarde no gerenciador de senhas e **apague os arquivos**.
> Chave perdida não se recupera: cria-se outra
> (`aws iam create-access-key --profile tiescolar --user-name ti-escolar-<amb>-s3`) e
> desativa-se a anterior.

**O que está travado:** o adaptador está na `develop` e a **produção roda a `main`** — e
mergear na `main` **não publica**, porque `FLY_API_TOKEN` e `PRODUCAO_BASE_URL` ainda não
estão cadastrados (§1): a esteira roda o CI, avisa e pula o deploy, verde. Até o adaptador
subir, `storage_efetivo` devolve `postgres` e os bytes seguem no `bytea` — inclusive a foto
do aluno, que nasce lá para ser migrada depois.

**O que só você faz, e a ordem importa:**

1. **Guardar as duas chaves** no gerenciador de senhas e apagar os `.env`.
2. **PR `develop` → `main`**, e mergear.
3. **Publicar**: cadastrar `FLY_API_TOKEN` e `PRODUCAO_BASE_URL` e rodar a esteira, ou
   `cd backend && fly deploy` na mão. Confira o `versao` do `/health`: verde não prova
   deploy, ele responde `ok` na versão velha também. Aqui o `/health` ainda diz
   `"storage": "postgres"`, e está certo — as envs não foram coladas.
4. **Só então as envs.** Produção:
   `cd backend && fly secrets import < ~/.config/ti-escolar/segredos/s3-prod.env` (reinicia
   a máquina sozinho). Homolog: *Render → Environment → Save* com as cinco linhas de
   `s3-homolog.env` (o *deploy hook* também não está cadastrado, então o deploy de lá é
   *Manual Deploy*).

> **O que a virada deixa para trás:** documento e foto guardados **antes** dela ficam no
> `bytea`, e a leitura vai procurá-los no bucket — ou seja, **404**. É decisão de
> 20/set/2026, não esquecimento: o que existe hoje é dado de teste e de demonstração, e uma
> migração custaria mais do que vale. Se a virada pegar acervo real, a decisão cai e a
> migração volta à lista.

> **Por que as envs vêm depois do deploy:** o `Settings` usa `extra="ignore"`
> (`backend/app/config.py`), então env colada num código que ainda não a lê é
> **silenciosamente descartada** — nada quebra e nada avisa. Colando depois, o `/health`
> responde na primeira olhada. Colar antes não quebra nada, mas faz a troca para o S3
> acontecer sozinha no deploy seguinte, sem ninguém olhando.

**As cinco envs**, por ambiente:

```
ARQUIVO_STORAGE=s3
S3_BUCKET_DOCUMENTOS=<o bucket daquele ambiente>
AWS_REGION=sa-east-1
AWS_ACCESS_KEY_ID=<a chave daquele ambiente>
AWS_SECRET_ACCESS_KEY=<o segredo daquele ambiente>
```

`S3_KMS_KEY_ID` e `S3_ENDPOINT_URL` ficam **vazios**. O endpoint é só para o MinIO local e do
CI; preenchido em produção, o boto3 fala com o lugar errado — e o sintoma é um upload que
falha sem explicar por quê.

### Conferir os buckets no console, quando desconfiar

O que o template **não** faz é checar a configuração dos buckets, que é anterior a ele. A
navegação vai como *Serviço → aba → botão*, e os nomes mudam de tempo em tempo.

**Os dois buckets** — *S3 → Buckets de uso geral (General purpose buckets)*. A
coluna **Região da AWS** tem de dizer `América do Sul (São Paulo) sa-east-1`: guardar
atestado de criança fora do Brasil é transferência internacional (LGPD arts. 33-36). Clique
no nome do bucket e confira, em duas abas:

- *aba **Propriedades*** → **Versionamento do bucket** = `Desativado`. Ligado e sem regra de
  expiração de versões não-correntes, o `DeleteObject` do expurgo **não apaga nada**: cria um
  *delete marker*, os bytes do atestado seguem no bucket e o expurgo relata sucesso. É a
  falha mais cara desta lista, porque ela mente na direção tranquilizadora.
- *aba **Propriedades*** → **Criptografia padrão** = `SSE-KMS` com a chave `aws/s3`.
- *aba **Gerenciamento** (Management)* → **Regras de ciclo de vida**: têm de aparecer
  `rede-de-seguranca-doc-395d` e `rede-de-seguranca-impressao-180d`. São **rede**, não
  mecanismo — o prazo de verdade é o `DOCUMENTO_RETENCAO_DIAS` da aplicação.

> **As três armadilhas da política**, que o template resolve e o console não avisa:
> `GetObject` cobre o `HeadObject` que o adaptador faz antes de apagar; `s3:ListBucket` vai
> no ARN **sem** `/*` (é permissão do bucket — no ARN com `/*`, só o varredor de órfãos
> falha, em silêncio); e sem o bloco `kms:GenerateDataKey`/`kms:Decrypt` o `PutObject` falha
> com `AccessDenied` **sem mencionar KMS**, porque a chave `aws/s3` é gerenciada pela AWS e
> não tem política editável. Nada de `s3:*` e nada de URL pré-assinada: os bytes saem pelo
> endpoint autenticado da API, que audita `documento.baixar` (§6k).

**Como conferir que caiu:** subir um documento pelo WhatsApp e ver o objeto aparecer no
bucket — *S3 → o bucket → aba **Objetos***, entrando pelas pastas `doc/` → `{tenant}` →
`{ano}` → `{mês}` — e um arquivo de professor sob `impressao/{tenant}/…`, que é o que separa
as duas regras de lifecycle. (As "pastas" do console são o prefixo da chave; não existe
diretório no S3.) O download pelo painel continua funcionando (ele
nunca é URL pública). O `/health` passa a trazer `"storage": "s3"`; se vier
`"storage": "postgres"` com `"storage_configurado": "s3"`, a env pediu o bucket e o processo
caiu no banco — a mesma armadilha do canal.

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
