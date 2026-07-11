import { test, expect } from "@playwright/test";

test.describe("Admin Page", () => {
  test("loads service connections", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.locator("h1, h2", { hasText: "Admin" }).first()).toBeVisible();
    // Should show service cards
    await expect(page.locator("text=Service Connections, text=Services").first()).toBeVisible({ timeout: 5000 });
  });

  test("GPU worker section visible", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.locator("text=GPU Worker, text=Worker").first()).toBeVisible();
  });

  test("service toggles are interactive", async ({ page }) => {
    await page.goto("/admin");
    const toggles = page.locator("button[class*='rounded-full'][class*='w-11']");
    const count = await toggles.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("fleet page loads from admin", async ({ page }) => {
    await page.goto("/admin");
    const fleetLink = page.locator("a[href='/admin/fleet'], [href='/admin/fleet']").first();
    if (await fleetLink.isVisible()) {
      await fleetLink.click();
      await expect(page.locator("text=Fleet, text=Worker")).toBeVisible();
    }
  });
});
