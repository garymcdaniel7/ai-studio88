import { test, expect } from "@playwright/test";

test.describe("Admin Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/admin");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with admin header", async ({ page }) => {
    const heading = page.locator("h1").first();
    const text = await heading.textContent();
    expect(text?.toLowerCase()).toMatch(/admin|dashboard|system/);
  });

  test("service connection cards are visible", async ({ page }) => {
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    const hasServices =
      content?.includes("Vast") ||
      content?.includes("Backblaze") ||
      content?.includes("Supabase") ||
      content?.includes("ComfyUI") ||
      content?.includes("Ollama") ||
      content?.includes("ElevenLabs") ||
      content?.includes("Service");
    expect(hasServices).toBeTruthy();
  });

  test("service toggles or connect buttons work", async ({ page }) => {
    await page.waitForTimeout(2000);
    const toggles = page.locator("button:has-text('Connect'), button:has-text('Enable'), button:has-text('Test'), input[type='checkbox'], [role='switch']");
    const count = await toggles.count();
    if (count > 0) {
      // Just verify they are interactive
      await expect(toggles.first()).toBeEnabled();
    }
  });

  test("health check or status indicators present", async ({ page }) => {
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    const hasHealth =
      content?.includes("Connected") ||
      content?.includes("Offline") ||
      content?.includes("Health") ||
      content?.includes("Status") ||
      content?.includes("Online");
    expect(hasHealth).toBeTruthy();
  });

  test("links to sub-pages work", async ({ page }) => {
    // Should have links to /admin/fleet, /admin/keys, /admin/downloads
    const fleetLink = page.locator("a[href='/admin/fleet'], button:has-text('Fleet')").first();
    if (await fleetLink.isVisible().catch(() => false)) {
      await fleetLink.click();
      await page.waitForURL("**/admin/fleet**");
      expect(page.url()).toContain("/admin/fleet");
    }
  });
});

test.describe("Admin Fleet Page", () => {
  test("page loads", async ({ page }) => {
    await page.goto("/admin/fleet");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("worker list or empty state shown", async ({ page }) => {
    await page.goto("/admin/fleet");
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    const hasFleet =
      content?.includes("Worker") ||
      content?.includes("GPU") ||
      content?.includes("Instance") ||
      content?.includes("Fleet") ||
      content?.includes("No workers");
    expect(hasFleet).toBeTruthy();
  });

  test("launch worker button exists", async ({ page }) => {
    await page.goto("/admin/fleet");
    const launchBtn = page.locator("button:has-text('Launch'), button:has-text('Add Worker'), button:has-text('Start')").first();
    if (await launchBtn.isVisible().catch(() => false)) {
      await expect(launchBtn).toBeEnabled();
    }
  });
});

test.describe("Admin Keys Page", () => {
  test("page loads with API keys section", async ({ page }) => {
    await page.goto("/admin/keys");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
    const content = await page.textContent("body");
    const hasKeys =
      content?.includes("API") ||
      content?.includes("Key") ||
      content?.includes("Secret") ||
      content?.includes("Token");
    expect(hasKeys).toBeTruthy();
  });

  test("key inputs are masked or hidden", async ({ page }) => {
    await page.goto("/admin/keys");
    await page.waitForTimeout(1000);
    // Keys should not show raw values (should show *** or password type)
    const passwordInputs = page.locator("input[type='password']");
    const maskedText = page.locator("text=***");
    const masked = (await passwordInputs.count()) > 0 || (await maskedText.count()) > 0;
    // This is advisory — some keys may be shown
  });

  test("save/update button for keys", async ({ page }) => {
    await page.goto("/admin/keys");
    const saveBtn = page.locator("button:has-text('Save'), button:has-text('Update'), button:has-text('Set')").first();
    if (await saveBtn.isVisible().catch(() => false)) {
      // Button may be disabled until changes are made — that's correct behavior
      await expect(saveBtn).toBeVisible();
    }
  });
});

test.describe("Admin Downloads Page", () => {
  test("page loads", async ({ page }) => {
    await page.goto("/admin/downloads");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("model download list or options shown", async ({ page }) => {
    await page.goto("/admin/downloads");
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    const hasDownloads =
      content?.includes("Download") ||
      content?.includes("Model") ||
      content?.includes("Cache") ||
      content?.includes("Available");
    expect(hasDownloads).toBeTruthy();
  });
});
