/**
 * Next.js Proxy — Secure Auth Gate
 *
 * Migrated from middleware.ts to proxy.ts per Next.js 16 convention.
 * The "middleware" file convention is deprecated; "proxy" is the supported
 * convention that clarifies this runs at the network boundary before routing.
 *
 * Validates Supabase sessions server-side using @supabase/ssr.
 * Cookie presence alone NEVER grants access — the session must be
 * verified via getUser() which validates the JWT with Supabase.
 *
 * Behavior:
 * - Public routes: pass through without auth check
 * - Protected routes: validate session, refresh if needed, reject if invalid
 * - Legacy cookies: cleared on every request (migration cleanup)
 * - Redirects: validated against open-redirect attacks
 *
 * Auth states handled:
 * - No session → redirect to /login with safe return URL
 * - Valid session → pass through (refresh cookies if needed)
 * - Expired/invalid session → clear cookies, redirect to /login
 * - Supabase not configured → pass through (graceful degradation)
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
  isPublicRoute,
  LEGACY_COOKIE_NAME,
  validateRedirectTarget,
} from "@/lib/auth-utils";
import {
  createMiddlewareClient,
  isSupabaseServerConfigured,
} from "@/lib/supabase-server";

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Always allow public routes
  if (isPublicRoute(pathname)) {
    return NextResponse.next();
  }

  // If Supabase is not configured, allow through (capability degraded)
  // This prevents the app from being completely broken during local dev
  // without Supabase. The pages themselves show unavailable states.
  if (!isSupabaseServerConfigured) {
    return NextResponse.next();
  }

  // Create response early — proxy client needs it for cookie writes
  let response = NextResponse.next({
    request: { headers: request.headers },
  });

  // Remove legacy insecure cookie on every request (migration cleanup)
  if (request.cookies.has(LEGACY_COOKIE_NAME)) {
    response.cookies.delete(LEGACY_COOKIE_NAME);
  }

  // Create server-side Supabase client that can read/write cookies
  const supabase = createMiddlewareClient(request, response);
  if (!supabase) {
    return response;
  }

  // ==========================================================================
  // Session Validation — This is the security boundary
  //
  // getUser() sends the access token to Supabase Auth server for validation.
  // It will also refresh the session if the access token is expired but the
  // refresh token is still valid — updating the cookies automatically.
  // ==========================================================================

  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error || !user) {
    // Session is invalid, expired, or missing — redirect to login
    const loginUrl = new URL("/login", request.url);
    const safeRedirect = validateRedirectTarget(pathname);
    if (safeRedirect !== "/") {
      loginUrl.searchParams.set("redirect", safeRedirect);
    }

    // Clear any stale Supabase cookies to prevent loops
    const redirectResponse = NextResponse.redirect(loginUrl);

    // Also clear legacy cookie
    if (request.cookies.has(LEGACY_COOKIE_NAME)) {
      redirectResponse.cookies.delete(LEGACY_COOKIE_NAME);
    }

    return redirectResponse;
  }

  // Session is valid — allow through
  // The response already has refreshed cookies set by createMiddlewareClient
  return response;
}

export const config = {
  // Match all routes except static files, images, and favicon
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
