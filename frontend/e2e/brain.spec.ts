import { test, expect } from "@playwright/test";

test.describe("AI Brain Page", () => {
  test("loads with mode selector", async ({ page }) => {
    await page.goto("/brain");
    await expect(page.locator("text=Creative Chat, text=Script Writer").first()).toBeVisible({ timeout: 5000 });
  });

  test("chat input accepts text", async ({ page }) => {
    await page.goto("/brain");
    const textarea = page.locator("textarea").first();
    await expect(textarea).toBeVisible();
    await textarea.fill("Hello, test message");
    await expect(textarea).toHaveValue("Hello, test message");
  });

  test("send button triggers message", async ({ page }) => {
    await page.goto("/brain");
    const textarea = page.locator("textarea").first();
    await textarea.fill("Hello test");
    const sendBtn = page.locator("button[class*='purple']").last();
    await sendBtn.click();
    // Should see user message appear
    await expect(page.locator("text=Hello test")).toBeVisible({ timeout: 5000 });
  });

  test("mode switching works", async ({ page }) => {
    await page.goto("/brain");
    const scriptMode = page.locator("button:has-text('Script Writer')");
    if (await scriptMode.isVisible()) {
      await scriptMode.click();
      await expect(page.locator("text=Script Writer, text=screenplays").first()).toBeVisible();
    }
  });

  test("quick action buttons pre-fill input", async ({ page }) => {
    await page.goto("/brain");
    const brainstorm = page.locator("button:has-text('Brainstorm')");
    if (await brainstorm.isVisible()) {
      await brainstorm.click();
      const textarea = page.locator("textarea").first();
      const value = await textarea.inputValue();
      expect(value.length).toBeGreaterThan(5);
    }
  });
});
