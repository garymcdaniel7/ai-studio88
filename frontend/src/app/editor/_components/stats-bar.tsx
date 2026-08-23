"use client";

/**
 * Stats Bar — shot counts and selected talent summary.
 * Extracted verbatim from editor/page.tsx.
 */

import { CheckCircle, Clock, Film, Layers, Users } from "lucide-react";

interface StatsBarProps {
  shotCount: number;
  totalDuration: number;
  completedCount: number;
  draftCount: number;
  /** Display name of the selected talent, or null when none is selected. */
  talentName: string | null;
}

export function StatsBar({ shotCount, totalDuration, completedCount, draftCount, talentName }: StatsBarProps) {
  return (
    <div className="flex items-center gap-6 rounded-xl border border-white/[0.06] bg-[#12122a] px-5 py-3">
      <div className="flex items-center gap-2">
        <Layers className="h-4 w-4 text-purple-400" />
        <span className="text-xs text-gray-400">{shotCount} shots</span>
      </div>
      <div className="flex items-center gap-2">
        <Clock className="h-4 w-4 text-blue-400" />
        <span className="text-xs text-gray-400">{totalDuration}s total</span>
      </div>
      <div className="flex items-center gap-2">
        <CheckCircle className="h-4 w-4 text-green-400" />
        <span className="text-xs text-gray-400">{completedCount} generated</span>
      </div>
      <div className="flex items-center gap-2">
        <Film className="h-4 w-4 text-amber-400" />
        <span className="text-xs text-gray-400">{draftCount} pending</span>
      </div>
      {talentName && (
        <div className="flex items-center gap-2 ml-auto">
          <Users className="h-4 w-4 text-pink-400" />
          <span className="text-xs text-pink-300">
            DNA: {talentName}
          </span>
        </div>
      )}
    </div>
  );
}
