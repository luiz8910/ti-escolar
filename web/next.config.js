/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Export estático: o painel vai para a **Cloudflare Pages** (§12a), cujo plano permite
  // uso comercial — o Hobby da Vercel não, e o painel atende escola pagante. O mesmo
  // build serve homolog e produção; muda só `NEXT_PUBLIC_API_URL`.
  //
  // Consequência que morde: **rota dinâmica passa a exigir `generateStaticParams()`**.
  // Não há como listar ids de escola em tempo de build, então o detalhe da escola lê
  // `?tenant=` — ver `app/admin/escolas/detalhe/page.tsx`.
  output: "export",
};

module.exports = nextConfig;
