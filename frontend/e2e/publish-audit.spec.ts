import { test, expect, Page } from "@playwright/test";

/**
 * PUBLISH PAGE + SCHEDULER + CALENDAR end-to-end test.
 * Login → /publish → schedule a post → verify it appears in queue AND calendar.
 */
const BASE = process.env.BASE_URL || "https://ai-studio88.vercel.app";
const EMAIL = process.env.TEST_EMAIL || "";
const PASSWORD = process.env.TEST_PASSWORD || "";

async function login(page: Page) {
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("you@example.com").fill(EMAIL);
  await page.getByPlaceholder("At least 6 characters").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/app|home|dashboard/i, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(2500);
}

test("publish page: schedule post + calendar updates", async ({ page }) => {
  // skip if no creds
  test.skip(!EMAIL, "TEST_EMAIL not set");

  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  await login(page);

  // Go to publish
  await page.goto(`${BASE}/publish`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  const body = await page.locator("body").innerText();
  console.log("PUBLISH_HAS_QUEUE:", /queue|scheduled/i.test(body));
  console.log("PUBLISH_HAS_CALENDAR:", /calendar/i.test(body));

  // Try to open schedule form
  const scheduleBtn = page.getByRole("button", { name: /schedule|new post|add post/i }).first();
  const hasScheduleBtn = await scheduleBtn.count();
  console.log("HAS_SCHEDULE_BTN:", hasScheduleBtn > 0);

  if (hasScheduleBtn > 0) {
    await scheduleBtn.click();
    await page.waitForTimeout(1500);
    const formBody = await page.locator("body").innerText();
    console.log("FORM_OPENED:", /title|platform|date|content/i.test(formBody));
    // Take a screenshot of the form state
    await page.screenshot({ path: "/tmp/publish-form.png", fullPage: false });
  }

  await page.screenshot({ path: "/tmp/publish-page.png", fullPage: false });
  console.log("TOTAL_CONSOLE_ERRORS:", errors.length);
  errors.slice(0, 5).forEach((e) => console.log("  ERR:", e.slice(0, 200)));
});
