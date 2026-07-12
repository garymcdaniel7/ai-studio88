import { test, expect } from "@playwright/test";

const ROUTES = [
  { path: "/", title: "Home", selector: "h1" },
  { path: "/brain", title: "Brain", selector: "h1, [data-testid='brain-page']" },
  { path: "/create", title: "Create", selector: "h1" },
  { path: "/talent", title: "Talent", selector: "h1" },
  { path: "/assets", title: "Assets", selector: "h1" },
  { path: "/models", title: "Models", selector: "h1" },
  { path: "/training", title: "Training", selector: "h1" },
  { path: "/editor", title: "Editor", selector: "body" },
  { path: "/workflows", title: "Workflows", selector: "h1" },
  { path: "/production", title: "Production", selector: "h1" },
  { path: "/publish", title: "Publish", selector: "h1" },
  { path: "/analytics", title: "Analytics", selector: "h1" },
  { path: "/admin", title: "Admin", selector: "h1, [role='tablist'], button" },
  { path: "/admin/fleet", title: "Fleet", selector: "h1" },
  { path: "/admin/keys", title: "Keys", selector: "h1" },
  { path: "/settings", title: "Settings", selector: "h1" },
];

test.describe("Navigation — All Routes Load", () => {
  for (const route of ROUTES) {
    test(`${route.path} loads successfully`, async ({ page }) => {
      const response = await page.goto(route.path);
      expect(response?.status()).toBeLessThan(500);
      await expect(page.locator(route.selector).first()).toBeVisible({ timeout: 10000 });
    });
  }
});

test.describe("Sidebar Navigation", () => {
  test("all sidebar links navigate correctly", async ({ page }) => {
    await page.goto("/");
    const sidebarLinks = page.locator("aside a[href]");
    const count = await sidebarLinks.count();
    expect(count).toBeGreaterThan(5);

    for (let i = 0; i < count; i++) {
      const href = await sidebarLinks.nth(i).getAttribute("href");
      if (href && href.startsWith("/")) {
        await page.goto(href);
        await page.waitForLoadState("domcontentloaded");
        expect(page.url()).toContain(href);
      }
    }
  });

  test("Brain chat popup opens without navigation", async ({ page }) => {
    await page.goto("/");
    const chatBtn = page.locator("button", { hasText: "Chat with Brain" });
    if (await chatBtn.isVisible()) {
      await chatBtn.click();
      await expect(page.locator("[class*='fixed'][class*='bottom']").first()).toBeVisible();
      expect(page.url()).not.toContain("/brain");
    }
  });
});

test.describe("Page Refresh Stability", () => {
  for (const route of ROUTES.slice(0, 5)) {
    test(`${route.path} survives refresh`, async ({ page }) => {
      await page.goto(route.path);
      await page.reload();
      await expect(page.locator(route.selector).first()).toBeVisible({ timeout: 10000 });
    });
  }
});
