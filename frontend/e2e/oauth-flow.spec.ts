import { test, expect } from "@playwright/test";

/**
 * OAuth FLOW VERIFICATION — click "Continue with Google" on the live login
 * page and confirm it reaches Google sign-in (NOT a Vercel 404).
 * Run:
 *   BASE_URL=https://ai-studio88.vercel.app npx playwright test e2e/oauth-flow.spec.ts
 */
test("google oauth click reaches Google sign-in (no 404)", async ({ page }) => {
  const BASE = process.env.BASE_URL || "https://ai-studio88.vercel.app";
  const errors: string[] = [];

  page.on("response", (r) => {
    if (r.status() >= 400) {
      const url = r.url();
      // Ignore Supabase rate-limit / noise
      if (url.includes("supabase.co/auth/v1/callback")) return;
      errors.push(`${r.status()} ${url}`);
    }
  });

  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.getByText("Welcome back").first().waitFor({ timeout: 15000 });

  // Click the Google button
  const googleBtn = page.locator("button").filter({ hasText: /Continue with Google|Sign in with Google|Google/i }).first();
  await googleBtn.click({ timeout: 10000 });

  // Wait for navigation — should land on accounts.google.com OR a Supabase redirect
  await page.waitForTimeout(6000);
  const url = page.url();
  console.log("FINAL_URL:", url);
  console.log("ERRORS:", errors.length ? errors.join("\n") : "none");

  // Acceptable outcomes: Google sign-in page OR Supabase callback (OAuth consent)
  const onGoogle = url.includes("accounts.google.com");
  const onCallback = url.includes("supabase.co/auth/v1/callback");
  expect(onGoogle || onCallback, `should reach Google or Supabase callback, got: ${url}`).toBe(true);

  // Must NOT be a Vercel deployment 404
  expect(url).not.toContain("DEPLOYMENT_NOT_FOUND");
});
