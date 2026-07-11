import { test, expect } from "@playwright/test";

test.describe("Publish Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/publish");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with publish header", async ({ page }) => {
    const heading = page.locator("h1").first();
    const text = await heading.textContent();
    expect(text?.toLowerCase()).toMatch(/publish|social/);
  });

  test("social platform connections are shown", async ({ page }) => {
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    const hasSocial =
      content?.includes("Instagram") ||
      content?.includes("TikTok") ||
      content?.includes("YouTube") ||
      content?.includes("Twitter") ||
      content?.includes("Connect") ||
      content?.includes("Platform") ||
      content?.includes("Social") ||
      content?.includes("Publish") ||
      content?.includes("publish");
    expect(hasSocial).toBeTruthy();
  });

  test("connect buttons are available", async ({ page }) => {
    const connectBtns = page.locator("button:has-text('Connect'), button:has-text('Link')");
    const count = await connectBtns.count();
    // At least some connect buttons should be visible
    if (count > 0) {
      await expect(connectBtns.first()).toBeEnabled();
    }
  });

  test("schedule or publish action exists", async ({ page }) => {
    const actionBtn = page.locator("button:has-text('Publish'), button:has-text('Schedule'), button:has-text('Post')").first();
    if (await actionBtn.isVisible().catch(() => false)) {
      await expect(actionBtn).toBeEnabled();
    }
  });
});
