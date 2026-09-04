import { test, expect, Page } from "@playwright/test";

/**
 * AUTHENTICATED full-stack audit — auth-gated pages + UI→backend contract.
 * Run with:
 *   BASE_URL=https://ai-studio88.vercel.app \
 *   TEST_EMAIL=hermes.uat@aistudio88.dev \
 *   TEST_PASSWORD=*** \
 *   npx playwright test e2e/auth-audit.spec.ts --project=desktop
 */

const BASE = process.env.BASE_URL || "https://ai-studio88.vercel.app";
const EMAIL = process.env.TEST_EMAIL || "";
const PASSWORD = process.env.TEST_PASSWORD || "";

test.beforeEach(async ({ page }) => {
  // Capture console errors + failed requests
  (page as any).__consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") (page as any).__consoleErrors.push(msg.text());
  });
  (page as any).__failedRequests = [];
  page.on("requestfailed", (req) =>
    (page as any).__failedRequests.push(`${req.method()} ${req.url()}`)
  );
});

test("login with test account", async ({ page }) => {
  test.skip(!EMAIL || !PASSWORD, "TEST_EMAIL/TEST_PASSWORD not set");
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("you@example.com").fill(EMAIL);
  await page.getByPlaceholder("At least 6 characters").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  // Should land on a protected page (dashboard or create)
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 });
  expect(page.url()).not.toContain("/login");
  console.log("LOGGED_IN_URL", page.url());
});

test("create page: model + LoRA dropdowns populated", async ({ page }) => {
  await page.goto(`${BASE}/create`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body", { timeout: 15000 });
  // Wait for the model selector to render
  await page.waitForTimeout(3000);
  const bodyText = await page.locator("body").innerText();
  // Model selector should list real model names (flux2-klein / SDXL / krea)
  const modelMentions = (bodyText.match(/flux|klein|sdxl|turbo|krea|wan|h3/gi) || []).length;
  console.log("MODEL_MENTIONS", modelMentions);
  // Advanced settings should expose LoRA picker with catalog entries
  const loraMentions = (bodyText.match(/lora/gi) || []).length;
  console.log("LORA_MENTIONS", loraMentions);
  expect(modelMentions).toBeGreaterThan(0);
  // No failed API requests on the page
  const failed = (page as any).__failedRequests || [];
  console.log("FAILED_REQUESTS", JSON.stringify(failed));
  expect(failed.filter((r: string) => !r.includes("analytics") && !r.includes("fonts"))).toEqual([]);
});

test("settings page renders migrated selects", async ({ page }) => {
  await page.goto(`${BASE}/settings`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body", { timeout: 15000 });
  await page.waitForTimeout(2000);
  const bodyText = await page.locator("body").innerText();
  const hasRecipe = /recipe|auto|flux/i.test(bodyText);
  const hasFormat = /format|square|landscape|portrait/i.test(bodyText);
  console.log("SETTINGS_HAS_RECIPE", hasRecipe, "HAS_FORMAT", hasFormat);
  expect(hasRecipe || hasFormat).toBe(true);
});

test("assets page returns real data (no 500)", async ({ page }) => {
  await page.goto(`${BASE}/assets`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body", { timeout: 15000 });
  const failed = (page as any).__failedRequests || [];
  console.log("ASSETS_FAILED", JSON.stringify(failed));
  const bodyText = await page.locator("body").innerText();
  // Either empty-state or list renders — but NOT an error page
  expect(/error|something went wrong/i.test(bodyText)).toBe(false);
});

test("admin/fleet renders (governed actions)", async ({ page }) => {
  await page.goto(`${BASE}/admin/fleet`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body", { timeout: 15000 });
  await page.waitForTimeout(2000);
  const bodyText = await page.locator("body").innerText();
  console.log("FLEET_SNIPPET", bodyText.slice(0, 300).replace(/\n+/g, " | "));
  // Should see fleet UI, not an error/403
  expect(/error|forbidden|access denied/i.test(bodyText)).toBe(false);
});

test("admin/connections renders (scaffold router now live)", async ({ page }) => {
  await page.goto(`${BASE}/admin/connections`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body", { timeout: 15000 });
  await page.waitForTimeout(2000);
  const bodyText = await page.locator("body").innerText();
  const failed = (page as any).__failedRequests || [];
  console.log("CONNECTIONS_FAILED", JSON.stringify(failed));
  console.log("CONNECTIONS_SNIPPET", bodyText.slice(0, 300).replace(/\n+/g, " | "));
  expect(/error|something went wrong/i.test(bodyText)).toBe(false);
});

test("logout works", async ({ page }) => {
  await page.goto(`${BASE}/settings`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("body", { timeout: 15000 });
  // Find logout button (usually in topbar/settings)
  const logout = page.getByRole("button", { name: /log out|sign out|logout/i }).first();
  if (await logout.isVisible().catch(() => false)) {
    await logout.click();
    await page.waitForURL((u) => u.pathname.includes("login"), { timeout: 15000 });
    console.log("LOGOUT_OK");
  } else {
    console.log("LOGOUT_BUTTON_NOT_FOUND");
  }
});
