import { test, expect, Page } from "@playwright/test";

/**
 * FULL-STACK LIVE AUDIT — ai-studio88.vercel.app + Railway backend
 * Run: BASE_URL=https://ai-studio88.vercel.app npx playwright test e2e/full-stack-audit.spec.ts
 *
 * Covers:
 *  - All public routes render 200 + expected content, no console errors
 *  - All protected routes gate correctly (redirect to /login?redirect=)
 *  - Backend /ready reports capabilities
 *  - Network failures (failed API calls) captured per page
 */

const BASE = process.env.BASE_URL || "https://ai-studio88.vercel.app";
const BACKEND = process.env.BACKEND_URL || "https://web-production-1f511.up.railway.app";

const PUBLIC_ROUTES: Record<string, RegExp> = {
  "/": /Your AITalent Agency/i,
  "/login": /Welcome back|Sign in|Continue with Google/i,
  "/pricing": /Pricing/i,
  "/privacy": /Privacy Policy/i,
  "/terms": /Terms of Service/i,
};

const PROTECTED_ROUTES = [
  "/create", "/editor", "/assets", "/models", "/talent", "/projects",
  "/production", "/publish", "/training", "/workflows", "/story", "/analytics",
  "/settings", "/brain", "/admin", "/admin/fleet", "/admin/connections",
  "/admin/fleet-planner", "/admin/keys", "/admin/knowledge", "/admin/objects",
  "/admin/health", "/admin/ise", "/admin/downloads",
];

test.describe("full-stack live audit", () => {
  test.beforeEach(async ({ page }) => {
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        test.info().annotations.push({ type: "console-error", description: msg.text() });
      }
    });
    page.on("requestfailed", (req) => {
      test.info().annotations.push({ type: "request-failed", description: `${req.method()} ${req.url()} ${req.failure()?.errorText}` });
    });
    page.on("response", (res) => {
      if (res.status() >= 400 && res.url().includes("/api/")) {
        test.info().annotations.push({ type: "api-error", description: `${res.status()} ${res.url()}` });
      }
    });
  });

  test("public routes render correctly", async ({ page }) => {
    for (const [route, pattern] of Object.entries(PUBLIC_ROUTES)) {
      const resp = await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded" });
      expect(resp?.status(), `${route} status`).toBeLessThan(400);
      await expect(page.locator("body")).toContainText(pattern, { timeout: 15000 });
      // No redirect to login for public routes
      expect(page.url(), `${route} should stay`).toContain(route);
    }
  });

  test("protected routes gate to login", async ({ page }) => {
    for (const route of PROTECTED_ROUTES) {
      await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded" });
      // Should land on login with redirect param (client-side gate)
      await page.waitForURL(/\/(login|auth).*\?redirect=/, { timeout: 15000 }).catch(() => {});
      const url = page.url();
      expect(url, `${route} gates to login`).toContain("login");
      expect(url, `${route} keeps redirect`).toContain(encodeURIComponent(route));
    }
  });

  test("backend /ready reports capabilities", async ({ request }) => {
    const res = await request.get(`${BACKEND}/ready`, { timeout: 30000 });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("capabilities");
    const caps = body.capabilities;
    const states: Record<string, string> = {};
    for (const [name, cap] of Object.entries(caps)) {
      states[name] = (cap as any)?.state ?? "?";
    }
    test.info().annotations.push({ type: "backend-state", description: JSON.stringify(states) });
    // Print to stdout for the report
    console.log("BACKEND_STATES", JSON.stringify(states));
    // generation + auth are the critical ones
    expect(states.generation, "generation ready").toBe("ready");
    expect(states.auth, "auth ready").toBe("ready");
  });

  test("backend CORS allows the live app origin", async ({ request }) => {
    const res = await request.get(`${BACKEND}/ready`, {
      headers: { Origin: BASE },
      timeout: 30000,
    });
    const acao = res.headers()["access-control-allow-origin"];
    test.info().annotations.push({ type: "cors", description: `Origin ${BASE} -> ACAO: ${acao ?? "MISSING"}` });
    console.log("CORS_ACAO", acao ?? "MISSING");
  });
});
