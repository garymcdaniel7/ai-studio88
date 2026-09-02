import { test, expect, Page } from "@playwright/test";

/**
 * Live-app public-surface audit.
 * Run against the deployed app:
 *   BASE_URL=https://ai-studio88.vercel.app npx playwright test e2e/live-audit.spec.ts
 *
 * Purpose: inventory what's actually rendered and wired on the PUBLIC pages
 * (landing, login, legal), flag broken links/buttons, dead CTAs, and
 * UI→backend calls that 404/500. Auth-gated pages are covered separately
 * once test credentials exist.
 */

const BASE = process.env.BASE_URL || "http://localhost:3000";

async function collectLinks(page: Page) {
  return page.$$eval("a[href]", (as) =>
    as.map((a) => ({
      text: (a.textContent || "").trim().slice(0, 60),
      href: a.getAttribute("href"),
    })),
  );
}

async function collectButtons(page: Page) {
  return page.$$eval("button, [role='button'], [data-testid]", (els) =>
    els.map((el) => ({
      tag: el.tagName,
      text: (el.textContent || "").trim().slice(0, 60),
      disabled: el.hasAttribute("disabled"),
      testid: el.getAttribute("data-testid"),
    })),
  );
}

test.describe("live audit: public pages", () => {
  test("landing page renders core components and valid links", async ({ page }) => {
    const response = await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    expect(response!.status()).toBe(200);

    // Hero / headline present?
    const h1 = await page.locator("h1").first().textContent();
    expect(h1).toBeTruthy();
    console.log("H1:", h1);

    // CTAs that should exist on a landing page
    const buttons = await collectButtons(page);
    const links = await collectLinks(page);
    console.log("buttons:", JSON.stringify(buttons.slice(0, 15), null, 0));
    console.log("links:", JSON.stringify(links.slice(0, 25), null, 0));

    // All links should be valid (not javascript:, not empty)
    const broken = links.filter(
      (l) => !l.href || l.href.startsWith("javascript:") || l.href === "#",
    );
    expect(broken).toEqual([]);

    // Nav links should resolve (spot-check first 5 http links)
    const httpLinks = links.filter((l) => l.href && l.href.startsWith("http"));
    for (const link of httpLinks.slice(0, 5)) {
      const res = await page.request.get(link.href!, { timeout: 15000 });
      console.log("link status:", res.status(), link.href);
      expect(res.status() < 400, `link ${link.href} returned ${res.status()}`).toBeTruthy();
    }
  });

  test("login page renders and validates", async ({ page }) => {
    const response = await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
    expect(response!.status()).toBe(200);

    const buttons = await collectButtons(page);
    console.log("login buttons:", JSON.stringify(buttons, null, 0));
    const email = page.locator("input[type='email'], input[name='email']");
    const password = page.locator("input[type='password'], input[name='password']");
    console.log("email inputs:", await email.count(), "password inputs:", await password.count());

    // Submit empty → validation message expected
    if ((await email.count()) > 0) {
      const submit = page.locator("button[type='submit'], button:has-text('Sign'), button:has-text('Log')").first();
      if ((await submit.count()) > 0) {
        await submit.click();
        await page.waitForTimeout(800);
        const body = await page.locator("body").innerText();
        const hasMsg = /email|password|required/i.test(body);
        console.log("validation message shown:", hasMsg);
      }
    }

    // Google OAuth button should exist and link to the provider flow
    const googleBtn = page.locator("button:has-text('Google'), a:has-text('Google')").first();
    if ((await googleBtn.count()) > 0) {
      console.log("Google button present:", await googleBtn.textContent());
    } else {
      console.log("WARN: no Google sign-in button found");
    }
  });

  test("legal pages public + reachable", async ({ page }) => {
    for (const path of ["/privacy", "/terms"]) {
      const res = await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
      expect(res!.status(), `${path} should be 200, got ${res!.status()}`).toBe(200);
      const body = await page.locator("body").innerText();
      expect(body.length).toBeGreaterThan(200);
      console.log(`${path}: OK (${body.length} chars)`);
    }
  });

  test("auth gate: app pages redirect to login", async ({ page }) => {
    for (const path of ["/create", "/editor", "/assets", "/admin"]) {
      const res = await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
      // Either 200 with login redirect or 200 landing on login
      const url = page.url();
      console.log(`${path} → ${url}`);
      expect(url.includes("/login"), `${path} should gate to login, landed ${url}`).toBeTruthy();
    }
  });
});
