"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { Search, Bell, MessageSquare, Plus } from "lucide-react";

export function Topbar() {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<{type: string; name: string; id: string; url: string}[]>([]);
  const [showResults, setShowResults] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

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
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
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
        <Link href="/admin" className="relative p-2 text-gray-400 hover:text-gray-200 transition-colors">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-purple-600 text-[10px] font-bold text-white">
            3
          </span>
        </Link>
        <Link href="/brain" className="p-2 text-gray-400 hover:text-gray-200 transition-colors">
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
