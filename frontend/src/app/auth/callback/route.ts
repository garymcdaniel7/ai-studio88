/**
 * OAuth Callback Route — GET /auth/callback
 *
 * Handles the redirect from Supabase OAuth providers (Google, etc.).
 * Exchanges the authorization code for a session and redirects to the
 * intended destination.
 *
 * This route is called by Supabase after the user completes OAuth consent.
 * The session is established via cookie, and workspace provisioning is
 * triggered on the next authenticated API call (backend handles this per R1.6).
 *
 * OAuth users do NOT need a separate AI Studio password (R1.10, R84.3).
 *
 * Validates: R84.1, R84.2, R84.3
 */

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { validateRedirectTarget } from "@/lib/auth-utils";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next");

  // Validate the redirect target to prevent open-redirect attacks
  const redirectTo = validateRedirectTarget(next);

  // Determine the origin for redirect
  const origin = request.nextUrl.origin;

  if (!code) {
    // No code means the OAuth flow was cancelled or errored
    const errorDescription = searchParams.get("error_description") || "Authentication cancelled";
    const loginUrl = new URL("/login", origin);
    loginUrl.searchParams.set("error", errorDescription);
    return NextResponse.redirect(loginUrl);
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

  if (!supabaseUrl || !supabaseAnonKey) {
    // Supabase not configured — redirect to login with error
    const loginUrl = new URL("/login", origin);
    loginUrl.searchParams.set("error", "Authentication service not configured");
    return NextResponse.redirect(loginUrl);
  }

  const cookieStore = await cookies();

  // Declare the response we will return. Because @supabase/ssr can only write
  // cookies to the response that is actually returned, we build it BEFORE
  // exchanging the code and write the session cookies onto it inside setAll.
  const response = NextResponse.redirect(new URL(redirectTo, origin));

  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value, options }) => {
          cookieStore.set(name, value, options);
          // Attach the session cookie to the response that reaches the browser.
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  // Exchange the authorization code for a session
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    console.error("[Auth Callback] Code exchange failed:", error.message);
    const loginUrl = new URL("/login", origin);
    loginUrl.searchParams.set("error", "Authentication failed. Please try again.");
    return NextResponse.redirect(loginUrl);
  }

  // Success — the session cookies were written to `response` during the
  // exchange, so the browser receives them and stays logged in.
  return response;
}
