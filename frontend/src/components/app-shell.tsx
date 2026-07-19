"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { BrainDock } from "@/components/brain-dock";
import { ConnectionStatus } from "@/components/connection-status";

/**
 * AppShell — Conditionally renders sidebar, topbar, and BrainDock.
 * 
 * Hidden on auth pages (/login) where the user should see a clean full-screen UI.
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
    <>
      <ConnectionStatus />
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex-1 md:pl-[200px]">
          <Topbar />
          <main className="p-6">{children}</main>
        </div>
      </div>
      <BrainDock />
    </>
  );
}
