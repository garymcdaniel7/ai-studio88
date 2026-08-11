"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { BrainDock } from "@/components/brain-dock";
import { ErrorBoundary } from "@/components/error-boundary";
import { useAuth } from "@/lib/auth-context";
import { OfflineBannerProvider } from "@/components/OfflineBanner";
import { Loader2 } from "lucide-react";

/**
 * AppShell — Conditionally renders sidebar, topbar, and BrainDock.
 *
 * Hidden on auth pages (/login) where the user should see a clean full-screen UI.
 * Shows a loading spinner while auth status is resolving to prevent flash of
 * wrong content (landing page flash before session resolves).
 *
 * Architecture:
 * - OfflineBannerProvider: shows persistent banner + provides mutation-disabled context
 * - Page-level ErrorBoundary wraps {children} only, keeping sidebar/topbar navigable (R23.6)
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { status } = useAuth();
  const isAuthPage = pathname === "/login" || pathname === "/signup";
  const isLoading = status === "loading";
  const isUnauthenticatedHome = pathname === "/" && status === "unauthenticated";

  // While auth is resolving, show a loading state — never flash wrong content
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#0a0a1a]">
        <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
      </div>
    );
  }

  if (isAuthPage || isUnauthenticatedHome) {
    return (
      <div className="min-h-screen">
        {children}
      </div>
    );
  }

  return (
    <OfflineBannerProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex-1 md:pl-[200px]">
          <Topbar />
          <main className="p-6">
            <ErrorBoundary pageLevel>
              {children}
            </ErrorBoundary>
          </main>
        </div>
      </div>
      <BrainDock />
    </OfflineBannerProvider>
  );
}
