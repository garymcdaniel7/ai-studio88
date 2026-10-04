import { expect, test } from "@playwright/test";
import {
  EDITOR_INTERSTITIAL_HTML,
  MIGRATION_REDIRECT_STATUS,
  MIGRATION_ROUTE_COUNT,
  V1_ROUTE_CONTRACT,
  buildMigrationLocation,
  getDestinationAdapter,
  getMigrationRoute,
  isSafeMigrationDestination,
} from "../src/lib/route-migration";
import { isPublicRoute, PLAYWRIGHT_AUTH_COOKIE } from "../src/lib/auth-utils";
import { test as authenticatedTest } from "./fixtures/authenticated";
const EXPECTED_DESTINATIONS: Record<string, string> = {
  "/home": "/start",
  "/create": "/make",
  "/production": "/write",
  "/training": "/cast?tab=training",
  "/talent": "/cast",
  "/workflows": "/make?tab=workflow",
  "/analytics": "/publish?tab=analytics",
  "/projects": "/start",
  "/jobs": "/make?tab=queue",
  "/assets": "/publish?tab=library",
  "/generate": "/make?tab=generate",
  "/video": "/make?tab=video",
  "/audio": "/make?tab=audio",
  "/campaigns": "/start?tab=campaigns",
  "/calendar": "/publish?tab=calendar",
  "/brands": "/start?tab=brands",
  "/teams": "/settings?tab=team",
  "/company": "/settings?tab=organization",
};

const PUBLIC_KEEP_ROUTES = new Set(["/", "/login", "/pricing"]);

test.describe("Phase 2 route absorption contract", () => {
  test("retains the complete 33-entry migration contract", () => {
    expect(V1_ROUTE_CONTRACT).toHaveLength(MIGRATION_ROUTE_COUNT);
    expect(new Set(V1_ROUTE_CONTRACT.map((route) => route.source)).size).toBe(MIGRATION_ROUTE_COUNT);
  });

  for (const [source, destination] of Object.entries(EXPECTED_DESTINATIONS)) {
    test(`${source} remains an authenticated 301 migration`, () => {
      expect(getMigrationRoute(source)?.kind).toBe("redirect");
      expect(getMigrationRoute(source)?.authRequired).toBe(true);
      expect(MIGRATION_REDIRECT_STATUS).toBe(301);
      expect(buildMigrationLocation(source)).toBe(destination);
    });
  }

  test("MAKE and WRITE are built canonical destinations, not adapters", () => {
    expect(getMigrationRoute("/make")).toBeUndefined();
    expect(getMigrationRoute("/write")).toBeUndefined();
    expect(getDestinationAdapter("/make")).toBeUndefined();
    expect(getDestinationAdapter("/write")).toBeUndefined();
  });

  test("START currently adapts to the preserved PROJECTS surface", () => {
    expect(getDestinationAdapter("/start")).toBe("/projects");
  });

  test("preserves query parameters while fixed route parameters win", () => {
    expect(buildMigrationLocation("/training", "talent_id=abc&tab=attacker&prompt=portrait%20test")).toBe(
      "/cast?tab=training&talent_id=abc&prompt=portrait+test",
    );
    expect(buildMigrationLocation("/home", "project_id=abc&view=recent")).toBe("/start?project_id=abc&view=recent");
  });

  test("keeps editor as a same-origin authenticated interstitial", () => {
    expect(getMigrationRoute("/editor")?.kind).toBe("interstitial");
    expect(getMigrationRoute("/editor")?.authRequired).toBe(true);
    expect(EDITOR_INTERSTITIAL_HTML).toContain('href="/write"');
    expect(EDITOR_INTERSTITIAL_HTML).toContain('href="/make"');
    expect(EDITOR_INTERSTITIAL_HTML).not.toContain("https://");
  });

  test("preserves public and protected route classification", () => {
    for (const route of V1_ROUTE_CONTRACT) {
      expect(isPublicRoute(route.source), route.source).toBe(
        !route.authRequired && PUBLIC_KEEP_ROUTES.has(route.source),
      );
    }
  });

  test("rejects external and unsafe destinations", () => {
    for (const destination of ["https://evil.example", "//evil.example", "javascript:alert(1)", "/\\evil", ""]) {
      expect(isSafeMigrationDestination(destination)).toBe(false);
    }
    expect(isSafeMigrationDestination("/make")).toBe(true);
    expect(isSafeMigrationDestination("/write?episode=1")).toBe(true);
  });

  test("uses the 60-day deprecation window only for the queue migration", () => {
    expect(getMigrationRoute("/jobs")?.deprecationDays).toBe(60);
    expect(getMigrationRoute("/create")?.deprecationDays).toBeUndefined();
  });

  test("local HTTP assertions use only the configured loopback server", async ({ request }, testInfo) => {
    const configuredBaseURL = testInfo.project.use.baseURL;
    expect(typeof configuredBaseURL).toBe("string");
    const baseURL = new URL(configuredBaseURL as string);
    expect(baseURL.protocol).toBe("http:");
    expect(["localhost", "127.0.0.1", "::1"]).toContain(baseURL.hostname);

    const headers = process.env.PLAYWRIGHT_AUTH_MODE === "mock"
      ? { Cookie: `${PLAYWRIGHT_AUTH_COOKIE}=authenticated` }
      : undefined;
    const response = await request.get("/create?prompt=portrait", { headers, maxRedirects: 0 });
    expect(response.status()).toBe(MIGRATION_REDIRECT_STATUS);
    expect(response.headers().location).toContain("/make");
    expect(response.headers().deprecation).toBe("true");
    expect(response.headers().sunset).toBeTruthy();
  });
});

authenticatedTest.describe("/editor authenticated deep-link evidence", () => {
  authenticatedTest("retains the post-owned editor behind the WRITE/MAKE interstitial", async ({ authenticatedPage }) => {
    const response = await authenticatedPage.goto("/editor");
    expect(response?.status()).toBe(200);
    await expect(authenticatedPage.getByRole("heading", { name: "The editor is being replaced" })).toBeVisible();
    await expect(authenticatedPage.getByRole("link", { name: "Continue to WRITE" })).toHaveAttribute("href", "/write");
    await expect(authenticatedPage.getByRole("link", { name: "Continue to MAKE" })).toHaveAttribute("href", "/make");
    expect(authenticatedPage.url()).toMatch(/\/editor$/);
  });
});
