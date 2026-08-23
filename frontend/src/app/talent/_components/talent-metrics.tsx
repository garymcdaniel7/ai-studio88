"use client";

import type { TalentRecord } from "./talent-grid";

interface TalentMetricsProps {
  items: TalentRecord[];
}

/**
 * Summary metric tiles computed from the full talent library.
 */
export function TalentMetrics({ items }: TalentMetricsProps) {
  const metrics = [
    { label: "Total Talent", value: String(items.length), sub: "AI personas", color: "text-blue-400" },
    { label: "Models", value: String(items.filter((t) => !t.default_style || t.default_style === "model" || t.default_style === "fashion").length), sub: "Fashion & commercial", color: "text-purple-400" },
    { label: "Characters", value: String(items.filter((t) => t.default_style === "character" || t.default_style === "story").length), sub: "Story characters", color: "text-amber-400" },
    { label: "Voices", value: String(items.filter((t) => t.default_style === "voice" || t.default_style === "narrator").length), sub: "Voice profiles", color: "text-green-400" },
    { label: "Influencers", value: String(items.filter((t) => t.default_style === "influencer" || t.default_style === "social").length), sub: "AI influencers", color: "text-pink-400" },
    { label: "Wardrobe Sets", value: String(items.filter((t) => t.default_style === "wardrobe" || t.default_style === "fashion_set").length), sub: "Outfits & styles", color: "text-teal-400" },
  ];

  return (
    <div className="grid grid-cols-6 gap-3">
      {metrics.map((m) => (
        <div key={m.label} className="rounded-xl border border-border-subtle bg-surface-raised p-3 text-center">
          <p className="text-xs text-content-muted">{m.label}</p>
          <p className="text-xl font-bold text-content-primary">{m.value}</p>
          <p className={`text-xs ${m.color}`}>{m.sub}</p>
        </div>
      ))}
    </div>
  );
}
