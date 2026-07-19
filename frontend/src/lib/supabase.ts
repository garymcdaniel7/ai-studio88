/**
 * Supabase Client — Browser client for authentication.
 *
 * Uses @supabase/supabase-js for client-side auth (login, signup, session).
 * The backend validates JWTs independently using the JWT secret.
 */

import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn(
    "[Auth] NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY not set. Auth will not work."
  );
}

export const supabase = createClient(supabaseUrl || "", supabaseAnonKey || "", {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

/**
 * Get the current session's access token (for API calls).
 * Returns null if not authenticated.
 */
export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token || null;
}

/**
 * Get the current user from the session.
 */
export async function getCurrentUser() {
  const { data } = await supabase.auth.getUser();
  return data.user;
}
