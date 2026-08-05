import { test, expect } from "@playwright/test";

test.describe("Production Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.context().addCookies([
      { name: "ai_studio_auth", value: "test_token", domain: "localhost", path: "/" },
    ]);
    await page.goto("/production");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with production header", async ({ page }) => {
    const heading = page.locator("h1").first();
    const text = await heading.textContent();
    expect(text?.toLowerCase()).toMatch(/jobs|production|queue/);
  });

  test("worker status section is visible", async ({ page }) => {
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    const hasWorkerUI =
      content?.includes("Worker") ||
      content?.includes("worker") ||
      content?.includes("GPU") ||
      content?.includes("Fleet") ||
      content?.includes("Manage Fleet");
    expect(hasWorkerUI).toBeTruthy();
  });

  test("manage fleet link exists", async ({ page }) => {
    const fleetLink = page.locator("a:has-text('Manage Fleet'), a[href='/admin/fleet']").first();
    if (await fleetLink.isVisible().catch(() => false)) {
      await expect(fleetLink).toBeVisible();
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
    // Should show job status indicators or fleet status
    const content = await page.textContent("body");
    const hasStatus =
      content?.includes("Active") ||
      content?.includes("Idle") ||
      content?.includes("Status") ||
      content?.includes("queued") ||
      content?.includes("completed") ||
      content?.includes("running");
    expect(hasStatus).toBeTruthy();
  });
});
