/**
 * Auth Utilities — Safe redirects, session state, and auth constants.
 *
 * Centralizes auth-related logic used by middleware, login, and logout.
 */

// =============================================================================
// Public Routes (no auth required)
// =============================================================================

/**
 * Routes that don't require authentication.
 * Prefix-matched: "/api" matches "/api/anything".
 */
export const PUBLIC_ROUTE_PREFIXES = [
  "/login",
  "/auth",
  "/api",
  "/_next",
  "/favicon.ico",
  // Public landing-page showcase images (served from public/showcase/)
  // Must be reachable without auth so unauthenticated visitors see the
  // "whoa" hero + cast + sample work on the landing page.
  "/showcase",
] as const;

/**
 * Exact paths that are public (not prefix-matched).
 */
export const PUBLIC_EXACT_PATHS = [
  "/",
  // Legal pages — must be publicly reachable for OAuth verification and
  // compliance (Google crawls these without an authenticated session).
  "/privacy",
  "/terms",
] as const;

/**
 * Check if a pathname is a public route.
 */
export function isPublicRoute(pathname: string): boolean {
  if (PUBLIC_EXACT_PATHS.includes(pathname as typeof PUBLIC_EXACT_PATHS[number])) {
    return true;
  }
  return PUBLIC_ROUTE_PREFIXES.some((prefix) => pathname.startsWith(prefix));
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
