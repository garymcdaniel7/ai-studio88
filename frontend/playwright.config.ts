import { defineConfig } from "@playwright/test";

/**
 * Playwright config supporting:
 * - Desktop (1440x900) + Mobile (390x844)
 * - Localhost (default) or Vercel (via BASE_URL env var)
 *
 * Run against localhost:  npx playwright test
 * Run against Vercel:    BASE_URL=https://ai-studio99.vercel.app npx playwright test
 */
const baseURL = process.env.BASE_URL || "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45000,
  expect: { timeout: 10000 },
  retries: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL,
    headless: true,
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    actionTimeout: 10000,
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: baseURL.includes("localhost")
    ? {
        command: "npm run dev",
        port: 3000,
        reuseExistingServer: true,
      }
    : undefined,
});
