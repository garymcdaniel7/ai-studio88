"use client";

import { Star, MoreHorizontal } from "lucide-react";
import type { TalentRecord } from "../_hooks/use-talent-data";

interface TalentGridProps {
  items: TalentRecord[];
  selectedId: string | null;
  onSelect: (talent: TalentRecord) => void;
  onToggleFavorite: (id: string) => void;
  isFavorite: (id: string) => boolean;
}

/**
 * Grid/list of talent cards with selection and favorites.
 */
export function TalentGrid({
  items,
  selectedId,
  onSelect,
  onToggleFavorite,
  isFavorite,
}: TalentGridProps) {
  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-gray-500">No talent found. Create your first character above.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-2 p-4 overflow-y-auto">
      {items.map((talent) => {
        const id = talent.id as string;
        const name = (talent.name as string) || "Untitled";
        const type = (talent.type as string) || (talent.default_style as string) || "model";
        const isSelected = selectedId === id;
        const fav = isFavorite(id);

        return (
          <div
            key={id}
            onClick={() => onSelect(talent)}
            role="button"
            tabIndex={0}
            className={`flex items-center gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition-colors ${
              isSelected
                ? "bg-purple-600/20 border border-purple-500/30"
                : "hover:bg-white/[0.03] border border-transparent"
            }`}
          >
            {/* Avatar */}
            <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-purple-500/20 to-blue-500/20 flex items-center justify-center shrink-0">
              <span className="text-sm font-bold text-purple-300">{name[0]?.toUpperCase()}</span>
            </div>
            {/* Info */}
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium truncate ${isSelected ? "text-purple-300" : "text-gray-200"}`}>
                {name}
              </p>
              <p className="text-[10px] text-gray-500 capitalize">{type}</p>
            </div>
            {/* Actions */}
            <button
              onClick={(e) => { e.stopPropagation(); onToggleFavorite(id); }}
              className={`p-1 rounded ${fav ? "text-amber-400" : "text-gray-600 hover:text-gray-400"}`}
              aria-label={fav ? "Remove from favorites" : "Add to favorites"}
            >
              <Star className="h-3.5 w-3.5" fill={fav ? "currentColor" : "none"} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
