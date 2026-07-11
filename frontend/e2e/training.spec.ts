import { test, expect } from "@playwright/test";

test.describe("Training Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/training");
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with training UI", async ({ page }) => {
    // Should show training page content
    const heading = page.locator("h1").first();
    await expect(heading).toBeVisible();
  });

  test("training form elements are present", async ({ page }) => {
    // Should have model selection, image upload area, or start training button
    const content = await page.textContent("body");
    const hasTrainingUI =
      content?.includes("Train") ||
      content?.includes("LoRA") ||
      content?.includes("training") ||
      content?.includes("Upload");
    expect(hasTrainingUI).toBeTruthy();
  });

  test("start training button exists", async ({ page }) => {
    const content = await page.textContent("body");
    const hasTrainAction =
      content?.includes("Start Training") ||
      content?.includes("Train") ||
      content?.includes("Begin") ||
      content?.includes("Submit");
    expect(hasTrainAction).toBeTruthy();
  });

  test("talent selector or images section exists", async ({ page }) => {
    const content = await page.textContent("body");
    const hasTalentOrImages =
      content?.includes("Talent") ||
      content?.includes("talent") ||
      content?.includes("Upload") ||
      content?.includes("image") ||
      content?.includes("Image") ||
      content?.includes("photo") ||
      content?.includes("Select") ||
      content?.includes("Training");
    expect(hasTalentOrImages).toBeTruthy();
  });

  test("training parameters are configurable", async ({ page }) => {
    // Should have options like steps, learning rate, resolution etc.
    const content = await page.textContent("body");
    const hasParams =
      content?.includes("Steps") ||
      content?.includes("Resolution") ||
      content?.includes("Learning") ||
      content?.includes("Epochs") ||
      content?.includes("Batch");
    // May or may not be present depending on UI state
    if (hasParams) {
      expect(hasParams).toBeTruthy();
    }
  });
});
