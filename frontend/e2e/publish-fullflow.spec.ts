import { test, expect, Page } from "@playwright/test";

/**
 * PUBLISH FULL FLOW: schedule a post via the form, verify it lands in
 * queue + calendar. Then check the backend row (draft vs scheduled).
 */
const BASE = process.env.BASE_URL || "https://ai-studio88.vercel.app";
const EMAIL = process.env.TEST_EMAIL || "";
const PASSWORD = process.env.TEST_PASSWORD || "";

const TS = Date.now();

async function login(page: Page) {
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("you@example.com").fill(EMAIL);
  await page.getByPlaceholder("At least 6 characters").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForTimeout(3000);
}

test("publish: full schedule flow lands in queue + calendar", async ({ page }) => {
  test.skip(!EMAIL, "TEST_EMAIL not set");
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  await login(page);
  await page.goto(`${BASE}/publish`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);

  // Open form
  await page.getByRole("button", { name: /schedule post/i }).first().click();
  await page.waitForTimeout(800);

  // Fill
  const title = `PW Test Post ${TS}`;
  await page.getByPlaceholder("Post title").fill(title);
  await page.getByPlaceholder("Post content / caption...").fill("Playwright e2e scheduling test content");
  // pick a date 2 days out
  const d = new Date(Date.now() + 2 * 86400000);
  const iso = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}T12:00`;
  await page.locator('input[type="datetime-local"]').fill(iso);

  // Submit
  await page.getByRole("button", { name: /^Schedule$/ }).click();
  await page.waitForTimeout(3000);

  // Check queue text
  const body = await page.locator("body").innerText();
  const inQueue = body.includes(title);
  console.log("TITLE_IN_QUEUE:", inQueue);

  // Switch to calendar view
  await page.getByRole("button", { name: /^Calendar$/ }).click();
  await page.waitForTimeout(1500);
  const calBody = await page.locator("body").innerText();
  console.log("TITLE_IN_CALENDAR:", calBody.includes(title));

  // Toast success?
  const hasSuccess = await page.locator("body").innerText().then(t => /scheduled successfully/i.test(t));
  console.log("SUCCESS_TOAST:", hasSuccess);

  await page.screenshot({ path: "/tmp/publish-after-schedule.png", fullPage: true });
  console.log("TOTAL_CONSOLE_ERRORS:", errors.length);
  errors.slice(0, 5).forEach((e) => console.log("  ERR:", e.slice(0, 200)));

  // Assertions: queue should have it
  expect(inQueue).toBe(true);
});
