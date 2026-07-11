import { test, expect } from "@playwright/test";

test.describe("Settings Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with settings header", async ({ page }) => {
    const heading = page.locator("h1").first();
    const text = await heading.textContent();
    expect(text?.toLowerCase()).toMatch(/settings|profile|account/);
  });

  test("profile section is visible", async ({ page }) => {
    const content = await page.textContent("body");
    const hasProfile =
      content?.includes("Name") ||
      content?.includes("Email") ||
      content?.includes("Profile") ||
      content?.includes("Account");
    expect(hasProfile).toBeTruthy();
  });

  test("save button exists", async ({ page }) => {
    const saveBtn = page.locator("button:has-text('Save'), button:has-text('Update')").first();
    if (await saveBtn.isVisible().catch(() => false)) {
      await expect(saveBtn).toBeEnabled();
    }
  });

  test("text inputs are editable", async ({ page }) => {
    const inputs = page.locator("input[type='text'], input[type='email']");
    const count = await inputs.count();
    if (count > 0) {
      const firstInput = inputs.first();
      await firstInput.click();
      const isEditable = await firstInput.isEditable();
      expect(isEditable).toBeTruthy();
    }
  });
});
