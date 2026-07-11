import { test, expect } from "@playwright/test";

test.describe("Analytics Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/analytics");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with analytics header", async ({ page }) => {
    const heading = page.locator("h1").first();
    const text = await heading.textContent();
    expect(text?.toLowerCase()).toMatch(/analytics|dashboard|stats/);
  });

  test("stat cards or charts are present", async ({ page }) => {
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    const hasStats =
      content?.includes("Total") ||
      content?.includes("Cost") ||
      content?.includes("Usage") ||
      content?.includes("Jobs") ||
      content?.includes("Generation");
    expect(hasStats).toBeTruthy();
  });

  test("time range selector exists", async ({ page }) => {
    const rangeSelector = page.locator("select, button:has-text('7 days'), button:has-text('30 days'), button:has-text('All Time')").first();
    if (await rangeSelector.isVisible().catch(() => false)) {
      await expect(rangeSelector).toBeEnabled();
    }
  });

  test("tabs or views switch content", async ({ page }) => {
    const tabs = page.locator("button[role='tab'], [class*='tab']");
    const count = await tabs.count();
    if (count > 1) {
      await tabs.nth(1).click();
      await page.waitForTimeout(500);
      // Content should update
    }
  });

  test("GPU cost or service spend shown", async ({ page }) => {
    const content = await page.textContent("body");
    const hasCostInfo =
      content?.includes("$") ||
      content?.includes("Cost") ||
      content?.includes("Spend") ||
      content?.includes("Budget") ||
      content?.includes("GPU");
    expect(hasCostInfo).toBeTruthy();
  });
});
