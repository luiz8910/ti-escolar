# `site/` — landing page institucional (tiescolar.com.br)

Site público do TI-Escolar. É um projeto **Next.js separado do painel** (`web/`): não
importa nada dele, não chama a API e não tem estado. O build gera HTML/CSS/JS estáticos,
publicados na **Cloudflare Pages**.

Ele reusa os **mesmos design tokens** do painel (marca Cobalt, neutros frios, Plus Jakarta
Sans), então site e produto têm a mesma identidade sem acoplar os dois projetos.

## Por que ele existe

Além de apresentar o produto, esta LP cumpre um requisito operacional: a **verificação da
empresa na Meta** (necessária para sair do sandbox do WhatsApp Business) exige um site
público, no ar, com **razão social e CNPJ visíveis**, além de política de privacidade e
termos de uso. A ausência disso foi o que reprovou o envio de julho/2026.

## Rodando local

```bash
cd site
npm install
npm run dev          # http://localhost:3001
```

Outros comandos:

| Comando | O que faz |
|---|---|
| `npm run build` | Gera o export estático em `site/out/` |
| `npm run typecheck` | `tsc --noEmit` (o mesmo que o CI roda) |
| `npm start` | Serve `out/` com `npx serve` (confere o build como ele vai ao ar) |

> **Dev e build compartilham o `.next`.** Alternar entre eles sem limpar faz o segundo
> comando reaproveitar chunks do primeiro e falhar com
> `Error: Cannot find module './948.js'`. Por isso `dev` e `build` têm um `pre`-script que
> limpa o `.next` antes de rodar — alternar na sequência funciona sem você pensar nisso.
>
> A única situação que ainda exige atenção: **rodar `npm run build` com o `npm run dev`
> aberto**. O build limpa o diretório debaixo do dev e ele passa a responder 500. É só
> reiniciar o dev (`Ctrl+C` e `npm run dev`).

## Dados legais

Todos os dados institucionais ficam em **um único arquivo**: `site/lib/empresa.ts`,
preenchidos a partir do **Cartão CNPJ emitido em 24/06/2026** (situação *ATIVA*):

| Campo | Valor |
|---|---|
| Razão social | LUIZ FERNANDO SANCHES |
| CNPJ | 60.116.323/0001-77 (matriz) |
| Endereço | Rua Odete Gori Bicudo, 601 — Nova Votorantim, Votorantim/SP, CEP 18113-400 |
| Telefone | (15) 99745-4531 |
| E-mail | contato@tiescolar.com.br |

Esses valores precisam estar **iguais** em *Business Manager → Informações da empresa* —
divergência entre site, documento e cadastro é motivo de reprovação na verificação da Meta.

> **Telefone:** o Cartão CNPJ ainda traz a forma antiga, de 8 dígitos (`9745-4531`),
> anterior ao nono dígito. O número em uso é `(15) 99745-4531`, e é ele que vai no site e
> no Business Manager. Vale atualizar o cadastro na Receita quando der, para os três
> ficarem idênticos.

Campos que voltem a ficar como `PENDENTE` **não são renderizados** — o bloco some em vez de
exibir um placeholder no ar.

## Estrutura

```
site/
├── app/
│   ├── layout.tsx          # fontes (next/font), metadata, Header + Footer
│   ├── page.tsx            # home: hero, dores, funcionalidades, como funciona, segurança, contato
│   ├── privacidade/        # política de privacidade (LGPD)
│   ├── termos/             # termos de uso
│   ├── not-found.tsx       # 404
│   ├── robots.ts           # robots.txt
│   ├── sitemap.ts          # sitemap.xml
│   ├── icon.svg            # favicon
│   └── globals.css         # design tokens (espelham web/app/globals.css)
├── components/             # Header, Footer, Logo, ChatMock, LegalPage, ui, icons
└── lib/
    ├── empresa.ts          # ← dados institucionais (ponto único de verdade)
    └── cn.ts
```

### Decisões técnicas

- **`output: "export"`** — sem servidor Node, sem adapter, sem Workers. A Cloudflare Pages
  serve os arquivos direto. É o modo mais barato e com menos partes móveis.
- **`trailingSlash: true`** — cada rota vira `.../index.html`, evitando 404 em CDN estático.
- **`next/font`** — as fontes são baixadas no build e servidas junto do site. A página não
  faz **nenhuma requisição a domínio externo** em runtime, o que evita depender do Google
  Fonts durante a análise da Meta.
- **Sem `@tailwindcss/typography`** — a tipografia das páginas legais usa seletores de filho
  no próprio `LegalPage`, mantendo as dependências mínimas.

> Nota: os textos de privacidade e termos foram redigidos a partir do funcionamento real da
> plataforma, mas **precisam de revisão jurídica** antes de valerem como instrumento
> contratual — em especial prazos de retenção, limitação de responsabilidade e rescisão.

## Deploy

Automatizado por `.github/workflows/site.yml`: todo push na `main` que toque em `site/**`
faz build e publica em produção. PRs geram um **deploy de preview** com URL própria.

### Configuração única na Cloudflare

1. **Criar o projeto Pages** (o workflow publica nele, mas não o cria):

   ```bash
   npx wrangler pages project create ti-escolar-site --production-branch=main
   ```

   Ou pelo painel: *Workers & Pages → Create → Pages → Direct Upload*, com o nome
   `ti-escolar-site`. Se preferir outro nome, ajuste `CF_PROJECT_NAME` no workflow.

2. **Criar o API token** em *My Profile → API Tokens → Create Token*, com a permissão
   **Account · Cloudflare Pages · Edit**.

3. **Cadastrar os secrets** no GitHub (*Settings → Secrets and variables → Actions*):

   | Secret | Onde encontrar |
   |---|---|
   | `CLOUDFLARE_API_TOKEN` | token criado no passo 2 |
   | `CLOUDFLARE_ACCOUNT_ID` | barra lateral do dashboard da Cloudflare |

   Sem esses secrets o workflow ainda roda o build (serve de status check), mas pula o
   deploy.

4. **Apontar o domínio**: no projeto Pages, *Custom domains → Set up a custom domain* →
   `tiescolar.com.br` (e `www`, se quiser). Como o DNS já está na Cloudflare, os registros
   são criados automaticamente.

   > Hoje `tiescolar.com.br` **não tem registro A/CNAME** — só o MX do Email Routing. É por
   > isso que o site não abre. Este passo é o que resolve.

### Publicar manualmente

```bash
cd site
npm run build
npx wrangler pages deploy out --project-name=ti-escolar-site --branch=main
```
