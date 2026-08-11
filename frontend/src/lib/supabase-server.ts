/**
 * Supabase Server Client — For middleware and server components.
 *
 * Uses @supabase/ssr to manage cookies properly. This client validates
 * sessions server-side and handles token refresh via secure httpOnly cookies.
 *
 * NEVER import this in client components — use @/lib/supabase instead.
 */

import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

/**
 * Whether Supabase SSR is properly configured.
 */
export const isSupabaseServerConfigured: boolean = Boolean(
  supabaseUrl &&
    supabaseAnonKey &&
    supabaseUrl.startsWith("http") &&
    supabaseAnonKey.length > 10
);

/**
 * Create a Supabase client for use in Next.js middleware.
 *
 * This client reads/writes cookies from the request/response pair,
 * enabling proper session validation and token refresh.
 */
export function createMiddlewareClient(
  request: NextRequest,
  response: NextResponse
) {
  if (!isSupabaseServerConfigured) {
    return null;
  }

  return createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        // Set cookies on the request (for downstream middleware/pages)
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value)
        );
        // Set cookies on the response (sent to the browser)
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options)
        );
      },
    },
  });
}
