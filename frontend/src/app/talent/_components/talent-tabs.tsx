"use client";

export const TALENT_TABS = [
  "All Talent", "Models", "Characters", "Voices",
  "Influencers", "Wardrobe", "Products", "Backgrounds",
];

interface TalentTabsProps {
  selectedTab: string;
  onSelectTab: (tab: string) => void;
}

/**
 * Domain type tab filter for the talent library.
 */
export function TalentTabs({ selectedTab, onSelectTab }: TalentTabsProps) {
  return (
    <div className="flex items-center gap-1 border-b border-border-subtle pb-px">
      {TALENT_TABS.map((tab) => (
        <button
          key={tab}
          onClick={() => onSelectTab(tab)}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            selectedTab === tab
              ? "border-b-2 border-purple-500 text-status-info"
              : "text-content-muted hover:text-content-secondary"
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
