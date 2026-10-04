/**
 * Shared integration coverage for the growth lane's public pages and the
 * creation lane's proxy. Run the public-page subset against the growth
 * worktree and the auth-regression subset against the creation worktree.
 */
import { expect, test } from "@playwright/test";

const PUBLIC_METADATA_ROUTES = ["/robots.txt", "/sitemap.xml"] as const;

test.describe("public routing contract", () => {
  test("showcase is a public responsive gallery", async ({ page }) => {
    const response = await page.goto("/showcase");
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: /studio for characters/i })).toBeVisible();
    await expect(page.locator("img").first()).toBeVisible();
    await expect(page.getByRole("link", { name: /get started/i })).toBeVisible();
  });

  for (const route of PUBLIC_METADATA_ROUTES) {
    test(`${route} is public metadata`, async ({ request }) => {
      const response = await request.get(route, { maxRedirects: 0 });
      expect(response.status()).toBe(200);
      expect(response.headers()["location"]).toBeUndefined();
      const body = await response.text();
      if (route === "/robots.txt") {
        expect(body).toContain("Sitemap:");
        expect(body).toContain("Disallow: /admin");
        expect(body).toContain("Disallow: /projects");
      } else {
        expect(body).toContain("<urlset");
        expect(body).toContain("/showcase");
        expect(body).not.toContain("/admin");
        expect(body).not.toContain("/projects/");
      }
    });
  }

  test("unknown frontend paths render 404 without a login redirect", async ({ request }) => {
    const response = await request.get("/not-a-real-frontend-route", { maxRedirects: 0 });
    expect(response.status()).toBe(404);
    expect(response.headers()["location"]).toBeUndefined();
  });

  test("/api explains the Railway backend without proxying credentials", async ({ request }) => {
    const response = await request.get("/api", { maxRedirects: 0 });
    expect(response.status()).toBe(200);
    const body = await response.text();
    expect(body).toContain("Railway backend");
    expect(body).toContain("API documentation");
    expect(body).not.toContain("SUPABASE_SERVICE_ROLE_KEY");
  });

  test("known protected routes still redirect unauthenticated requests", async ({ request }) => {
    for (const route of ["/brain", "/projects/example-id"]) {
      const response = await request.get(route, { maxRedirects: 0 });
      expect(response.status(), route).toBe(307);
      expect(response.headers()["location"], route).toContain("/login");
    }
  });

  test("frontend API paths retain their non-login contract", async ({ request }) => {
    const response = await request.get("/api/v1/health", { maxRedirects: 0 });
    expect(response.status()).not.toBe(307);
    expect(response.headers()["location"]).toBeUndefined();
  });
});
