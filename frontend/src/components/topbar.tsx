"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { Search, Bell, MessageSquare, Plus, X, AlertTriangle, CheckCircle } from "lucide-react";

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
  const searchRef = useRef<HTMLDivElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);

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
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-white/[0.06] bg-[#0a0a1a]/80 px-6 backdrop-blur-xl">
      {/* Search */}
      <div ref={searchRef} className="relative w-[360px]">
        <div className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2">
          <Search className="h-4 w-4 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search projects, assets, talent, models..."
            className="flex-1 bg-transparent text-sm text-gray-300 placeholder:text-gray-600 outline-none"
          />
          <kbd className="rounded border border-white/[0.1] bg-white/[0.04] px-1.5 py-0.5 text-[10px] text-gray-500">
            ⌘K
          </kbd>
        </div>
        {/* Search Results Dropdown */}
        {showResults && searchResults.length > 0 && (
          <div className="absolute top-full left-0 right-0 mt-1 rounded-xl border border-white/[0.1] bg-[#12122a] shadow-2xl max-h-80 overflow-y-auto z-50">
            {searchResults.map((r, i) => (
              <a
                key={i}
                href={r.url}
                onClick={() => { setShowResults(false); setSearchQuery(""); }}
                className="flex items-center gap-3 px-4 py-2.5 hover:bg-white/[0.04] border-b border-white/[0.04] last:border-0"
              >
                <span className="text-[10px] font-medium text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded uppercase">{r.type}</span>
                <span className="text-sm text-gray-200 truncate">{r.name}</span>
              </a>
            ))}
          </div>
        )}
        {showResults && searchResults.length === 0 && searchQuery.length >= 2 && (
          <div className="absolute top-full left-0 right-0 mt-1 rounded-xl border border-white/[0.1] bg-[#12122a] shadow-2xl p-4 z-50">
            <p className="text-xs text-gray-500 text-center">No results for &ldquo;{searchQuery}&rdquo;</p>
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
            className="relative p-2 text-gray-400 hover:text-gray-200 transition-colors"
          >
            <Bell className="h-5 w-5" />
            {alertCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
                {alertCount > 9 ? "9+" : alertCount}
              </span>
            )}
          </button>

          {/* Alert Dropdown */}
          {showAlerts && (
            <div className="absolute right-0 top-full mt-2 w-96 rounded-xl border border-white/[0.1] bg-[#12122a] shadow-2xl z-50">
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
                <p className="text-sm font-semibold text-white">System Alerts</p>
                <button onClick={() => setShowAlerts(false)} className="text-gray-500 hover:text-white">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="max-h-96 overflow-y-auto">
                {alerts.length === 0 ? (
                  <div className="flex items-center gap-2 px-4 py-3">
                    <CheckCircle className="h-4 w-4 text-green-400" />
                    <p className="text-sm text-green-400">All systems healthy</p>
                  </div>
                ) : (
                  alerts.map((alert, i) => (
                    <div key={i} className="px-4 py-3 border-b border-white/[0.04] last:border-0 hover:bg-white/[0.03]">
                      <div className="flex items-start gap-2">
                        <AlertTriangle className={`h-4 w-4 mt-0.5 shrink-0 ${alert.severity === "critical" ? "text-red-400" : "text-amber-400"}`} />
                        <div>
                          <p className="text-xs font-medium text-white capitalize">{alert.service}</p>
                          <p className="text-[11px] text-gray-400 mt-0.5">{alert.message}</p>
                          <Link
                            href="/admin/ise"
                            onClick={() => setShowAlerts(false)}
                            className="text-[10px] text-purple-400 hover:text-purple-300 mt-1 block"
                          >
                            Diagnose & Fix →
                          </Link>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
              <div className="px-4 py-2 border-t border-white/[0.06]">
                <Link href="/admin/ise" onClick={() => setShowAlerts(false)} className="text-xs text-gray-500 hover:text-gray-300">
                  View full diagnostics →
                </Link>
              </div>
            </div>
          )}
        </div>
        <Link href="/brain" aria-label="Chat with AI Brain" className="p-2 text-gray-400 hover:text-gray-200 transition-colors">
          <MessageSquare className="h-5 w-5" />
        </Link>
        <Link href="/create" className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 transition-colors">
          Quick Create
          <Plus className="h-4 w-4" />
        </Link>
      </div>
    </header>
  );
}
