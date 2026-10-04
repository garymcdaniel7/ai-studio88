/**
 * Next.js 16 proxy for session validation and legacy route migration.
 *
 * Protected migration is deliberately evaluated only after Supabase validates
 * the session. Local fallback still exposes the same route contract without
 * weakening configured-environment auth behavior.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
  isPlaywrightMockAuthEnabled,
  isKnownRoute,
  isPublicRoute,
  LEGACY_COOKIE_NAME,
  PLAYWRIGHT_AUTH_COOKIE,
  validateRedirectTarget,
} from "@/lib/auth-utils";
import {
  EDITOR_INTERSTITIAL_HTML,
  buildMigrationLocation,
  getDestinationAdapter,
  getMigrationRoute,
  getSunsetDate,
} from "@/lib/route-migration";
import { createMiddlewareClient, isSupabaseServerConfigured } from "@/lib/supabase-server";

function addDeprecationHeaders(response: NextResponse, days: number): NextResponse {
  response.headers.set("Deprecation", "true");
  response.headers.set("Sunset", getSunsetDate(days));
  response.headers.set("X-AI-Studio-Route-Migration", "phase-2");
  return response;
}

function copySetCookieHeader(source: NextResponse, destination: NextResponse): NextResponse {
  const setCookie = source.headers.get("set-cookie");
  if (setCookie) destination.headers.set("set-cookie", setCookie);
  return destination;
}

function isLoopbackRequest(request: NextRequest): boolean {
  return request.nextUrl.protocol === "http:" &&
    ["localhost", "127.0.0.1", "::1"].includes(request.nextUrl.hostname);
}

function isMockAuthenticatedRequest(request: NextRequest): boolean {
  return (
    process.env.NODE_ENV !== "production" &&
    process.env.PLAYWRIGHT_AUTH_MODE === "mock" &&
    isPlaywrightMockAuthEnabled() &&
    isLoopbackRequest(request) &&
    request.cookies.get(PLAYWRIGHT_AUTH_COOKIE)?.value === "authenticated"
  );
}

function getUnauthenticatedResponse(request: NextRequest): NextResponse {
  const loginUrl = new URL("/login", request.url);
  const safeRedirect = validateRedirectTarget(request.nextUrl.pathname);
  if (safeRedirect !== "/") loginUrl.searchParams.set("redirect", safeRedirect);
  return NextResponse.redirect(loginUrl);
}

function getMigrationResponse(request: NextRequest): NextResponse | null {
  const route = getMigrationRoute(request.nextUrl.pathname);
  if (!route || route.kind === "keep") return null;
  const days = route.deprecationDays ?? 90;
  if (route.kind === "interstitial") {
    return addDeprecationHeaders(new NextResponse(EDITOR_INTERSTITIAL_HTML, {
      status: 200,
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
    }), days);
  }
  const location = buildMigrationLocation(route.source, request.nextUrl);
  if (!location) return null;
  return addDeprecationHeaders(NextResponse.redirect(new URL(location, request.url), 301), days);
}

function getDestinationAdapterResponse(
  request: NextRequest,
  responseToPreserve: NextResponse | null,
): NextResponse | null {
  const adapter = getDestinationAdapter(request.nextUrl.pathname);
  if (!adapter) return null;
  const destination = new URL(adapter, request.url);
  destination.search = request.nextUrl.search;
  const response = NextResponse.rewrite(destination, { request: { headers: request.headers } });
  return responseToPreserve ? copySetCookieHeader(responseToPreserve, response) : response;
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;
  // Public routes still receive legacy-cookie cleanup; public access does not
  // make the old insecure cookie authoritative.
  if (isPublicRoute(pathname)) {
    const publicResponse = NextResponse.next();
    if (request.cookies.has(LEGACY_COOKIE_NAME)) publicResponse.cookies.delete(LEGACY_COOKIE_NAME);
    return publicResponse;
  }

  // Do not turn arbitrary paths into login redirects. Next.js owns 404
  // rendering for anything outside the explicit known-route inventory.
  if (!isKnownRoute(pathname)) {
    return NextResponse.next();
  }

  if (!isSupabaseServerConfigured) {
    if (process.env.PLAYWRIGHT_AUTH_MODE === "mock" && isPlaywrightMockAuthEnabled() && isLoopbackRequest(request)) {
      if (!isMockAuthenticatedRequest(request)) return getUnauthenticatedResponse(request);
      return getMigrationResponse(request) ?? getDestinationAdapterResponse(request, null) ?? NextResponse.next();
    }
    return getMigrationResponse(request) ?? getDestinationAdapterResponse(request, null) ?? NextResponse.next();
  }

  const response = NextResponse.next({ request: { headers: request.headers } });
  if (request.cookies.has(LEGACY_COOKIE_NAME)) response.cookies.delete(LEGACY_COOKIE_NAME);

  if (isMockAuthenticatedRequest(request)) {
    const migrationResponse = getMigrationResponse(request);
    if (migrationResponse) return copySetCookieHeader(response, migrationResponse);
    return getDestinationAdapterResponse(request, response) ?? response;
  }

  const supabase = createMiddlewareClient(request, response);
  if (!supabase) return response;

  const { data: { user }, error } = await supabase.auth.getUser();
  if (error || !user) {
    const loginUrl = new URL("/login", request.url);
    const safeRedirect = validateRedirectTarget(pathname);
    if (safeRedirect !== "/") loginUrl.searchParams.set("redirect", safeRedirect);
    const redirectResponse = NextResponse.redirect(loginUrl);
    if (request.cookies.has(LEGACY_COOKIE_NAME)) redirectResponse.cookies.delete(LEGACY_COOKIE_NAME);
    return redirectResponse;
  }

  const migrationResponse = getMigrationResponse(request);
  if (migrationResponse) return copySetCookieHeader(response, migrationResponse);
  return getDestinationAdapterResponse(request, response) ?? response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
