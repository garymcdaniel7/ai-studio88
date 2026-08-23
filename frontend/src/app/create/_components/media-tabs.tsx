"use client";

import { Image as ImageIcon, Film, Mic } from "lucide-react";

export type MediaTab = "image" | "video" | "audio";

const TABS: { key: MediaTab; label: string; icon: typeof ImageIcon }[] = [
  { key: "image", label: "Image Generation", icon: ImageIcon },
  { key: "video", label: "Video Generation", icon: Film },
  { key: "audio", label: "Voice & Music", icon: Mic },
];

/**
 * Image / Video / Audio tab selector for the Create page.
 */
export function MediaTabs({ activeTab, onTabChange }: { activeTab: MediaTab; onTabChange: (tab: MediaTab) => void }) {
  return (
    <div className="flex gap-1 border-b border-border-subtle pb-px">
      {TABS.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onTabChange(tab.key)}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors ${
            activeTab === tab.key
              ? "border-b-2 border-purple-500 text-status-info"
              : "text-content-muted hover:text-content-secondary"
          }`}
        >
          <tab.icon className="h-4 w-4" />
          {tab.label}
        </button>
      ))}
    </div>
  );
}
