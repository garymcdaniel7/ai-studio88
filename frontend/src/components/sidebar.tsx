"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Brain } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import { getVisibleSections, isNavItemActive, type UserRole } from "@/lib/navigation";

/**
 * Desktop Sidebar — consumes the canonical navigation configuration.
 * Same destinations as mobile drawer (Story 115).
 */
export function Sidebar() {
  const pathname = usePathname();

  // Derive the role from the authenticated user's workspace role so that
  // non-admin users don't see Admin/developer-only navigation. Falls back to
  // "viewer" when there's no workspace yet (least-privilege default).
  const { workspace } = useAuth();
  const userRole: UserRole = (workspace?.role as UserRole) || "viewer";
  const sections = getVisibleSections(userRole);

  return (
    <aside className="fixed left-0 top-0 z-40 hidden md:flex h-screen w-[200px] flex-col border-r border-border-subtle bg-surface-sunken">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-interactive-default">
          <Brain className="h-4 w-4 text-interactive-foreground" />
        </div>
        <span className="text-lg font-bold text-content-primary">AI STUDIO</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-4" aria-label="Main navigation">
        {sections.map((section, sIdx) => (
          <div key={sIdx} role="group" aria-label={section.label || "Primary"}>
            {section.label && (
              <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-content-muted">
                {section.label}
              </p>
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const isActive = isNavItemActive(item, pathname);
                return (
                  <Link
                    key={item.key}
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-interactive-muted text-status-info"
                        : "text-content-tertiary hover:bg-surface-hover hover:text-content-secondary"
                    )}
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* AI Brain Dock */}
      <div className="mx-3 mb-3 rounded-xl border border-border-subtle bg-surface-raised p-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-status-info">AI BRAIN</span>
          <span className="flex h-2 w-2 rounded-full bg-status-info animate-pulse" />
        </div>
        <p className="mt-1 text-xs text-content-muted">Ask anything</p>
        <Link
          href="/brain"
          className="mt-2 block w-full rounded-md bg-interactive-muted px-3 py-1.5 text-center text-xs font-medium text-status-info hover:bg-interactive-muted/80 transition-colors"
        >
          Open Brain →
        </Link>
      </div>

      {/* User */}
      <div className="border-t border-border-subtle p-3">
        <div className="flex items-center gap-2">
          <Link href="/settings" aria-label="User profile" className="h-8 w-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 hover:ring-2 hover:ring-focus-ring/50 transition-all" />
          <Link href="/settings" className="flex-1 min-w-0 hover:opacity-80 transition-opacity">
            <p className="text-sm font-medium text-content-primary truncate">My Account</p>
            <p className="text-xs text-content-muted">Studio</p>
          </Link>
        </div>
      </div>
    </aside>
  );
}
