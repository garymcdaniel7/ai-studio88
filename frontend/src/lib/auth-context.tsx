"use client";

/**
 * AuthProvider — Single source of truth for frontend auth and workspace state.
 *
 * This is the ONE canonical context for authentication in the React tree.
 * All components that need user/session/workspace data consume this context
 * via the useAuth() hook.
 *
 * State machine:
 *   loading → authenticated | unauthenticated | expired | error | unconfigured
 *
 * Features:
 * - Subscribes to Supabase onAuthStateChange (handles refresh, multi-tab)
 * - Exposes current user, session, and access token via approved interface
 * - Provides logout() that clears state + signs out of Supabase
 * - Active workspace (org) context from membership resolution
 * - Never reads tokens directly from localStorage
 *
 * Usage:
 *   import { useAuth } from "@/lib/auth-context";
 *   const { user, status, logout, accessToken } = useAuth();
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";

// =============================================================================
// Types
// =============================================================================

export type AuthStatus =
  | "loading"          // Initial load, checking session
  | "authenticated"    // Valid session with active user
  | "unauthenticated"  // No session
  | "expired"          // Session existed but token refresh failed
  | "error"            // Unexpected error during auth resolution
  | "unconfigured";    // Supabase env vars not set

export interface Workspace {
  orgId: string;
  role: string;
  name?: string;
}

export interface AuthContextValue {
  /** Current authentication status */
  status: AuthStatus;

  /** The authenticated Supabase user, or null */
  user: User | null;

  /** The current Supabase session, or null */
  session: Session | null;

  /** The current access token (for API calls), or null */
  accessToken: string | null;

  /** The active workspace/org context, or null if not resolved */
  workspace: Workspace | null;

  /** Whether auth is still resolving (convenience for loading states) */
  isLoading: boolean;

  /** Whether the user is authenticated (convenience) */
  isAuthenticated: boolean;

  /** Sign out — clears session, redirects to login */
  logout: () => Promise<void>;

  /** Set the active workspace (for multi-workspace users) */
  setActiveWorkspace: (orgId: string) => void;
}

// =============================================================================
// Context
// =============================================================================

const AuthContext = createContext<AuthContextValue | null>(null);

// =============================================================================
// Provider
// =============================================================================

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(
    isSupabaseConfigured ? "loading" : "unconfigured"
  );
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);

  // Track initialization to avoid double-fire in StrictMode
  const initialized = useRef(false);

  // =========================================================================
  // Session initialization + subscription
  // =========================================================================

  useEffect(() => {
    if (!isSupabaseConfigured || !supabase) {
      setStatus("unconfigured");
      return;
    }

    // Prevent double initialization in React StrictMode
    if (initialized.current) return;
    initialized.current = true;

    // 1. Get initial session
    supabase.auth.getSession().then(({ data: { session: initialSession }, error }) => {
      if (error) {
        console.warn("[Auth] Failed to get initial session:", error.message);
        setStatus("error");
        return;
      }

      if (initialSession?.user) {
        setSession(initialSession);
        setUser(initialSession.user);
        setStatus("authenticated");
        resolveWorkspace(initialSession.user);
      } else {
        setStatus("unauthenticated");
      }
    });

    // 2. Subscribe to auth state changes (handles refresh, multi-tab, logout)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, newSession) => {
      switch (event) {
        case "SIGNED_IN":
        case "TOKEN_REFRESHED":
          setSession(newSession);
          setUser(newSession?.user ?? null);
          setStatus("authenticated");
          if (newSession?.user) {
            resolveWorkspace(newSession.user);
          }
          break;

        case "SIGNED_OUT":
          setSession(null);
          setUser(null);
          setWorkspace(null);
          setStatus("unauthenticated");
          break;

        case "USER_UPDATED":
          setUser(newSession?.user ?? null);
          setSession(newSession);
          break;

        default:
          // INITIAL_SESSION, PASSWORD_RECOVERY, etc.
          if (newSession?.user) {
            setSession(newSession);
            setUser(newSession.user);
            setStatus("authenticated");
          }
          break;
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // =========================================================================
  // Workspace resolution
  // =========================================================================

  function resolveWorkspace(authUser: User) {
    // Extract org_id from user metadata (set by backend during signup/invite)
    const appMetadata = authUser.app_metadata ?? {};
    const userMetadata = authUser.user_metadata ?? {};
    const orgId =
      appMetadata.org_id || userMetadata.org_id || null;

    if (orgId) {
      setWorkspace({
        orgId,
        role: appMetadata.role || "editor",
        name: appMetadata.org_name || userMetadata.org_name,
      });
    } else {
      // User has valid session but no workspace metadata yet.
      // This happens after first signup before backend provisioning completes.
      // Set a placeholder workspace using user ID — the backend will provision
      // the real org on first API call (Task 2.2 idempotent provisioning).
      setWorkspace({
        orgId: authUser.id,
        role: "owner",
        name: "My Workspace",
      });
    }
  }

  // =========================================================================
  // Actions
  // =========================================================================

  const logout = useCallback(async () => {
    if (!supabase) return;

    try {
      await supabase.auth.signOut();
    } catch (err) {
      console.warn("[Auth] Sign out error:", err);
    }

    // State is cleared by the onAuthStateChange SIGNED_OUT handler
    // Force navigation to login for immediate feedback
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }, []);

  const setActiveWorkspace = useCallback((orgId: string) => {
    setWorkspace((prev) => (prev ? { ...prev, orgId } : { orgId, role: "viewer" }));
  }, []);

  // =========================================================================
  // Derived values
  // =========================================================================

  const accessToken = session?.access_token ?? null;
  const isLoading = status === "loading";
  const isAuthenticated = status === "authenticated";

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      session,
      accessToken,
      workspace,
      isLoading,
      isAuthenticated,
      logout,
      setActiveWorkspace,
    }),
    [status, user, session, accessToken, workspace, isLoading, isAuthenticated, logout, setActiveWorkspace]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// =============================================================================
// Hook
// =============================================================================

/**
 * Access the auth context from any component.
 *
 * Must be used within an AuthProvider (included in Providers wrapper).
 * Throws if used outside the provider tree.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

/**
 * Get the current access token for use in API calls.
 *
 * This is the APPROVED way to get the token — never read from localStorage.
 * Returns null if not authenticated.
 */
export function useAccessToken(): string | null {
  const { accessToken } = useAuth();
  return accessToken;
}
