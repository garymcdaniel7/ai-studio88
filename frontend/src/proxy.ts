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
  EDITOR_INTERSTITIAL_HTML,
  buildMigrationLocation,
  getDestinationAdapter,
  getMigrationRoute,
  getSunsetDate,
} from "@/lib/route-migration";
import {
  createMiddlewareClient,
  isSupabaseServerConfigured,
} from "@/lib/supabase-server";

const EDITOR_INTERSTITIAL = EDITOR_INTERSTITIAL_HTML;

function addDeprecationHeaders(response: NextResponse, days: number): NextResponse {
  response.headers.set("Deprecation", "true");
  response.headers.set("Sunset", getSunsetDate(days));
  response.headers.set("X-AI-Studio-Route-Migration", "phase-1");
  return response;
}

function copySetCookieHeader(source: NextResponse, destination: NextResponse): NextResponse {
  const setCookie = source.headers.get("set-cookie");
  if (setCookie) destination.headers.set("set-cookie", setCookie);
  return destination;
}

function getMigrationResponse(request: NextRequest): NextResponse | null {
  const route = getMigrationRoute(request.nextUrl.pathname);
  if (!route || route.kind === "keep") return null;

  const days = route.deprecationDays ?? 90;
  if (route.kind === "interstitial") {
    return addDeprecationHeaders(
      new NextResponse(EDITOR_INTERSTITIAL, {
        status: 200,
        headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
      }),
      days,
    );
  }

  const location = buildMigrationLocation(route.source, request.nextUrl);
  if (!location) return null;
  const response = NextResponse.redirect(new URL(location, request.url), 301);
  return addDeprecationHeaders(response, days);
}

function getDestinationAdapterResponse(
  request: NextRequest,
  responseToPreserve: NextResponse | null,
): NextResponse | null {
  const adapter = getDestinationAdapter(request.nextUrl.pathname);
  if (!adapter) return null;

  const destination = new URL(adapter, request.url);
  destination.search = request.nextUrl.search;
  const response = NextResponse.rewrite(destination, {
    request: { headers: request.headers },
  });
  return responseToPreserve ? copySetCookieHeader(responseToPreserve, response) : response;
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Always allow public routes
  if (isPublicRoute(pathname)) {
    return NextResponse.next();
  }

  // In local/test fallback mode, preserve the existing no-Supabase behavior
  // while still making legacy URLs resolve to the Phase 1 destinations.
  // Production/staging auth is checked below before any protected migration.
  if (!isSupabaseServerConfigured) {
    return (
      getMigrationResponse(request) ??
      getDestinationAdapterResponse(request, null) ??
      NextResponse.next()
    );
  }

  // Create response early — proxy client needs it for cookie writes
  const response = NextResponse.next({
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

  // Session is valid — allow through, or perform the authenticated route
  // migration/adapter. The response already has refreshed cookies set by the
  // Supabase client, so preserve them on redirects and rewrites.
  const migrationResponse = getMigrationResponse(request);
  if (migrationResponse) return copySetCookieHeader(response, migrationResponse);

  return getDestinationAdapterResponse(request, response) ?? response;
}

export const config = {
  // Match all routes except static files, images, and favicon
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
