import type { MetadataRoute } from "next";
import { EMPRESA } from "@/lib/empresa";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const agora = new Date();
  return [
    { url: `${EMPRESA.site}/`, lastModified: agora, priority: 1 },
    { url: `${EMPRESA.site}/privacidade/`, lastModified: agora, priority: 0.5 },
    { url: `${EMPRESA.site}/termos/`, lastModified: agora, priority: 0.5 },
  ];
}
