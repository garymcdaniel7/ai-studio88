"use client";

import { Image as ImageIcon, Film, Mic } from "lucide-react";

export type MediaTab = "image" | "video" | "audio";

interface MediaTabsProps {
  activeTab: MediaTab;
  onTabChange: (tab: MediaTab) => void;
}

const TABS: { key: MediaTab; label: string; icon: typeof ImageIcon }[] = [
  { key: "image", label: "Image", icon: ImageIcon },
  { key: "video", label: "Video", icon: Film },
  { key: "audio", label: "Audio", icon: Mic },
];

/**
 * Image / Video / Audio tab selector for the Create page.
 */
export function MediaTabs({ activeTab, onTabChange }: MediaTabsProps) {
  return (
    <div className="flex items-center gap-1 border-b border-white/[0.06] px-6">
      {TABS.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onTabChange(tab.key)}
          className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === tab.key
              ? "border-purple-500 text-purple-300"
              : "border-transparent text-gray-500 hover:text-gray-300"
          }`}
        >
          <tab.icon className="h-4 w-4" />
          {tab.label}
        </button>
      ))}
    </div>
  );
}
