"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { Search, Plus, Filter, Users } from "lucide-react";

export type TalentRecord = Record<string, unknown>;

interface TalentGridProps {
  items: TalentRecord[];
  selectedId: string | null;
  selectedTab: string;
  isFetching: boolean;
  onSelect: (talent: TalentRecord) => void;
  onCreateClick: () => void;
}

/**
 * Talent card grid with result-count toolbar, search affordance,
 * and empty state.
 */
export function TalentGrid({ items, selectedId, selectedTab, isFetching, onSelect, onCreateClick }: TalentGridProps) {
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-content-tertiary">
          Talent Library · {items.length} results
        </p>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-border-default bg-surface-hover px-2 py-1">
            <Search className="h-3.5 w-3.5 text-content-muted" />
            <input className="w-32 bg-transparent text-xs text-content-secondary placeholder:text-content-muted outline-none" placeholder="Search..." />
          </div>
          <button aria-label="Filter talent" className="flex items-center gap-1 rounded-lg border border-border-default px-2 py-1 text-xs text-content-tertiary">
            <Filter className="h-3 w-3" /> Filters
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {items.length === 0 && !isFetching && (
          <div className="col-span-4 rounded-xl border border-border-subtle bg-surface-raised p-8 text-center">
            <Users className="h-10 w-10 text-content-muted mx-auto mb-3" />
            <p className="text-sm text-content-tertiary">
              {selectedTab === "All Talent" ? "No talent yet" : `No ${selectedTab.toLowerCase()} found`}
            </p>
            <p className="text-xs text-content-muted mt-1">Create your first AI persona to start generating content.</p>
            <button
              onClick={onCreateClick}
              className="mt-3 inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
            >
              <Plus className="h-4 w-4" /> Create Talent
            </button>
          </div>
        )}
        {items.map((talent) => (
          <button
            key={talent.id as string}
            onClick={() => onSelect(talent)}
            className={`group relative overflow-hidden rounded-xl border transition-all ${
              selectedId === talent.id
                ? "border-purple-500/50 ring-1 ring-purple-500/30"
                : "border-border-subtle hover:border-white/[0.12]"
            } bg-surface-raised`}
          >
            {/* Avatar / Default Photo */}
            <div className="aspect-[3/4] w-full bg-gradient-to-br from-purple-900/30 to-blue-900/30 overflow-hidden">
              {(talent.avatar_url as string) ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={(talent.avatar_url as string).startsWith("/") ? `${API_BASE}${talent.avatar_url}` : (talent.avatar_url as string)}
                  alt={(talent.name as string) || ""}
                  className="w-full h-full object-cover"
                />
              ) : null}
            </div>
            <div className="p-3">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-content-primary">{talent.name as string}</p>
                <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-interactive-muted text-status-info">
                  {(talent.default_style as string) || "Model"}
                </span>
              </div>
              <p className="text-xs text-content-muted">{(talent.bio as string)?.slice(0, 40) || "AI Talent"}</p>
              <div className="mt-1 flex items-center justify-between">
                <div className="flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                  <span className="text-[10px] text-content-muted">Active</span>
                </div>
                <a
                  href={`/training?talent_id=${talent.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="text-[10px] text-status-info hover:text-purple-300 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  Train LoRA →
                </a>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
