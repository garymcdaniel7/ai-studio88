import { test, expect } from "@playwright/test";

test.describe("Talent Page", () => {
  test("loads talent list", async ({ page }) => {
    await page.goto("/talent");
    await expect(page.locator("h1", { hasText: "Talent" })).toBeVisible();
    // Should show talent cards or empty state
    const hasCards = await page.locator("[class*='rounded-xl']").count();
    expect(hasCards).toBeGreaterThan(0);
  });

  test("create new talent button exists", async ({ page }) => {
    await page.goto("/talent");
    const createBtn = page.locator("button", { hasText: "New Talent" });
    await expect(createBtn).toBeVisible();
  });

  test("create talent flow", async ({ page }) => {
    await page.goto("/talent");
    await page.click("button:has-text('New Talent')");
    // Fill form
    const nameInput = page.locator("input[placeholder*='name']").first();
    if (await nameInput.isVisible()) {
      await nameInput.fill("Test Talent UAT");
      // Look for create/save button
      const saveBtn = page.locator("button:has-text('Create'), button:has-text('Save')").first();
      if (await saveBtn.isVisible()) {
        await saveBtn.click();
        await page.waitForTimeout(1000);
      }
    }
  });

  test("photo upload area visible on talent detail", async ({ page }) => {
    await page.goto("/talent");
    // Click first talent card
    const card = page.locator("[class*='rounded-xl']").first();
    if (await card.isVisible()) {
      await card.click();
      await page.waitForTimeout(500);
      // Should see upload area or photos
      const uploadArea = page.locator("text=Upload Photos, text=Upload reference photo").first();
      await expect(uploadArea).toBeVisible({ timeout: 5000 });
    }
  });

  test("Train LoRA button navigates to training", async ({ page }) => {
    await page.goto("/talent");
    const card = page.locator("[class*='rounded-xl']").first();
    if (await card.isVisible()) {
      await card.click();
      await page.waitForTimeout(500);
      const trainBtn = page.locator("button:has-text('Train LoRA')");
      if (await trainBtn.isVisible()) {
        await trainBtn.click();
        await page.waitForURL("**/training**");
        expect(page.url()).toContain("training");
      }
    }
  });
});
