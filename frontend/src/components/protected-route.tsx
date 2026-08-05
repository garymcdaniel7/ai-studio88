"use client";

/**
 * ProtectedRoute — Client-side auth gate for page content.
 *
 * This is a defense-in-depth layer on top of the server-side middleware.
 * While middleware prevents unauthenticated navigation, ProtectedRoute
 * ensures page content doesn't flash before the client-side auth state
 * resolves (e.g., on slow hydration or middleware bypass in dev mode).
 *
 * Usage in a page:
 *   import { ProtectedRoute } from "@/components/protected-route";
 *
 *   export default function DashboardPage() {
 *     return (
 *       <ProtectedRoute>
 *         <DashboardContent />
 *       </ProtectedRoute>
 *     );
 *   }
 *
 * Or wrap in app-shell for all protected pages automatically.
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

interface ProtectedRouteProps {
  children: React.ReactNode;
  /** Require a specific role (optional) */
  requiredRole?: "owner" | "admin" | "editor" | "viewer";
  /** Custom fallback while loading (default: spinner) */
  loadingFallback?: React.ReactNode;
}

export function ProtectedRoute({
  children,
  requiredRole,
  loadingFallback,
}: ProtectedRouteProps) {
  const { status, isAuthenticated, workspace } = useAuth();
  const router = useRouter();

  useEffect(() => {
    // Only redirect after auth has resolved (not during loading)
    if (status === "unauthenticated" || status === "expired") {
      const returnUrl = typeof window !== "undefined" ? window.location.pathname : "/";
      router.push(`/login?redirect=${encodeURIComponent(returnUrl)}`);
    }
  }, [status, router]);

  // Loading state — don't render protected content yet
  if (status === "loading") {
    return (
      loadingFallback ?? (
        <div className="flex items-center justify-center min-h-[200px]">
          <Loader2 className="h-6 w-6 animate-spin text-purple-500" />
        </div>
      )
    );
  }

  // Unconfigured Supabase — show content anyway (dev mode graceful degradation)
  if (status === "unconfigured") {
    return <>{children}</>;
  }

  // Not authenticated — show nothing (redirect in progress)
  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <Loader2 className="h-6 w-6 animate-spin text-purple-500" />
      </div>
    );
  }

  // Role check (if required)
  if (requiredRole && workspace) {
    const roleHierarchy = ["viewer", "editor", "admin", "owner"];
    const userLevel = roleHierarchy.indexOf(workspace.role);
    const requiredLevel = roleHierarchy.indexOf(requiredRole);

    if (userLevel < requiredLevel) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[200px] gap-2">
          <p className="text-sm text-gray-400">
            You need <span className="font-medium text-white">{requiredRole}</span> access for this page.
          </p>
          <p className="text-xs text-gray-600">
            Contact your workspace administrator.
          </p>
        </div>
      );
    }
  }

  // Authenticated and authorized — render content
  return <>{children}</>;
}
