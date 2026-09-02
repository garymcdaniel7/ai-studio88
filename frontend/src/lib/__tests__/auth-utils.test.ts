/**
 * Unit tests for auth-utils.ts — safe redirects, public routes, auth states.
 *
 * Run with: npx jest src/lib/__tests__/auth-utils.test.ts
 */

import {
  isPublicRoute,
  validateRedirectTarget,
  LEGACY_COOKIE_NAME,
} from "../auth-utils";

// =============================================================================
// Safe Redirect Validation
// =============================================================================

describe("validateRedirectTarget", () => {
  it("returns / for null input", () => {
    expect(validateRedirectTarget(null)).toBe("/");
  });

  it("returns / for undefined input", () => {
    expect(validateRedirectTarget(undefined)).toBe("/");
  });

  it("returns / for empty string", () => {
    expect(validateRedirectTarget("")).toBe("/");
  });

  it("accepts valid internal paths", () => {
    expect(validateRedirectTarget("/talent")).toBe("/talent");
    expect(validateRedirectTarget("/brain")).toBe("/brain");
    expect(validateRedirectTarget("/admin/fleet")).toBe("/admin/fleet");
    expect(validateRedirectTarget("/create?tab=image")).toBe("/create?tab=image");
  });

  it("rejects protocol-relative URLs (open redirect)", () => {
    expect(validateRedirectTarget("//evil.com")).toBe("/");
    expect(validateRedirectTarget("//evil.com/path")).toBe("/");
  });

  it("rejects absolute URLs with protocols", () => {
    expect(validateRedirectTarget("http://evil.com")).toBe("/");
    expect(validateRedirectTarget("https://evil.com/path")).toBe("/");
    expect(validateRedirectTarget("javascript:alert(1)")).toBe("/");
    expect(validateRedirectTarget("data:text/html,<script>")).toBe("/");
  });

  it("rejects paths not starting with /", () => {
    expect(validateRedirectTarget("evil.com")).toBe("/");
    expect(validateRedirectTarget("relative/path")).toBe("/");
  });

  it("rejects encoded slashes (bypass attempt)", () => {
    expect(validateRedirectTarget("/%2f/evil.com")).toBe("/");
    expect(validateRedirectTarget("/%2F%2Fevil.com")).toBe("/");
  });

  it("rejects backslashes (IE attack vector)", () => {
    expect(validateRedirectTarget("/\\evil.com")).toBe("/");
    expect(validateRedirectTarget("\\evil.com")).toBe("/");
  });

  it("rejects redirect to /login (infinite loop)", () => {
    expect(validateRedirectTarget("/login")).toBe("/");
    expect(validateRedirectTarget("/login?redirect=/brain")).toBe("/");
  });

  it("rejects redirect to /auth (internal)", () => {
    expect(validateRedirectTarget("/auth/callback")).toBe("/");
    expect(validateRedirectTarget("/auth/logout")).toBe("/");
  });

  it("handles whitespace", () => {
    expect(validateRedirectTarget("  /talent  ")).toBe("/talent");
    expect(validateRedirectTarget("   ")).toBe("/");
  });
});

// =============================================================================
// Public Route Detection
// =============================================================================

describe("isPublicRoute", () => {
  it("recognizes login as public", () => {
    expect(isPublicRoute("/login")).toBe(true);
    expect(isPublicRoute("/login?redirect=/brain")).toBe(true);
  });

  it("recognizes root as public", () => {
    expect(isPublicRoute("/")).toBe(true);
  });

  it("recognizes legal pages as public", () => {
    expect(isPublicRoute("/privacy")).toBe(true);
    expect(isPublicRoute("/terms")).toBe(true);
  });

  it("recognizes API routes as public", () => {
    expect(isPublicRoute("/api/v1/health")).toBe(true);
    expect(isPublicRoute("/api/anything")).toBe(true);
  });

  it("recognizes Next.js internals as public", () => {
    expect(isPublicRoute("/_next/static/chunk.js")).toBe(true);
    expect(isPublicRoute("/_next/image")).toBe(true);
  });

  it("recognizes auth routes as public", () => {
    expect(isPublicRoute("/auth/logout")).toBe(true);
    expect(isPublicRoute("/auth/callback")).toBe(true);
  });

  it("marks protected routes as non-public", () => {
    expect(isPublicRoute("/talent")).toBe(false);
    expect(isPublicRoute("/brain")).toBe(false);
    expect(isPublicRoute("/admin")).toBe(false);
    expect(isPublicRoute("/create")).toBe(false);
    expect(isPublicRoute("/settings")).toBe(false);
  });
});

// =============================================================================
// Legacy Cookie Name
// =============================================================================

describe("LEGACY_COOKIE_NAME", () => {
  it("is the old insecure cookie name", () => {
    expect(LEGACY_COOKIE_NAME).toBe("ai_studio_auth");
  });
});
