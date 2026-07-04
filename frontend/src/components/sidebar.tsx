"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Brain,
  Pencil,
  Users,
  Image,
  BookOpen,
  Film,
  Send,
  BarChart3,
  Settings,
  Bell,
  HelpCircle,
  Cpu,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { name: "Home", href: "/", icon: Home },
  { name: "Brain", href: "/brain", icon: Brain },
  { name: "Create", href: "/create", icon: Pencil },
  { name: "Talent", href: "/talent", icon: Users },
  { name: "Assets", href: "/assets", icon: Image },
  { name: "Story", href: "/story", icon: BookOpen },
  { name: "Production", href: "/production", icon: Film },
  { name: "Publish", href: "/publish", icon: Send },
  { name: "Models", href: "/models", icon: Cpu },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
  { name: "Admin", href: "/admin", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-[200px] flex-col border-r border-white/[0.06] bg-[#0d0d20]">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-600">
          <Brain className="h-4 w-4 text-white" />
        </div>
        <span className="text-lg font-bold text-white">AI STUDIO</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const isActive = pathname === item.href || 
            (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "bg-purple-600/20 text-purple-400"
                  : "text-gray-400 hover:bg-white/[0.04] hover:text-gray-200"
              )}
            >
              <item.icon className="h-4.5 w-4.5" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* AI Brain Dock */}
      <div className="mx-3 mb-3 rounded-xl border border-white/[0.06] bg-[#12122a] p-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-purple-400">AI BRAIN</span>
          <span className="flex h-2 w-2 rounded-full bg-green-500" />
        </div>
        <p className="mt-1 text-xs text-gray-500">Ready to assist</p>
        <Link
          href="/brain"
          className="mt-2 block rounded-md bg-purple-600/20 px-3 py-1.5 text-center text-xs font-medium text-purple-400 hover:bg-purple-600/30 transition-colors"
        >
          Chat with Brain →
        </Link>
      </div>

      {/* User */}
      <div className="border-t border-white/[0.06] p-3">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-500" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">Gary</p>
            <p className="text-xs text-gray-500">Studio Owner</p>
          </div>
        </div>
      </div>

      {/* Bottom icons */}
      <div className="flex items-center justify-around border-t border-white/[0.06] px-3 py-2">
        <Link href="/brain" title="AI Brain" className="p-1.5 text-gray-500 hover:text-gray-300">
          <Brain className="h-4 w-4" />
        </Link>
        <Link href="/admin" title="Notifications" className="p-1.5 text-gray-500 hover:text-gray-300">
          <Bell className="h-4 w-4" />
        </Link>
        <Link href="/models" title="Help & Docs" className="p-1.5 text-gray-500 hover:text-gray-300">
          <HelpCircle className="h-4 w-4" />
        </Link>
        <Link href="/admin" title="Settings" className="p-1.5 text-gray-500 hover:text-gray-300">
          <Settings className="h-4 w-4" />
        </Link>
      </div>
    </aside>
  );
}
