"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, Bell, MessageSquare, X, AlertTriangle, CheckCircle, Menu, Brain } from "lucide-react";
import { getVisibleFlatItems, isNavItemActive, type UserRole } from "@/lib/navigation";

interface Alert {
  severity: string;
  service: string;
  message: string;
}

export function Topbar() {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<{type: string; name: string; id: string; url: string}[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [showAlerts, setShowAlerts] = useState(false);
  const [alertCount, setAlertCount] = useState(0);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  useEffect(() => {
    if (!searchQuery.trim() || searchQuery.length < 2) {
      setSearchResults([]);
      setShowResults(false);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/v1/search?q=${encodeURIComponent(searchQuery)}`);
        if (resp.ok) {
          const data = await resp.json();
          setSearchResults(data.results || []);
          setShowResults(true);
        }
      } catch {
        setSearchResults([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Close on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setShowResults(false);
      if (alertRef.current && !alertRef.current.contains(e.target as Node)) setShowAlerts(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Poll alerts from Ise every 60 seconds
  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const resp = await fetch(`${API_BASE}/aios/v1/health/alerts`);
        if (resp.ok) {
          const data = await resp.json();
          setAlerts(data.alerts || []);
          setAlertCount(data.count || 0);
        }
      } catch {}
    };
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border-subtle bg-surface-base/80 px-4 md:px-6 backdrop-blur-xl">
      {/* Mobile Menu Button */}
      <button
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        className="md:hidden p-2 rounded-lg text-content-tertiary hover:text-content-primary hover:bg-surface-hover"
      >
        {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </button>

      {/* Search — hidden on mobile, shown on md+ */}
      <div ref={searchRef} className="relative hidden md:block w-[360px]">
        <div className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-hover px-3 py-2">
          <Search className="h-4 w-4 text-content-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search projects, assets, talent, models..."
            className="flex-1 bg-transparent text-sm text-content-secondary placeholder:text-content-muted outline-none"
          />
          <kbd className="rounded border border-border-strong bg-surface-hover px-1.5 py-0.5 text-[10px] text-content-muted">
            ⌘K
          </kbd>
        </div>
        {/* Search Results Dropdown */}
        {showResults && searchResults.length > 0 && (
          <div className="absolute top-full left-0 right-0 mt-1 rounded-xl border border-border-strong bg-surface-raised shadow-2xl max-h-80 overflow-y-auto z-50">
            {searchResults.map((r, i) => (
              <a
                key={i}
                href={r.url}
                onClick={() => { setShowResults(false); setSearchQuery(""); }}
                className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-hover border-b border-border-subtle last:border-0"
              >
                <span className="text-[10px] font-medium text-status-info bg-status-info-muted px-1.5 py-0.5 rounded uppercase">{r.type}</span>
                <span className="text-sm text-content-secondary truncate">{r.name}</span>
              </a>
            ))}
          </div>
        )}
        {showResults && searchResults.length === 0 && searchQuery.length >= 2 && (
          <div className="absolute top-full left-0 right-0 mt-1 rounded-xl border border-border-strong bg-surface-raised shadow-2xl p-4 z-50">
            <p className="text-xs text-content-muted text-center">No results for &ldquo;{searchQuery}&rdquo;</p>
          </div>
        )}
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        {/* Alert Bell */}
        <div ref={alertRef} className="relative">
          <button
            onClick={() => setShowAlerts(!showAlerts)}
            aria-label="Notifications"
            className="relative p-2 text-content-tertiary hover:text-content-secondary transition-colors"
          >
            <Bell className="h-5 w-5" />
            {alertCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-status-error text-[9px] font-bold text-content-inverse">
                {alertCount > 9 ? "9+" : alertCount}
              </span>
            )}
          </button>

          {/* Alert Dropdown */}
          {showAlerts && (
            <div className="absolute right-0 top-full mt-2 w-96 rounded-xl border border-border-strong bg-surface-raised shadow-2xl z-50">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
                <p className="text-sm font-semibold text-content-primary">System Alerts</p>
                <button onClick={() => setShowAlerts(false)} className="text-content-muted hover:text-content-primary">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="max-h-96 overflow-y-auto">
                {alerts.length === 0 ? (
                  <div className="flex items-center gap-2 px-4 py-3">
                    <CheckCircle className="h-4 w-4 text-status-success" />
                    <p className="text-sm text-status-success">All systems healthy</p>
                  </div>
                ) : (
                  alerts.map((alert, i) => (
                    <div key={i} className="px-4 py-3 border-b border-border-subtle last:border-0 hover:bg-surface-hover">
                      <div className="flex items-start gap-2">
                        <AlertTriangle className={`h-4 w-4 mt-0.5 shrink-0 ${alert.severity === "critical" ? "text-status-error" : "text-status-warning"}`} />
                        <div>
                          <p className="text-xs font-medium text-content-primary capitalize">{alert.service}</p>
                          <p className="text-[11px] text-content-tertiary mt-0.5">{alert.message}</p>
                          <Link
                            href="/admin/ise"
                            onClick={() => setShowAlerts(false)}
                            className="text-[10px] text-status-info hover:text-interactive-default mt-1 block"
                          >
                            Diagnose & Fix →
                          </Link>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
              <div className="px-4 py-2 border-t border-border-subtle">
                <Link href="/admin/ise" onClick={() => setShowAlerts(false)} className="text-xs text-content-muted hover:text-content-secondary">
                  View full diagnostics →
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>

    {/* Mobile Navigation Drawer */}
    {mobileMenuOpen && (
      <div className="fixed inset-0 z-50 md:hidden">
        <div className="absolute inset-0 bg-black/60" onClick={() => setMobileMenuOpen(false)} />
        <nav className="absolute left-0 top-0 h-full w-64 bg-surface-sunken border-r border-border-subtle p-4 space-y-1 overflow-y-auto" aria-label="Mobile navigation">
          <div className="flex items-center gap-2 mb-6 px-2">
            <div className="h-8 w-8 rounded-lg bg-interactive-default flex items-center justify-center">
              <Brain className="h-4 w-4 text-interactive-foreground" />
            </div>
            <span className="text-lg font-bold text-content-primary">AI STUDIO</span>
          </div>
          {getVisibleFlatItems("owner" as UserRole).map((item) => (
            <Link
              key={item.key}
              href={item.href}
              onClick={() => setMobileMenuOpen(false)}
              aria-current={isNavItemActive(item, pathname) ? "page" : undefined}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                isNavItemActive(item, pathname) ? "bg-interactive-muted text-status-info" : "text-content-tertiary hover:text-content-primary hover:bg-surface-hover"
              }`}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    )}
    </>
  );
}
