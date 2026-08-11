"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { BrainDock } from "@/components/brain-dock";
import { ErrorBoundary } from "@/components/error-boundary";
import { OfflineBannerProvider } from "@/components/OfflineBanner";

/**
 * AppShell — Conditionally renders sidebar, topbar, and BrainDock.
 *
 * Hidden on auth pages (/login) where the user should see a clean full-screen UI.
 *
 * Architecture:
 * - OfflineBannerProvider: shows persistent banner + provides mutation-disabled context
 * - Page-level ErrorBoundary wraps {children} only, keeping sidebar/topbar navigable (R23.6)
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAuthPage = pathname === "/login" || pathname === "/signup";

  if (isAuthPage) {
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
