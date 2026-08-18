/** @type {import('next').NextConfig} */

/**
 * Painel admin — publicado como **export estático**.
 *
 * Dá para fazer isso porque o painel é uma SPA: 29 das 30 páginas são `"use client"`, não há
 * server action, `next/headers` nem `app/api`. Tudo fala com o back-end por REST, com o
 * token no `localStorage`.
 *
 * **Por que sair do runtime Node.** O plano Hobby da Vercel proíbe uso comercial, e o painel
 * atende escola pagante. Como export estático ele roda na Cloudflare Pages de graça e com
 * uso comercial permitido — e continua publicável na Vercel sem fork de código, que é o que
 * mantém o homolog onde está.
 *
 * `trailingSlash` faz cada rota virar `.../index.html`, evitando 404 ao servir de um CDN.
 */
const nextConfig = {
  reactStrictMode: true,
  output: "export",
  trailingSlash: true,
  // O otimizador de imagens do Next exige servidor; no export estático ele não roda.
  images: { unoptimized: true },
};

module.exports = nextConfig;
