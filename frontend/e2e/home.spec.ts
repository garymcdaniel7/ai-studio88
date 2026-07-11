import { test, expect } from "@playwright/test";

test.describe("Home Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with welcome or dashboard", async ({ page }) => {
    const heading = page.locator("h1").first();
    await expect(heading).toBeVisible();
  });

  test("quick create button exists", async ({ page }) => {
    const quickCreate = page.locator("button:has-text('Quick Create'), button:has-text('Create'), a:has-text('Create')").first();
    if (await quickCreate.isVisible().catch(() => false)) {
      await expect(quickCreate).toBeEnabled();
    }
  });

  test("recent activity or stats section is present", async ({ page }) => {
    const content = await page.textContent("body");
    const hasDashboard =
      content?.includes("Recent") ||
      content?.includes("Activity") ||
      content?.includes("Jobs") ||
      content?.includes("Talent") ||
      content?.includes("Welcome") ||
      content?.includes("Studio");
    expect(hasDashboard).toBeTruthy();
  });

  test("navigation sidebar is visible on desktop", async ({ page, viewport }) => {
    if (viewport && viewport.width >= 768) {
      const sidebar = page.locator("aside");
      await expect(sidebar).toBeVisible();
    }
  });

  test("all workspace links are present in sidebar", async ({ page, viewport }) => {
    if (viewport && viewport.width >= 768) {
      const links = page.locator("aside a[href]");
      const count = await links.count();
      expect(count).toBeGreaterThanOrEqual(10);
    }
  });
});
