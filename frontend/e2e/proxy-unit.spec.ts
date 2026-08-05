/**
 * Proxy Unit Tests — Story 066
 *
 * Tests for auth-utils functions used by the proxy.
 * Uses Next.js experimental testing utilities where available,
 * otherwise validates behavior through route-level assertions.
 */

import { test, expect } from "@playwright/test";

// =============================================================================
// Route Classification Tests (via behavior)
// =============================================================================

test.describe("Route classification behavior", () => {
  // Public exact paths
  test("/ is public (exact match)", async ({ page }) => {
    const response = await page.goto("/");
    expect(response?.status()).toBe(200);
    expect(page.url()).not.toContain("/login");
  });

  // Public prefix paths
  test("/login is public (prefix)", async ({ page }) => {
    const response = await page.goto("/login");
    expect(response?.status()).toBe(200);
    expect(page.url()).not.toContain("redirect");
  });

  test("/login/reset is public (prefix match)", async ({ page }) => {
    const response = await page.goto("/login/reset");
    // Should NOT redirect to /login (it IS /login prefix)
    expect(page.url()).not.toMatch(/\/login\?redirect/);
  });

  test("/auth/callback is public (prefix)", async ({ page }) => {
    await page.goto("/auth/callback");
    expect(page.url()).not.toMatch(/\/login\?redirect/);
  });

  // Protected paths
  test("/brain is protected", async ({ page }) => {
    await page.goto("/brain");
    await page.waitForURL("**/login**");
    expect(page.url()).toContain("/login");
  });

  test("/training is protected", async ({ page }) => {
    await page.goto("/training");
    await page.waitForURL("**/login**");
    expect(page.url()).toContain("/login");
  });

  test("/analytics is protected", async ({ page }) => {
    await page.goto("/analytics");
    await page.waitForURL("**/login**");
    expect(page.url()).toContain("/login");
  });
});

// =============================================================================
// Session Handling (via behavior)
// =============================================================================

test.describe("Session edge cases", () => {
  test("expired cookie still redirects to login", async ({ page, context }) => {
    // Set a fake expired/malformed Supabase cookie
    await context.addCookies([
      {
        name: "sb-access-token",
        value: "expired-garbage-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.goto("/brain");
    await page.waitForURL("**/login**");
    expect(page.url()).toContain("/login");
  });

  test("malformed cookie still redirects to login", async ({ page, context }) => {
    await context.addCookies([
      {
        name: "sb-access-token",
        value: "not-a-jwt",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.goto("/talent");
    await page.waitForURL("**/login**");
    expect(page.url()).toContain("/login");
  });

  test("legacy cookie (ai_studio_auth) is cleared", async ({ page, context }) => {
    // Set the legacy cookie
    await context.addCookies([
      {
        name: "ai_studio_auth",
        value: "old-insecure-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    // Visit a public route
    await page.goto("/");

    // Legacy cookie should be cleared from response
    const cookies = await context.cookies();
    const legacyCookie = cookies.find((c) => c.name === "ai_studio_auth");
    // Either removed or expired
    expect(!legacyCookie || legacyCookie.value === "").toBeTruthy();
  });
});

// =============================================================================
// Redirect Validation (via behavior)
// =============================================================================

test.describe("Redirect validation", () => {
  test("redirect param is a safe relative path", async ({ page }) => {
    await page.goto("/production");
    await page.waitForURL("**/login**");
    const url = new URL(page.url());
    const redirect = url.searchParams.get("redirect");
    // Must be relative, start with /
    expect(redirect).toBe("/production");
    expect(redirect).not.toContain("//");
    expect(redirect).not.toContain("http");
  });

  test("deeply nested protected route preserves full path in redirect", async ({
    page,
  }) => {
    await page.goto("/admin/fleet");
    await page.waitForURL("**/login**");
    const url = new URL(page.url());
    expect(url.searchParams.get("redirect")).toBe("/admin/fleet");
  });
});
