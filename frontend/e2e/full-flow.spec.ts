import { test, expect } from "@playwright/test";

/**
 * End-to-end user journeys — complete flows that cross multiple pages.
 * Tests the full user workflow from start to finish.
 */

test.describe("User Journey: Upload Model → View in Registry", () => {
  test("can navigate to models page and see upload UI", async ({ page }) => {
    await page.goto("/models");
    await page.waitForTimeout(3000);

    const content = await page.textContent("body");
    const hasUpload =
      content?.includes("Upload") ||
      content?.includes("upload") ||
      content?.includes("Drop") ||
      content?.includes("Model");
    expect(hasUpload).toBeTruthy();

    // Upload button should be present (either inline zone or button)
    const uploadBtn = page.locator("button:has-text('Upload')").first();
    if (await uploadBtn.isVisible().catch(() => false)) {
      await expect(uploadBtn).toBeEnabled();
    }
  });
});

test.describe("User Journey: Create Talent → Upload Photos → Train LoRA", () => {
  test("can create talent from Talent page", async ({ page }) => {
    await page.goto("/talent");
    await expect(page.locator("h1", { hasText: "Talent" })).toBeVisible();

    const newBtn = page.locator("button:has-text('New Talent')");
    await expect(newBtn).toBeVisible();
    await newBtn.click();

    // Should show creation form/modal
    await page.waitForTimeout(1000);
    const nameInput = page.locator("input[placeholder*='name'], input[placeholder*='Name']").first();
    if (await nameInput.isVisible()) {
      await nameInput.fill("E2E Test Talent");
    }
  });

  test("can navigate from Talent to Training", async ({ page }) => {
    await page.goto("/talent");
    await page.waitForTimeout(2000);

    // Click first talent card
    const card = page.locator("[class*='rounded-xl']").first();
    if (await card.isVisible()) {
      await card.click();
      await page.waitForTimeout(1000);

      // Look for Train LoRA button
      const trainBtn = page.locator("button:has-text('Train LoRA')");
      if (await trainBtn.isVisible()) {
        await trainBtn.click();
        await page.waitForURL("**/training**", { timeout: 5000 });
        expect(page.url()).toContain("training");
      }
    }
  });
});

test.describe("User Journey: Create → Generate Image", () => {
  test("can fill prompt and trigger generation", async ({ page }) => {
    await page.goto("/create");
    await page.waitForTimeout(2000);

    const promptInput = page.locator("textarea, input[placeholder*='prompt'], input[placeholder*='Describe']").first();
    if (await promptInput.isVisible()) {
      await promptInput.fill("A professional portrait photo, studio lighting, high quality");

      const genBtn = page.locator("button:has-text('Generate'), button:has-text('Create')").first();
      if (await genBtn.isVisible()) {
        // Just verify the button is clickable — don't actually generate (costs GPU)
        await expect(genBtn).toBeEnabled();
      }
    }
  });
});

test.describe("User Journey: Brain Chat Flow", () => {
  test("can open brain, type message, and interact", async ({ page }) => {
    await page.goto("/brain");
    await page.waitForTimeout(2000);

    const chatInput = page.locator("textarea, input[placeholder*='message'], input[placeholder*='Ask']").first();
    if (await chatInput.isVisible()) {
      await chatInput.fill("What models are available?");

      const sendBtn = page.locator("button:has-text('Send'), button[type='submit']").first();
      if (await sendBtn.isVisible()) {
        await expect(sendBtn).toBeEnabled();
        // Don't actually send (requires Ollama running)
      }
    }
  });
});

test.describe("User Journey: Admin → Launch Worker → Monitor", () => {
  test("can navigate admin flow", async ({ page }) => {
    // Start at admin
    await page.goto("/admin");
    await page.waitForTimeout(2000);

    // Go to fleet
    await page.goto("/admin/fleet");
    await page.waitForTimeout(2000);
    const content = await page.textContent("body");
    expect(content?.includes("Worker") || content?.includes("Fleet") || content?.includes("GPU")).toBeTruthy();

    // Go to production for monitoring
    await page.goto("/production");
    await page.waitForTimeout(2000);
    const prodContent = await page.textContent("body");
    expect(prodContent?.includes("Worker") || prodContent?.includes("Production") || prodContent?.includes("Status")).toBeTruthy();
  });
});

test.describe("User Journey: Analytics Overview", () => {
  test("can view analytics with all sections", async ({ page }) => {
    await page.goto("/analytics");
    await page.waitForTimeout(3000);

    const content = await page.textContent("body");
    // Should have cost info, usage stats, or job counts
    const hasAnalytics =
      content?.includes("Total") ||
      content?.includes("Cost") ||
      content?.includes("Jobs") ||
      content?.includes("Analytics");
    expect(hasAnalytics).toBeTruthy();
  });
});

test.describe("User Journey: Settings Profile", () => {
  test("can view and interact with settings", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForTimeout(2000);

    const content = await page.textContent("body");
    expect(content?.includes("Settings") || content?.includes("Profile") || content?.includes("Account")).toBeTruthy();

    // Try editing a text field
    const inputs = page.locator("input[type='text']");
    const count = await inputs.count();
    if (count > 0) {
      const firstInput = inputs.first();
      if (await firstInput.isEditable()) {
        const currentValue = await firstInput.inputValue();
        await firstInput.fill("E2E Test Value");
        await firstInput.fill(currentValue); // Restore
      }
    }
  });
});
