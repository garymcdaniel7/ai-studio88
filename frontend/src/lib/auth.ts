/**
 * Auth — OAuth and email/password authentication helpers.
 *
 * Provides typed wrappers around Supabase Auth for the unified login surface.
 * OAuth users do NOT need a separate AI Studio password (R1.10, R84.3).
 *
 * Usage:
 *   import { signInWithGoogle, signInWithEmail, signUpWithEmail } from "@/lib/auth";
 */

import { supabase, isSupabaseConfigured } from "@/lib/supabase";

// =============================================================================
// Types
// =============================================================================

export interface AuthResult {
  success: boolean;
  error?: string;
  /** For OAuth, the URL to redirect the user to */
  redirectUrl?: string;
}

// =============================================================================
// OAuth — Google
// =============================================================================

/**
 * Initiate Google OAuth sign-in via Supabase Auth.
 *
 * This handles both new signups and returning users:
 * - Existing identity → logs the user in
 * - New identity → creates user and triggers workspace provisioning (backend)
 *
 * OAuth users are NOT required to create a separate AI Studio password.
 *
 * @param redirectTo - Where to redirect after successful OAuth (defaults to "/")
 * @returns AuthResult with redirectUrl on success, or error message on failure
 *
 * Validates: R1.10, R84.1, R84.2, R84.3
 */
export async function signInWithGoogle(
  redirectTo?: string
): Promise<AuthResult> {
  if (!isSupabaseConfigured || !supabase) {
    return {
      success: false,
      error: "Supabase is not configured. Cannot authenticate.",
    };
  }

  // Build the callback URL for the OAuth redirect
  const callbackUrl = buildOAuthCallbackUrl(redirectTo);

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: callbackUrl,
      queryParams: {
        // Request offline access for refresh tokens
        access_type: "offline",
        // Always show the account chooser
        prompt: "select_account",
      },
    },
  });

  if (error) {
    return {
      success: false,
      error: error.message || "Failed to initiate Google sign-in",
    };
  }

  if (data.url) {
    return {
      success: true,
      redirectUrl: data.url,
    };
  }

  return {
    success: false,
    error: "No redirect URL returned from OAuth provider",
  };
}

// =============================================================================
// Email/Password — Sign In
// =============================================================================

/**
 * Sign in with email and password.
 *
 * @returns AuthResult indicating success or an error message
 */
export async function signInWithEmail(
  email: string,
  password: string
): Promise<AuthResult> {
  if (!isSupabaseConfigured || !supabase) {
    return {
      success: false,
      error: "Supabase is not configured. Cannot authenticate.",
    };
  }

  const { error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    return {
      success: false,
      error: error.message || "Invalid email or password",
    };
  }

  return { success: true };
}

// =============================================================================
// Email/Password — Sign Up
// =============================================================================

/**
 * Create a new account with email and password.
 *
 * After signup, the user may need to verify their email depending on
 * Supabase project settings. Workspace provisioning is triggered on
 * first authenticated API call (handled by backend per Task 2.2).
 *
 * @returns AuthResult indicating success or an error message
 */
export async function signUpWithEmail(
  email: string,
  password: string
): Promise<AuthResult> {
  if (!isSupabaseConfigured || !supabase) {
    return {
      success: false,
      error: "Supabase is not configured. Cannot authenticate.",
    };
  }

  const { error } = await supabase.auth.signUp({
    email,
    password,
  });

  if (error) {
    return {
      success: false,
      error: error.message || "Failed to create account",
    };
  }

  return { success: true };
}

// =============================================================================
// Utilities
// =============================================================================

/**
 * Build the OAuth callback URL.
 *
 * The callback route at /auth/callback will:
 * 1. Exchange the code for a session
 * 2. Redirect to the intended destination
 *
 * This ensures the OAuth flow triggers workspace provisioning if needed.
 */
function buildOAuthCallbackUrl(redirectTo?: string): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const callbackPath = "/auth/callback";

  // Encode the final redirect destination as a query param
  const params = new URLSearchParams();
  if (redirectTo && redirectTo !== "/") {
    params.set("next", redirectTo);
  }

  const queryString = params.toString();
  return `${origin}${callbackPath}${queryString ? `?${queryString}` : ""}`;
}
