import type { MetadataRoute } from "next";

function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL?.trim() || "http://localhost:3000").replace(/\/$/, "");
}

export default function robots(): MetadataRoute.Robots {
  const publicSite = siteUrl();
  return {
    rules: {
      userAgent: "*",
      allow: ["/", "/showcase", "/pricing", "/login", "/auth", "/api"],
      disallow: [
        "/admin",
        "/analytics",
        "/assets",
        "/brain",
        "/create",
        "/make",
        "/models",
        "/projects",
        "/publish",
        "/settings",
        "/story",
        "/talent",
        "/training",
        "/workflows",
        "/api/",
      ],
    },
    sitemap: `${publicSite}/sitemap.xml`,
  };
}
