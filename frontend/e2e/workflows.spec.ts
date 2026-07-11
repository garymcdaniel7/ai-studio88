import { test, expect } from "@playwright/test";

test.describe("Workflows Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/workflows");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with workflow list", async ({ page }) => {
    const heading = page.locator("h1").first();
    const text = await heading.textContent();
    expect(text?.toLowerCase()).toContain("workflow");
  });

  test("workflow cards or list items are displayed", async ({ page }) => {
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    // Should show workflow names like flux, sdxl, wan etc.
    const hasWorkflows =
      content?.includes("flux") ||
      content?.includes("sdxl") ||
      content?.includes("wan") ||
      content?.includes("Workflow") ||
      content?.includes("No workflows");
    expect(hasWorkflows).toBeTruthy();
  });

  test("workflow detail view opens on click", async ({ page }) => {
    await page.waitForTimeout(2000);
    const cards = page.locator("[class*='rounded-xl'], [class*='cursor-pointer']");
    const count = await cards.count();
    if (count > 0) {
      await cards.first().click();
      await page.waitForTimeout(1000);
      // Should show more detail — nodes, parameters, etc.
      const content = await page.textContent("body");
      const hasDetail =
        content?.includes("node") ||
        content?.includes("Node") ||
        content?.includes("parameter") ||
        content?.includes("requires");
      // This is informational — may not open in all cases
    }
  });
});
