import { test, expect, Page } from "@playwright/test";

/**
 * AUTHENTICATED full-stack audit — single logged-in session covers all pages.
 * Run:
 *   BASE_URL=https://ai-studio88.vercel.app \
 *   TEST_EMAIL=hermes.uat@aistudio88.dev \
 *   TEST_PASSWORD=*** \
 *   npx playwright test e2e/auth-audit.spec.ts --project=desktop
 */

const BASE = process.env.BASE_URL || "https://ai-studio88.vercel.app";
const EMAIL = process.env.TEST_EMAIL || "";
const PASSWORD = process.env.TEST_PASSWORD || "";

async function login(page: Page) {
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("you@example.com").fill(EMAIL);
  await page.getByPlaceholder("At least 6 characters").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 25000 });
}

async function trackErrors(page: Page) {
  (page as any).__consoleErrors = [];
  page.on("console", (m) => m.type() === "error" && (page as any).__consoleErrors.push(m.text()));
  (page as any).__failedRequests = [];
  page.on("requestfailed", (r) => {
    const err = r.failure()?.errorText || "";
    if (err.includes("ERR_ABORTED")) return; // benign: aborted RSC prefetch during nav
    (page as any).__failedRequests.push(`${r.method()} ${r.url()} :: ${err}`);
  });
}

test("authenticated full-stack audit", async ({ page }) => {
  test.skip(!EMAIL || !PASSWORD, "TEST_EMAIL/TEST_PASSWORD not set");
  await trackErrors(page);

  // 1. LOGIN
  await login(page);
  console.log("LOGIN_OK", page.url());

  // 2. CREATE PAGE — model + LoRA dropdowns
  await page.goto(`${BASE}/create`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(4000);
  const createText = await page.locator("body").innerText();
  const modelMentions = (createText.match(/flux|klein|sdxl|turbo|krea|wan|h3/i) || []).length;
  const loraMentions = (createText.match(/lora/gi) || []).length;
  console.log("CREATE_MODEL_MENTIONS", modelMentions, "LORA_MENTIONS", loraMentions);
  expect(modelMentions).toBeGreaterThan(0);
  const createFailed = (page as any).__failedRequests || [];
  console.log("CREATE_FAILED", JSON.stringify(createFailed));
  expect(createFailed.filter((r: string) => !/analytics|fonts|gtm/.test(r))).toEqual([]);

  // 3. SETTINGS — migrated selects render (Preferences tab)
  await page.goto(`${BASE}/settings`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  // Click into the Preferences tab where the migrated selects live
  const prefsTab = page.getByRole("button", { name: /preferences/i }).first();
  if (await prefsTab.isVisible().catch(() => false)) {
    await prefsTab.click();
    await page.waitForTimeout(1500);
  }
  const settingsText = await page.locator("body").innerText();
  const hasRecipe = /recipe|auto \(ai picks best\)|preferred recipe/i.test(settingsText);
  const hasFormat = /format|square \(1024x1024\)|landscape|portrait/i.test(settingsText);
  console.log("SETTINGS_RECIPE", hasRecipe, "FORMAT", hasFormat);
  expect(hasRecipe || hasFormat).toBe(true);

  // 4. ASSETS — real data, no 500
  await page.goto(`${BASE}/assets`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  const assetsText = await page.locator("body").innerText();
  console.log("ASSETS_SNIPPET", assetsText.slice(0, 150).replace(/\n+/g, " | "));
  expect(/error|something went wrong/i.test(assetsText)).toBe(false);

  // 5. ADMIN/FLEET — governed actions render
  await page.goto(`${BASE}/admin/fleet`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  const fleetText = await page.locator("body").innerText();
  console.log("FLEET_SNIPPET", fleetText.slice(0, 200).replace(/\n+/g, " | "));
  expect(/error|forbidden|access denied/i.test(fleetText)).toBe(false);
  expect(fleetText).not.toContain("Welcome back"); // not bounced to login

  // 6. ADMIN/CONNECTIONS — scaffold router live
  await page.goto(`${BASE}/admin/connections`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  const connText = await page.locator("body").innerText();
  const connFailed = (page as any).__failedRequests || [];
  console.log("CONNECTIONS_FAILED", JSON.stringify(connFailed));
  console.log("CONNECTIONS_SNIPPET", connText.slice(0, 200).replace(/\n+/g, " | "));
  expect(/error|something went wrong/i.test(connText)).toBe(false);

  // 7. LOGOUT
  const logout = page.getByRole("button", { name: /log out|sign out|logout/i }).first();
  if (await logout.isVisible().catch(() => false)) {
    await logout.click();
    await page.waitForURL((u) => u.pathname.includes("login"), { timeout: 15000 });
    console.log("LOGOUT_OK");
  } else {
    console.log("LOGOUT_BUTTON_NOT_FOUND");
  }

  const consoleErrors = (page as any).__consoleErrors || [];
  console.log("TOTAL_CONSOLE_ERRORS", JSON.stringify(consoleErrors));
});
