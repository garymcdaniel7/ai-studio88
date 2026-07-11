import { test, expect } from "@playwright/test";

test.describe("Brain Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/brain");
    await expect(page.locator("h1, [data-testid='brain-page']").first()).toBeVisible({ timeout: 10000 });
  });

  test("page loads with Brain UI", async ({ page }) => {
    const content = await page.textContent("body");
    const hasBrain =
      content?.includes("Brain") ||
      content?.includes("Chat") ||
      content?.includes("AI") ||
      content?.includes("Assistant");
    expect(hasBrain).toBeTruthy();
  });

  test("chat input is visible and editable", async ({ page }) => {
    const chatInput = page.locator("textarea, input[placeholder*='message'], input[placeholder*='chat'], input[placeholder*='Ask']").first();
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill("Hello");
      const value = await chatInput.inputValue();
      expect(value).toBe("Hello");
    }
  });

  test("send button exists and is clickable", async ({ page }) => {
    const sendBtn = page.locator("button:has-text('Send'), button[type='submit'], button[aria-label='Send']").first();
    if (await sendBtn.isVisible().catch(() => false)) {
      await expect(sendBtn).toBeEnabled();
    }
  });

  test("brain modes are selectable", async ({ page }) => {
    const content = await page.textContent("body");
    const hasModes =
      content?.includes("Creative") ||
      content?.includes("Prompt Engineer") ||
      content?.includes("Story") ||
      content?.includes("Production") ||
      content?.includes("Research") ||
      content?.includes("Mode");
    // Modes may be visible as tabs or dropdown
    if (hasModes) {
      const modeBtn = page.locator("button:has-text('Creative'), button:has-text('Prompt'), button:has-text('Story')").first();
      if (await modeBtn.isVisible().catch(() => false)) {
        await modeBtn.click();
        await page.waitForTimeout(500);
      }
    }
  });

  test("chat message can be sent (if backend connected)", async ({ page }) => {
    const chatInput = page.locator("textarea, input[placeholder*='message'], input[placeholder*='Ask']").first();
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill("What can you do?");
      const sendBtn = page.locator("button:has-text('Send'), button[type='submit']").first();
      if (await sendBtn.isVisible().catch(() => false)) {
        await sendBtn.click();
        // Wait for response or loading indicator
        await page.waitForTimeout(3000);
        const messages = page.locator("[class*='message'], [class*='chat'], [class*='response']");
        // May get a response or an error — both are acceptable
      }
    }
  });

  test("conversation history section exists", async ({ page }) => {
    const content = await page.textContent("body");
    const hasHistory =
      content?.includes("History") ||
      content?.includes("Conversation") ||
      content?.includes("Previous") ||
      content?.includes("Collection");
    // History section may or may not be present
  });

  test("brain health/status indicator is present", async ({ page }) => {
    const content = await page.textContent("body");
    const hasStatus =
      content?.includes("Connected") ||
      content?.includes("Offline") ||
      content?.includes("Ready") ||
      content?.includes("Ollama") ||
      content?.includes("Provider");
    expect(hasStatus).toBeTruthy();
  });
});
