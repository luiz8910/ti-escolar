/** @type {import('next').NextConfig} */

/**
 * Landing page institucional — 100% estática.
 *
 * `output: "export"` gera HTML/CSS/JS puros em `out/`, que é exatamente o que a
 * Cloudflare Pages publica: sem servidor Node, sem adapter, sem Workers. Como a
 * LP não chama API nem renderiza nada por requisição, essa é a forma mais barata
 * e resiliente de hospedar.
 *
 * `trailingSlash` faz cada rota virar `.../index.html` (ex.: `/privacidade/index.html`),
 * o que evita 404 ao servir os arquivos direto de um CDN estático.
 */
const nextConfig = {
  reactStrictMode: true,
  output: "export",
  trailingSlash: true,
  // O otimizador de imagens do Next exige servidor; no export estático ele não roda.
  // A LP usa apenas SVG inline, então isso é só uma salvaguarda.
  images: { unoptimized: true },
};

module.exports = nextConfig;
