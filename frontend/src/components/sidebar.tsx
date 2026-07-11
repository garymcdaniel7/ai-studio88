"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrainChatPanel } from "@/components/brain-chat-panel";
import {
  Home,
  Brain,
  Pencil,
  Users,
  Image,
  Film,
  Send,
  BarChart3,
  Settings,
  Cpu,
  Clapperboard,
  GraduationCap,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navSections = [
  {
    label: null, // No label for top section
    items: [
      { name: "Home", href: "/", icon: Home },
      { name: "Brain", href: "/brain", icon: Brain },
    ],
  },
  {
    label: "Create",
    items: [
      { name: "Create", href: "/create", icon: Pencil },
      { name: "Editor", href: "/editor", icon: Clapperboard },
      { name: "Workflows", href: "/workflows", icon: Workflow },
      { name: "Training", href: "/training", icon: GraduationCap },
    ],
  },
  {
    label: "Manage",
    items: [
      { name: "Talent", href: "/talent", icon: Users },
      { name: "Assets", href: "/assets", icon: Image },
      { name: "Models", href: "/models", icon: Cpu },
    ],
  },
  {
    label: "Operate",
    items: [
      { name: "Production", href: "/production", icon: Film },
      { name: "Publish", href: "/publish", icon: Send },
      { name: "Analytics", href: "/analytics", icon: BarChart3 },
      { name: "Admin", href: "/admin", icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [showBrainChat, setShowBrainChat] = useState(false);

  return (
    <>
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-[200px] flex-col border-r border-white/[0.06] bg-[#0d0d20]">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-600">
          <Brain className="h-4 w-4 text-white" />
        </div>
        <span className="text-lg font-bold text-white">AI STUDIO</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
        {navSections.map((section, sIdx) => (
          <div key={sIdx}>
            {section.label && (
              <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-600">
                {section.label}
              </p>
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const isActive = pathname === item.href ||
                  (item.href !== "/" && pathname.startsWith(item.href));
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-purple-600/20 text-purple-400"
                        : "text-gray-400 hover:bg-white/[0.04] hover:text-gray-200"
                    )}
                  >
                    <item.icon className="h-4 w-4" />
                    {item.name}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* AI Brain Dock */}
      <div className="mx-3 mb-3 rounded-xl border border-white/[0.06] bg-[#12122a] p-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-purple-400">AI BRAIN</span>
          <span className="flex h-2 w-2 rounded-full bg-green-500" />
        </div>
        <p className="mt-1 text-xs text-gray-500">Ready to assist</p>
        <button
          onClick={() => setShowBrainChat(!showBrainChat)}
          className="mt-2 block w-full rounded-md bg-purple-600/20 px-3 py-1.5 text-center text-xs font-medium text-purple-400 hover:bg-purple-600/30 transition-colors"
        >
          {showBrainChat ? "Close Chat" : "Chat with Brain →"}
        </button>
      </div>

      {/* User */}
      <div className="border-t border-white/[0.06] p-3">
        <div className="flex items-center gap-2">
          <Link href="/settings" className="h-8 w-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 hover:ring-2 hover:ring-purple-500/50 transition-all" />
          <Link href="/settings" className="flex-1 min-w-0 hover:opacity-80 transition-opacity">
            <p className="text-sm font-medium text-white truncate">Gary</p>
            <p className="text-xs text-gray-500">Studio Owner</p>
          </Link>
          <Link href="/admin" title="Settings" className="p-1 text-gray-500 hover:text-gray-300">
            <Settings className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </aside>
    {showBrainChat && <BrainChatPanel onClose={() => setShowBrainChat(false)} />}
    </>
  );
}
