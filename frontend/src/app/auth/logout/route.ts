/**
 * Logout Route Handler — POST /auth/logout
 *
 * Signs out the user from Supabase, clears all session cookies,
 * and redirects to the login page.
 *
 * This is a server-side route that properly invalidates the session
 * rather than just deleting client-side state.
 */

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { LEGACY_COOKIE_NAME } from "@/lib/auth-utils";

export async function POST() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

  if (!supabaseUrl || !supabaseAnonKey) {
    // Supabase not configured — just redirect
    return NextResponse.redirect(new URL("/login", process.env.NEXT_PUBLIC_API_URL || "http://localhost:3000"));
  }

  const cookieStore = await cookies();

  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value, options }) => {
          cookieStore.set(name, value, options);
        });
      },
    },
  });

  // Sign out from Supabase (invalidates refresh token server-side)
  await supabase.auth.signOut();

  // Clear legacy cookie if it exists
  cookieStore.delete(LEGACY_COOKIE_NAME);

  // Redirect to login
  return NextResponse.redirect(
    new URL("/login", process.env.NEXT_PUBLIC_API_URL || "http://localhost:3000")
  );
}

// Also support GET for simple link-based logout
export async function GET() {
  return POST();
}
