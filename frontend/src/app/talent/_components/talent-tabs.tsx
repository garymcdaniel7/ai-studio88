"use client";

export const TALENT_TABS = [
  "All Talent", "Models", "Characters", "Voices",
  "Influencers", "Wardrobe", "Products", "Backgrounds",
];

interface TalentTabsProps {
  selectedTab: string;
  onTabChange: (tab: string) => void;
  counts?: Record<string, number>;
}

/**
 * Domain type tab filter for talent grid.
 */
export function TalentTabs({ selectedTab, onTabChange, counts }: TalentTabsProps) {
  return (
    <div className="flex items-center gap-1 border-b border-white/[0.06] px-6">
      {TALENT_TABS.map((tab) => (
        <button
          key={tab}
          onClick={() => onTabChange(tab)}
          className={`px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${
            selectedTab === tab
              ? "border-purple-500 text-purple-300"
              : "border-transparent text-gray-500 hover:text-gray-300"
          }`}
        >
          {tab}
          {counts && counts[tab] !== undefined && (
            <span className="ml-1.5 text-[10px] text-gray-600">({counts[tab]})</span>
          )}
        </button>
      ))}
    </div>
  );
}
