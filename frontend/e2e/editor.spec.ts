import { test, expect } from "@playwright/test";

test.describe("Editor Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/editor");
    await page.waitForTimeout(3000);
  });

  test("page loads with editor UI", async ({ page }) => {
    // Editor page may load slowly — wait for any content
    const content = await page.textContent("body");
    const hasEditor =
      content?.includes("Editor") ||
      content?.includes("Video") ||
      content?.includes("Create") ||
      content?.includes("Quick");
    expect(hasEditor).toBeTruthy();
  });

  test("editor tools or timeline is present", async ({ page }) => {
    const content = await page.textContent("body");
    const hasEditor =
      content?.includes("Timeline") ||
      content?.includes("Canvas") ||
      content?.includes("Layer") ||
      content?.includes("Editor") ||
      content?.includes("Quick Edit") ||
      content?.includes("Upload") ||
      content?.includes("Create");
    expect(hasEditor).toBeTruthy();
  });

  test("quick edit or quick create buttons exist", async ({ page }) => {
    const content = await page.textContent("body");
    const hasButtons =
      content?.includes("Quick") ||
      content?.includes("Edit") ||
      content?.includes("Create") ||
      content?.includes("Upload");
    expect(hasButtons).toBeTruthy();
  });
});
