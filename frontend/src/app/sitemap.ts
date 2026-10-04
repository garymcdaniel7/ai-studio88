import type { MetadataRoute } from "next";

const PUBLIC_ROUTES = ["/", "/showcase", "/pricing", "/login", "/api"] as const;

function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL?.trim() || "http://localhost:3000").replace(/\/$/, "");
}

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = siteUrl();
  return PUBLIC_ROUTES.map((route) => ({
    url: `${baseUrl}${route}`,
    changeFrequency: route === "/" ? "weekly" : "monthly",
    priority: route === "/" ? 1 : 0.7,
  }));
}
