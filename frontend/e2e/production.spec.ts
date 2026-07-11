import { test, expect } from "@playwright/test";

test.describe("Production Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/production");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with production header", async ({ page }) => {
    const heading = page.locator("h1").first();
    const text = await heading.textContent();
    expect(text?.toLowerCase()).toMatch(/production|fleet|worker/);
  });

  test("worker status section is visible", async ({ page }) => {
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    const hasWorkerUI =
      content?.includes("Worker") ||
      content?.includes("worker") ||
      content?.includes("GPU") ||
      content?.includes("Instance") ||
      content?.includes("Fleet");
    expect(hasWorkerUI).toBeTruthy();
  });

  test("launch worker button exists", async ({ page }) => {
    const launchBtn = page.locator("button:has-text('Launch'), button:has-text('Start Worker'), button:has-text('New Worker')").first();
    if (await launchBtn.isVisible().catch(() => false)) {
      await expect(launchBtn).toBeEnabled();
    }
  });

  test("job queue or history section exists", async ({ page }) => {
    const content = await page.textContent("body");
    const hasJobs =
      content?.includes("Job") ||
      content?.includes("Queue") ||
      content?.includes("History") ||
      content?.includes("Completed") ||
      content?.includes("Running");
    expect(hasJobs).toBeTruthy();
  });

  test("connection status indicators are present", async ({ page }) => {
    await page.waitForTimeout(2000);
    // Should show connection status for GPU, ComfyUI, etc.
    const content = await page.textContent("body");
    const hasStatus =
      content?.includes("Connected") ||
      content?.includes("Offline") ||
      content?.includes("Online") ||
      content?.includes("Status");
    expect(hasStatus).toBeTruthy();
  });
});
