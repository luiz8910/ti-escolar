# Landing page institucional (`site/`)

> Parte do guia do TI-Escolar — índice em [`CLAUDE.md`](../../CLAUDE.md).
> A numeração das seções (§6a, §9c, …) é a original: as referências cruzadas
> espalhadas pelos outros documentos continuam valendo.

### 9d. Landing page institucional (`site/`) — Cloudflare Pages

Site público em **`site/`** (`tiescolar.com.br`), **separado do painel**: projeto Next.js
próprio, sem imports de `web/`, sem chamadas de API e sem estado. Reusa os **mesmos design
tokens** do painel (marca Cobalt, Plus Jakarta Sans) copiados em `site/app/globals.css` +
`site/tailwind.config.ts`, de modo que site e produto compartilham a identidade sem acoplar
os projetos.

- **Por que existe:** além de apresentar o produto, a **verificação da empresa na Meta**
  exige um site público no ar com **razão social e CNPJ visíveis**, política de privacidade
  e termos de uso. A falta disso reprovou o envio de jul/2026 (o domínio não tinha registro
  A/CNAME — só o MX do Email Routing).
- **Build:** `output: "export"` (HTML/CSS/JS estáticos em `site/out/`) + `trailingSlash`.
  Sem servidor Node, sem adapter, sem Workers — a Cloudflare Pages serve os arquivos direto.
  Fontes via `next/font` (auto-hospedadas no build): a página **não faz nenhuma requisição a
  domínio externo** em runtime.
- **Dados institucionais em um único arquivo:** `site/lib/empresa.ts` (razão social, CNPJ,
  endereço, telefone, e-mail). Campos ainda não preenchidos ficam marcados como `PENDENTE` e
  o bloco correspondente **não é renderizado** — nada de placeholder no ar. Os valores
  precisam bater **caractere por caractere** com o Cartão CNPJ e com *Informações da empresa*
  no Business Manager.
- **Páginas:** `/` (hero, dores, funcionalidades, como funciona, segurança/LGPD, contato),
  `/privacidade/`, `/termos/`, 404, `robots.txt`, `sitemap.xml`. O rodapé carrega a
  identificação legal do controlador em todas elas.
- **Deploy:** `.github/workflows/site.yml` — push na `main` que toque em `site/**` faz
  build + publica em produção na Cloudflare Pages; PR gera **preview** com URL própria.
  Exige o projeto Pages criado (`ti-escolar-site`) e os secrets `CLOUDFLARE_API_TOKEN` /
  `CLOUDFLARE_ACCOUNT_ID`; sem eles o workflow só valida o build. Ver `site/README.md`.
