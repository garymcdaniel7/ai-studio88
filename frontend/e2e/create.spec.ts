import { test, expect } from "@playwright/test";

test.describe("Create Page", () => {
  test("loads with image tab active", async ({ page }) => {
    await page.goto("/create");
    await expect(page.locator("h1, h3", { hasText: "Quick Generate" }).first()).toBeVisible();
  });

  test("model selector shows available models", async ({ page }) => {
    await page.goto("/create");
    const select = page.locator("select").first();
    await expect(select).toBeVisible();
    const options = await select.locator("option").count();
    expect(options).toBeGreaterThan(0);
  });

  test("prompt input accepts text", async ({ page }) => {
    await page.goto("/create");
    const input = page.locator("input[placeholder*='luxury'], input[placeholder*='prompt']").first();
    await expect(input).toBeVisible();
    await input.fill("A test prompt for UAT");
    await expect(input).toHaveValue("A test prompt for UAT");
  });

  test("generate button exists and is clickable with prompt", async ({ page }) => {
    await page.goto("/create");
    const input = page.locator("input[placeholder*='luxury'], input[placeholder*='prompt']").first();
    await input.fill("test prompt");
    const genBtn = page.locator("button:has-text('Generate')").first();
    await expect(genBtn).toBeEnabled();
  });

  test("video tab switches correctly", async ({ page }) => {
    await page.goto("/create");
    const videoTab = page.locator("button:has-text('Video')").first();
    await videoTab.click();
    await expect(page.locator("text=Video from Text")).toBeVisible();
  });

  test("audio tab switches correctly", async ({ page }) => {
    await page.goto("/create");
    const audioTab = page.locator("button:has-text('Audio')").first();
    await audioTab.click();
    await expect(page.locator("text=Voice Generation")).toBeVisible();
  });

  test("favorites star button saves prompt", async ({ page }) => {
    await page.goto("/create");
    const input = page.locator("input[placeholder*='luxury'], input[placeholder*='prompt']").first();
    await input.fill("My favorite test prompt");
    const star = page.locator("button[title='Save to favorites']");
    if (await star.isVisible()) {
      await star.click();
      // Favorites bar should appear
      await expect(page.locator("text=saved prompt")).toBeVisible({ timeout: 3000 });
    }
  });
});
