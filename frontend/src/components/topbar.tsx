"use client";

import Link from "next/link";
import { Search, Bell, MessageSquare, Plus } from "lucide-react";

export function Topbar() {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-white/[0.06] bg-[#0a0a1a]/80 px-6 backdrop-blur-xl">
      {/* Search */}
      <div className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 w-[360px]">
        <Search className="h-4 w-4 text-gray-500" />
        <input
          type="text"
          placeholder="Search projects, assets, tools..."
          className="flex-1 bg-transparent text-sm text-gray-300 placeholder:text-gray-600 outline-none"
        />
        <kbd className="rounded border border-white/[0.1] bg-white/[0.04] px-1.5 py-0.5 text-[10px] text-gray-500">
          ⌘K
        </kbd>
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
