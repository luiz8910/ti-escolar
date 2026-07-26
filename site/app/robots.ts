import type { MetadataRoute } from "next";
import { EMPRESA } from "@/lib/empresa";

export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${EMPRESA.site}/sitemap.xml`,
  };
}
