/**
 * Explicit Phase 1-to-Phase 2 route migration contract.
 *
 * Legacy routes are authenticated before this map is applied by proxy.ts.
 * Redirects are same-origin, preserve caller query parameters, and use fixed
 * contract parameters when a legacy caller tries to override them.
 */

export const MIGRATION_REDIRECT_STATUS = 301;
export const MIGRATION_ROUTE_COUNT = 33;
export const MIGRATION_DEPRECATION_HEADER = "true";

export const EDITOR_INTERSTITIAL_HTML = `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Editor moved</title></head>
  <body>
    <main>
      <h1>The editor is being replaced</h1>
      <p>Choose the authenticated Phase 2 workspace that owns this capability.</p>
      <nav aria-label="Editor destinations">
        <a href="/write">Continue to WRITE</a>
        <a href="/make">Continue to MAKE</a>
      </nav>
    </main>
  </body>
</html>`;

export type MigrationRouteKind = "keep" | "redirect" | "interstitial";

export type MigrationRoute = {
  source: string;
  kind: MigrationRouteKind;
  authRequired: boolean;
  destination?: string;
  fixedQuery?: Readonly<Record<string, string>>;
  deprecationDays?: number;
};

export const V1_ROUTE_CONTRACT: readonly MigrationRoute[] = [
  { source: "/", kind: "keep", authRequired: false },
  { source: "/home", kind: "redirect", authRequired: true, destination: "/start" },
  { source: "/create", kind: "redirect", authRequired: true, destination: "/make" },
  { source: "/editor", kind: "interstitial", authRequired: true, deprecationDays: 90 },
  { source: "/production", kind: "redirect", authRequired: true, destination: "/write" },
  { source: "/training", kind: "redirect", authRequired: true, destination: "/cast", fixedQuery: { tab: "training" } },
  { source: "/talent", kind: "redirect", authRequired: true, destination: "/cast" },
  { source: "/workflows", kind: "redirect", authRequired: true, destination: "/make", fixedQuery: { tab: "workflow" } },
  { source: "/analytics", kind: "redirect", authRequired: true, destination: "/publish", fixedQuery: { tab: "analytics" } },
  { source: "/projects", kind: "redirect", authRequired: true, destination: "/start" },
  { source: "/models", kind: "redirect", authRequired: true, deprecationDays: 90 },
  { source: "/jobs", kind: "redirect", authRequired: true, destination: "/make", fixedQuery: { tab: "queue" }, deprecationDays: 60 },
  { source: "/brain", kind: "keep", authRequired: true },
  { source: "/login", kind: "keep", authRequired: false },
  { source: "/assets", kind: "redirect", authRequired: true, destination: "/publish", fixedQuery: { tab: "library" } },
  { source: "/pricing", kind: "keep", authRequired: false },
  { source: "/story", kind: "keep", authRequired: true },
  { source: "/settings", kind: "keep", authRequired: true },
  { source: "/admin", kind: "keep", authRequired: true },
  { source: "/admin/fleet", kind: "redirect", authRequired: true, destination: "/admin", fixedQuery: { tab: "fleet" } },
  { source: "/admin/ise", kind: "redirect", authRequired: true, destination: "/admin", fixedQuery: { tab: "ise" } },
  { source: "/admin/keys", kind: "redirect", authRequired: true, destination: "/admin", fixedQuery: { tab: "keys" } },
  { source: "/admin/knowledge", kind: "redirect", authRequired: true, destination: "/admin", fixedQuery: { tab: "knowledge" } },
  { source: "/admin/downloads", kind: "redirect", authRequired: true, destination: "/admin", fixedQuery: { tab: "downloads" } },
  { source: "/publish", kind: "keep", authRequired: true },
  { source: "/generate", kind: "redirect", authRequired: true, destination: "/make", fixedQuery: { tab: "generate" } },
  { source: "/video", kind: "redirect", authRequired: true, destination: "/make", fixedQuery: { tab: "video" } },
  { source: "/audio", kind: "redirect", authRequired: true, destination: "/make", fixedQuery: { tab: "audio" } },
  { source: "/campaigns", kind: "redirect", authRequired: true, destination: "/start", fixedQuery: { tab: "campaigns" } },
  { source: "/calendar", kind: "redirect", authRequired: true, destination: "/publish", fixedQuery: { tab: "calendar" } },
  { source: "/brands", kind: "redirect", authRequired: true, destination: "/start", fixedQuery: { tab: "brands" } },
  { source: "/teams", kind: "redirect", authRequired: true, destination: "/settings", fixedQuery: { tab: "team" } },
  { source: "/company", kind: "redirect", authRequired: true, destination: "/settings", fixedQuery: { tab: "organization" } },
] as const;

