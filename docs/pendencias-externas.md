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
(`rede-de-seguranca-doc-395d`, `rede-de-seguranca-impressao-180d`). O adaptador
`S3ArquivoStorage` **está na `develop`** desde 16/set/2026, com `listar_chaves` para o
varredor de órfãos, e a fábrica `criar_arquivo_storage`/`storage_efetivo` escolhe o adaptador
pela env. Testado contra MinIO de verdade (compose + CI), não contra mock.

> Antes disso ele passou **um mês numa branch que nunca foi mergeada** (`feat/arquivos-no-s3`,
> 17/ago/2026): estava "escrito e testado" e, ao mesmo tempo, ausente do código que roda. Foi
> o terceiro caso do mesmo padrão, junto do §1 e da documentação do §0 — e é por isso que
> **"está pronto" só conta quando está na `develop`**.

**O que está travado:** **nada disso tem efeito.** Sem credencial, `storage_efetivo` devolve
`postgres` e os bytes seguem no `bytea` — inclusive a foto do aluno, que nasce lá para ser
migrada depois.

**O que só você faz:** criar **um usuário IAM por ambiente** no console da AWS e colar a
chave nos segredos da Fly (produção) e do Render (homolog). O caminho completo, porque o
console da AWS esconde metade disso em abas — a navegação vai como *Serviço → aba → botão*,
e os nomes mudam de tempo em tempo (quando mudarem, o passo ainda diz o que procurar).

> **A ordem importa e é contraintuitiva:** faça a AWS **antes** do deploy, mas cole as envs
> **depois**. O `Settings` do back-end usa `extra="ignore"` (`backend/app/config.py`), então
> uma env colada num código que ainda não a lê é **silenciosamente descartada** — nada
> quebra e nada avisa. Colando depois do deploy, o `/health` responde na primeira olhada.

**1. Conferir os dois buckets** — *S3 → Buckets de uso geral (General purpose buckets)*. A
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

**2. Criar o usuário** — *IAM → Gerenciamento de acesso → Usuários → Criar usuário*. Um por
ambiente (`ti-escolar-prod-s3`, `ti-escolar-homolog-s3`), separados de propósito: chave de
homolog que vaza não pode escrever no bucket de produção. **Não marque** "Fornecer acesso
ao Console de Gerenciamento da AWS" — este usuário nunca é uma pessoa. Em *Definir
permissões*, siga **sem anexar nada** (`Próximo` → `Criar usuário`): a política entra no
passo 3, e o assistente não oferece política em linha.

**3. A política, em linha no usuário** — abra o usuário → *aba **Permissões*** → **Adicionar
permissões ▾** → **Criar política em linha** → *aba **JSON*** → cole, trocando `<BUCKET>`
pelo bucket **daquele** ambiente → `Próximo` → nomeie (`ti-escolar-s3-prod`) → `Criar
política`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ObjetosDesteBucket",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::<BUCKET>/*"
    },
    {
      "Sid": "ListarParaVarrerOrfaos",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::<BUCKET>"
    },
    {
      "Sid": "ChaveDeDadosDoKMS",
      "Effect": "Allow",
      "Action": ["kms:GenerateDataKey", "kms:Decrypt"],
      "Resource": "*",
      "Condition": {
        "StringEquals": { "kms:ViaService": "s3.sa-east-1.amazonaws.com" }
      }
    }
  ]
}
```

Cada bloco existe por um sintoma diferente, e nenhum dos três é óbvio a partir do erro:

> **`GetObject` cobre o `HeadObject`.** O adaptador faz `head` antes de apagar, para o
> booleano da porta não mentir; sem isso o expurgo relataria como apagado o que nunca existiu.
>
> **`s3:ListBucket` vai no ARN *sem* `/*`** — é permissão **do bucket**, não do objeto. Pôr as
> duas no ARN com `/*` deixa upload e download funcionando e faz **só o varredor de órfãos**
> falhar, que é o que ninguém testa na hora: ele não enxerga lixo nenhum e relata zero, sem erro.
>
> **O `kms:*` com `Resource: "*"` não é largo:** a condição `ViaService` limita o uso a
> chamadas que passam pelo S3 daquela região. Sem este bloco, policy só com
> `PutObject`/`GetObject` **não basta** — o `PutObject` falha com `AccessDenied` na hora de
> gerar a chave de dados, e **a mensagem não menciona KMS**. A chave `aws/s3` é gerenciada
> pela AWS (*KMS → Chaves gerenciadas pela AWS → `aws/s3`*, com a região em São Paulo no
> seletor do topo) e **não tem política editável**, e é justamente por isso que a permissão
> tem de vir pelo lado do usuário. Se um dia trocar por CMK própria, é aqui que o ARN da
> chave entra, em vez do `"*"`.
>
> **Nada de `s3:*`** e nada de URL pré-assinada: os bytes saem pelo endpoint autenticado da
> API, que audita `documento.baixar` (§6k).

**4. Gerar a chave** — ainda no usuário, *aba **Credenciais de segurança*** → **Chaves de
acesso** → **Criar chave de acesso** → caso de uso **Aplicação executada fora da AWS** →
`Próximo` → `Criar`. **O segredo aparece uma única vez**: copie os dois valores para o
gerenciador de senhas antes de fechar a tela. Se perder, não há como recuperar — só criar
outra e desativar a anterior.

**5. Só então, as envs** (Fly: `fly secrets set`, que reinicia a máquina; Render:
*Environment → Save*, que redeploya):

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
