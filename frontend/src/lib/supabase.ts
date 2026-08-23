/**
 * Supabase Client — Safe browser client factory.
 *
 * Guards against empty/missing env vars during build, prerender, or SSG.
 * When configuration is absent, exports null and typed helpers that
 * return appropriate unavailable states instead of crashing.
 *
 * Usage:
 *   import { supabase, isSupabaseConfigured } from "@/lib/supabase";
 *   if (!isSupabaseConfigured) { // show unavailable UI }
 */

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

// =============================================================================
// Configuration Validation
// =============================================================================

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

/**
 * Whether Supabase is properly configured for this environment.
 * False during SSG/prerender if env vars are not injected, or if
 * values are empty/placeholder.
 */
export const isSupabaseConfigured: boolean = Boolean(
  supabaseUrl &&
    supabaseAnonKey &&
    supabaseUrl.startsWith("http") &&
    supabaseAnonKey.length > 10
);

// =============================================================================
// Client Factory
// =============================================================================

/**
 * The Supabase browser client instance, or null if not configured.
 *
 * Uses @supabase/ssr's createBrowserClient, which stores the session in an
 * httpOnly cookie instead of localStorage. This keeps the session in sync with
 * the server-side middleware/callback routes, so full page loads and deep links
 * (e.g. /create) stay authenticated instead of bouncing back to /login.
 *
 * Callers must check `isSupabaseConfigured` or null-check before use.
 */
export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createBrowserClient(supabaseUrl, supabaseAnonKey)
  : null;

// =============================================================================
// Auth Helpers (safe — return null when unconfigured)
// =============================================================================

/**
 * Get the current session's access token (for API calls).
 * Returns null if not authenticated or Supabase is not configured.
 */
export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token || null;
}

/**
 * Get the current user from the session.
 * Returns null if not authenticated or Supabase is not configured.
 */
export async function getCurrentUser() {
  if (!supabase) return null;
  const { data } = await supabase.auth.getUser();
  return data.user;
}

// =============================================================================
// Type exports for consumers
// =============================================================================

export type { SupabaseClient } from "@supabase/supabase-js";
