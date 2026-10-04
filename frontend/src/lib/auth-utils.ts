/**
 * Auth Utilities — Safe redirects, session state, and auth constants.
 *
 * Centralizes auth-related logic used by middleware, login, and logout.
 */

// =============================================================================
// Public Routes (no auth required)
// =============================================================================

/**
 * Routes that don't require authentication. Prefixes are matched on a path
 * boundary so near-matches such as `/apiary` cannot accidentally become public.
 */
export const PUBLIC_ROUTE_PREFIXES = [
  "/login",
  "/auth",
  "/api",
  "/_next",
  "/showcase",
] as const;

/** Static files that Next serves without the auth boundary. */
export const PUBLIC_EXACT_PATHS = [
  "/",
  "/pricing",
  "/favicon.ico",
] as const;

/** Explicit protected route families and migration destinations. */
export const KNOWN_PROTECTED_PATHS = [
  "/admin",
  "/admin/connections",
  "/admin/fleet",
  "/admin/health",
  "/admin/ise",
  "/admin/keys",
  "/admin/knowledge",
  "/admin/objects",
  "/analytics",
  "/assets",
  "/brain",
  "/create",
  "/editor",
  "/make",
  "/models",
  "/production",
  "/projects",
  "/publish",
  "/settings",
  "/story",
  "/talent",
  "/training",
  "/workflows",
  "/write",
  "/start",
  "/cast",
  "/home",
  "/generate",
  "/video",
  "/audio",
  "/jobs",
  "/campaigns",
  "/calendar",
  "/brands",
  "/teams",
  "/company",
] as const;

function matchesPathPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/** Check if a pathname is a public route. */
export function isPublicRoute(pathname: string): boolean {
  const pathOnly = pathname.split("?", 1)[0].split("#", 1)[0];
  if (PUBLIC_EXACT_PATHS.includes(pathOnly as typeof PUBLIC_EXACT_PATHS[number])) {
    return true;
  }
  return PUBLIC_ROUTE_PREFIXES.some((prefix) => matchesPathPrefix(pathOnly, prefix));
}

/**
 * Check whether a non-public pathname maps to a known protected route.
 * Unknown paths deliberately return false so Next.js can render its 404 page
 * instead of turning an arbitrary typo into an authentication redirect.
 */
export function isKnownRoute(pathname: string): boolean {
  if (isPublicRoute(pathname)) return true;
  if (KNOWN_PROTECTED_PATHS.includes(pathname as typeof KNOWN_PROTECTED_PATHS[number])) {
    return true;
  }
  return /^\/projects\/[^/]+$/.test(pathname);
}

// =============================================================================
// Safe Redirect Validation
// =============================================================================

/**
 * Validate a redirect target to prevent open-redirect attacks.
 *
 * Rules:
 * - Must be a relative path starting with "/"
 * - Must not contain protocol ("//", "http:", "javascript:")
 * - Must not redirect to login (infinite loop)
 * - Returns "/" if invalid
 */
export function validateRedirectTarget(target: string | null | undefined): string {
  if (!target) return "/";

  const trimmed = target.trim();

  // Must start with single "/"
  if (!trimmed.startsWith("/")) return "/";

  // Reject protocol-relative URLs ("//evil.com")
  if (trimmed.startsWith("//")) return "/";

  // Reject any URL with a protocol
  if (/^[a-z]+:/i.test(trimmed)) return "/";

  // Reject encoded slashes that could bypass the check
  if (trimmed.includes("%2f") || trimmed.includes("%2F")) return "/";

  // Reject backslashes (IE compatibility attack vector)
  if (trimmed.includes("\\")) return "/";

  // Don't redirect back to login (infinite loop)
  if (trimmed.startsWith("/login")) return "/";

  // Don't redirect to auth callback (internal)
  if (trimmed.startsWith("/auth")) return "/";

  return trimmed;
}

// =============================================================================
// Auth States
// =============================================================================

export type AuthState =
  | "unauthenticated"     // No session at all
  | "authenticated"       // Valid session with active user
  | "expired"             // Session existed but could not be refreshed
  | "unconfigured";       // Supabase not configured for this environment

// =============================================================================
// Legacy Cookie Cleanup
// =============================================================================

/**
 * Cookie name used by the old insecure auth implementation.
 * Must be removed during migration.
 */
export const LEGACY_COOKIE_NAME = "ai_studio_auth";

// =============================================================================
// Production Bypass Guard
// =============================================================================

/**
 * Whether dev bypass is allowed in this environment.
 * NEVER true in production — controlled by build-time NODE_ENV.
 */
export const isDevBypassAllowed: boolean =
  process.env.NODE_ENV === "development";

/** Cookie used only by the explicit loopback Playwright mock-auth seam. */
export const PLAYWRIGHT_AUTH_COOKIE = "ai_studio_playwright_session";

/**
 * Return whether the test-only mock auth mode is explicitly enabled.
 *
 * The public variable is provided by the local Playwright web server so client
 * components can mirror the server-side seam without reading dotenv files.
 */
export function isPlaywrightMockAuthEnabled(): boolean {
  return (
    process.env.PLAYWRIGHT_AUTH_MODE === "mock" ||
    process.env.NEXT_PUBLIC_PLAYWRIGHT_AUTH_MODE === "mock"
  );
}
