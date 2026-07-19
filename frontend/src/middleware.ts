import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Next.js Middleware — Auth Gate
 *
 * Redirects unauthenticated users to /login.
 * Checks for Supabase session cookie/token in the request.
 *
 * Public routes (no auth required):
 * - /login
 * - /api/* (backend handles its own auth)
 * - /_next/* (static assets)
 * - /favicon.ico
 */

const PUBLIC_ROUTES = ["/login", "/api", "/_next", "/favicon.ico"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public routes
  if (PUBLIC_ROUTES.some((route) => pathname.startsWith(route))) {
    return NextResponse.next();
  }

  // Check for Supabase session token in cookies
  // Supabase stores auth in cookies named sb-<project-ref>-auth-token
  const cookies = request.cookies;
  const hasSupabaseSession = Array.from(cookies.getAll()).some(
    (cookie) =>
      cookie.name.startsWith("sb-") && cookie.name.endsWith("-auth-token")
  );

  // Also check localStorage-based session via a custom cookie we'll set on login
  const hasStudioSession = cookies.has("ai_studio_auth");

  if (!hasSupabaseSession && !hasStudioSession) {
    // Not authenticated — redirect to login
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Match all routes except static files and API
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api).*)",
  ],
};
