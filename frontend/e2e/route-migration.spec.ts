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
import { isPublicRoute } from "../src/lib/auth-utils";

const EXPECTED_ROUTES = [
  "/",
  "/home",
  "/create",
  "/editor",
  "/production",
  "/training",
  "/talent",
  "/workflows",
  "/analytics",
  "/projects",
  "/models",
  "/jobs",
  "/brain",
  "/login",
  "/assets",
  "/pricing",
  "/story",
  "/settings",
  "/admin",
  "/admin/fleet",
  "/admin/ise",
  "/admin/keys",
  "/admin/knowledge",
  "/admin/downloads",
  "/publish",
  "/generate",
  "/video",
  "/audio",
  "/campaigns",
  "/calendar",
  "/brands",
  "/teams",
  "/company",
] as const;

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
  "/admin/fleet": "/admin?tab=fleet",
  "/admin/ise": "/admin?tab=ise",
  "/admin/keys": "/admin?tab=keys",
  "/admin/knowledge": "/admin?tab=knowledge",
  "/admin/downloads": "/admin?tab=downloads",
  "/generate": "/make?tab=generate",
  "/video": "/make?tab=video",
  "/audio": "/make?tab=audio",
  "/campaigns": "/start?tab=campaigns",
  "/calendar": "/publish?tab=calendar",
  "/brands": "/start?tab=brands",
  "/teams": "/settings?tab=team",
  "/company": "/settings?tab=organization",
};

const KEEP_ROUTES = new Set(["/", "/brain", "/login", "/pricing", "/story", "/settings", "/admin", "/publish"]);
const PUBLIC_KEEP_ROUTES = new Set(["/", "/login", "/pricing"]);

test.describe("Phase 1 V1-to-V2 route migration contract", () => {
  test("contains exactly the verified 33 route entries", () => {
    expect(V1_ROUTE_CONTRACT).toHaveLength(MIGRATION_ROUTE_COUNT);
    expect(V1_ROUTE_CONTRACT.map((route) => route.source)).toEqual(EXPECTED_ROUTES);
  });

  for (const [source, expectedDestination] of Object.entries(EXPECTED_DESTINATIONS)) {
    test(`${source} returns a 301 location for its V2 destination`, () => {
      const route = getMigrationRoute(source);
      expect(route?.kind).toBe("redirect");
      expect(route?.authRequired).toBe(true);
      expect(MIGRATION_REDIRECT_STATUS).toBe(301);
      expect(buildMigrationLocation(source)).toBe(expectedDestination);
    });
  }

  test("/models preserves the character/generative split", () => {
    expect(buildMigrationLocation("/models", "model_type=character&talent_id=abc")).toBe(
      "/cast?section=models&model_type=character&talent_id=abc",
    );
    expect(buildMigrationLocation("/models", "type=generative&family=flux")).toBe(
      "/admin/models?section=generative&type=generative&family=flux",
    );
    expect(buildMigrationLocation("/models", "model_type=lora")).toBe(
      "/cast?section=models&model_type=lora",
    );
  });

  test("forwards query parameters while fixed migration parameters win", () => {
    const location = buildMigrationLocation(
      "/training",
      "talent_id=abc&talent_id=def&tab=attacker&prompt=portrait%20test",
    );
    expect(location).toBe(
      "/cast?tab=training&talent_id=abc&talent_id=def&prompt=portrait+test",
    );

    expect(buildMigrationLocation("/home", "project_id=abc&view=recent")).toBe(
      "/start?project_id=abc&view=recent",
    );
  });

  test("uses the shorter 60-day deprecation window only for jobs", () => {
    expect(getMigrationRoute("/jobs")?.deprecationDays).toBe(60);
    expect(getMigrationRoute("/create")?.deprecationDays).toBeUndefined();
  });

  test("kept routes do not redirect and retain their public/protected contract", () => {
    for (const source of KEEP_ROUTES) {
      const route = getMigrationRoute(source);
      expect(route?.kind, source).toBe("keep");
      expect(buildMigrationLocation(source), source).toBeNull();
      expect(route?.authRequired, source).toBe(!PUBLIC_KEEP_ROUTES.has(source));
      expect(isPublicRoute(source), source).toBe(PUBLIC_KEEP_ROUTES.has(source));
    }
  });

  test("editor remains a Phase 1 interstitial with only local WRITE/MAKE links", () => {
    expect(getMigrationRoute("/editor")?.kind).toBe("interstitial");
    expect(getMigrationRoute("/editor")?.authRequired).toBe(true);
    expect(buildMigrationLocation("/editor")).toBeNull();
    expect(EDITOR_INTERSTITIAL_HTML).toContain('href="/write"');
    expect(EDITOR_INTERSTITIAL_HTML).toContain('href="/make"');
    expect(EDITOR_INTERSTITIAL_HTML).not.toContain("http://");
    expect(EDITOR_INTERSTITIAL_HTML).not.toContain("https://");
  });

  test("rejects unsafe or external destinations", () => {
    for (const destination of [
      "https://evil.example/steal",
      "//evil.example/steal",
      "javascript:alert(1)",
      "/\\evil.example",
      "",
    ]) {
      expect(isSafeMigrationDestination(destination), destination).toBe(false);
    }
    for (const destination of ["/make", "/admin?tab=fleet", "/cast?section=models"]) {
      expect(isSafeMigrationDestination(destination), destination).toBe(true);
    }
  });

  test("has no redirect-source collisions or unsafe destination adapters", () => {
    const redirectSources = new Set(
      V1_ROUTE_CONTRACT.filter((route) => route.kind === "redirect").map((route) => route.source),
    );
    for (const route of V1_ROUTE_CONTRACT) {
      if (route.kind !== "redirect" || !route.destination) continue;
      expect(redirectSources.has(route.destination), route.source).toBe(false);
    }
    expect(getDestinationAdapter("/start")).toBe("/projects");
    expect(getDestinationAdapter("/admin/models")).toBe("/models");
  });

  test("every migrating source is protected before redirect/interstitial handling", () => {
    for (const route of V1_ROUTE_CONTRACT) {
      if (route.kind === "keep" && !route.authRequired) continue;
      expect(route.authRequired, route.source).toBe(true);
      expect(isPublicRoute(route.source), route.source).toBe(false);
    }
  });

  test("built frontend representative requests expose the migration status when local fallback is active", async ({
    request,
  }) => {
    test.skip(
      !process.env.ROUTE_MIGRATION_HTTP,
      "Set ROUTE_MIGRATION_HTTP=1 with an authenticated/local-fallback server for HTTP assertions",
    );
    const response = await request.get("/training?talent_id=abc", { maxRedirects: 0 });
    expect(response.status()).toBe(MIGRATION_REDIRECT_STATUS);
    expect(response.headers().location).toContain("/cast?tab=training");
    expect(response.headers().location).toContain("talent_id=abc");
    expect(response.headers().deprecation).toBe("true");
    expect(response.headers().sunset).toBeTruthy();
  });

  test("built frontend editor response exposes the interstitial when local fallback is active", async ({
    request,
  }) => {
    test.skip(
      !process.env.ROUTE_MIGRATION_HTTP,
      "Set ROUTE_MIGRATION_HTTP=1 with an authenticated/local-fallback server for HTTP assertions",
    );
    const response = await request.get("/editor", { maxRedirects: 0 });
    expect(response.status()).toBe(200);
    const body = await response.text();
    expect(body).toContain("/write");
    expect(body).toContain("/make");
    expect(response.headers().deprecation).toBe("true");
  });
});