/**
 * Internal adapters keep destinations renderable while adjacent lanes finish
 * their route surfaces. The browser remains on the canonical destination.
 */
export const DESTINATION_ADAPTERS: Readonly<Record<string, string>> = {
  "/start": "/projects",
  "/cast": "/talent",
  "/admin/models": "/models",
};

const MODEL_TYPE_KEYS = ["model_type", "modelType", "type", "kind", "category"] as const;
const CHARACTER_MODEL_TYPES = new Set(["character", "talent", "persona", "lora"]);

function getRoute(source: string): MigrationRoute | undefined {
  return V1_ROUTE_CONTRACT.find((route) => route.source === source);
}

function getSearchParams(input: URL | URLSearchParams | string | { readonly search: string }): URLSearchParams {
  if (typeof input === "string") return new URLSearchParams(input.startsWith("?") ? input.slice(1) : input);
  if (input instanceof URLSearchParams) return new URLSearchParams(input);
  return new URLSearchParams(input.search);
}

/** Return true only for a local, absolute-path migration destination. */
export function isSafeMigrationDestination(destination: string): boolean {
  if (!destination || !destination.startsWith("/") || destination.startsWith("//")) return false;
  if (destination.includes("\\") || /^[a-z][a-z\d+.-]*:/i.test(destination)) return false;
  try {
    const parsed = new URL(destination, "https://migration.invalid");
    return parsed.origin === "https://migration.invalid" && parsed.pathname.startsWith("/");
  } catch {
    return false;
  }
}

function getModelDestination(params: URLSearchParams): string {
  const modelType = MODEL_TYPE_KEYS.map((key) => params.get(key)?.trim().toLowerCase()).find(Boolean);
  return modelType && CHARACTER_MODEL_TYPES.has(modelType) ? "/cast" : "/admin/models";
}

function getFixedQuery(route: MigrationRoute, params: URLSearchParams): Readonly<Record<string, string>> {
  if (route.source === "/models") return { section: getModelDestination(params) === "/cast" ? "models" : "generative" };
  return route.fixedQuery ?? {};
}

/** Build a same-origin location while preserving non-conflicting query values. */
export function buildMigrationLocation(source: string, input: URL | URLSearchParams | string = ""): string | null {
  const route = getRoute(source);
  if (!route || route.kind !== "redirect") return null;
  const params = getSearchParams(input);
  const destination = route.source === "/models" ? getModelDestination(params) : route.destination;
  if (!destination || !isSafeMigrationDestination(destination)) return null;
  const fixedQuery = getFixedQuery(route, params);
  const target = new URL(destination, "https://migration.invalid");
  for (const [key, value] of Object.entries(fixedQuery)) target.searchParams.set(key, value);
  for (const [key, value] of params.entries()) if (!(key in fixedQuery)) target.searchParams.append(key, value);
  return `${target.pathname}${target.search}`;
}

/** Return the explicit route contract for a legacy path. */
export function getMigrationRoute(source: string): MigrationRoute | undefined {
  return getRoute(source);
}

/** Return an internal adapter for a canonical destination, if needed. */
export function getDestinationAdapter(pathname: string): string | undefined {
  return DESTINATION_ADAPTERS[pathname];
}

/** Return the observable sunset date for a deprecation window. */
export function getSunsetDate(days: number): string {
  return new Date(Date.now() + days * 24 * 60 * 60 * 1000).toUTCString();
}

/** Validate route count, duplicate sources, unsafe destinations, and loops. */
export function validateMigrationContract(): void {
  if (V1_ROUTE_CONTRACT.length !== MIGRATION_ROUTE_COUNT) throw new Error(`Expected ${MIGRATION_ROUTE_COUNT} migration routes`);
  const sources = new Set(V1_ROUTE_CONTRACT.map((route) => route.source));
  const redirectSources = new Set(V1_ROUTE_CONTRACT.filter((route) => route.kind === "redirect").map((route) => route.source));
  if (sources.size !== V1_ROUTE_CONTRACT.length) throw new Error("Duplicate migration source");
  for (const route of V1_ROUTE_CONTRACT) {
    if (route.kind === "redirect" && route.destination) {
      if (!isSafeMigrationDestination(route.destination)) throw new Error(`Unsafe migration destination: ${route.destination}`);
      if (redirectSources.has(route.destination)) throw new Error(`Migration redirect loop: ${route.destination}`);
    }
  }
  for (const [destination, adapter] of Object.entries(DESTINATION_ADAPTERS)) {
    if (!isSafeMigrationDestination(destination) || !isSafeMigrationDestination(adapter)) throw new Error(`Unsafe destination adapter: ${destination}`);
  }
}

validateMigrationContract();
