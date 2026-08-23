"use client";

import { useState } from "react";
import {
  Star,
  MoreHorizontal,
} from "lucide-react";
import { useToast } from "@/components/toast";
import type { TalentRecord } from "./talent-grid";
import { TalentProfileImage } from "./talent-profile-image";
import { TalentMediaSection } from "./talent-media-section";
import { TalentLoraSection } from "./talent-lora-section";
import { TalentVoiceSection } from "./talent-voice-section";
import { TalentRelationshipsSection } from "./talent-relationships-section";
import { TalentGenerationsSection } from "./talent-generations-section";
import { isFavorite } from "../_hooks/use-talent-favorites";

// ---------------------------------------------------------------------------
// Helper: Dynamic tabs based on talent type
// ---------------------------------------------------------------------------

export function getTabsForType(type: string): string[] {
  switch (type.toLowerCase()) {
    case "model":
    case "influencer":
      return ["Overview", "Details", "Generations", "Voices", "LoRAs", "Relationships", "Stats"];
    case "character":
      return ["Overview", "Details", "Generations", "Voices", "LoRAs", "Story", "Stats"];
    case "voice":
      return ["Overview", "Details", "Voices", "Projects", "Stats"];
    case "wardrobe":
      return ["Overview", "Details", "Media", "Combinations", "Stats"];
    case "background":
      return ["Overview", "Details", "Media", "Variants", "Stats"];
    default:
      return ["Overview", "Details", "Generations", "Voices", "Media", "LoRAs", "Projects", "Stats"];
  }
}

interface TalentDetailProps {
  talent: TalentRecord;
  allTalent: TalentRecord[];
  detailTab: string;
  onDetailTabChange: (tab: string) => void;
  onEdit: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onToggleFavorite: (id: string) => void;
  onAvatarChange: (url: string) => void;
}

/**
 * Detail panel for the selected talent: profile header, reference image,
 * per-type tabs, and tab content sections.
 */
export function TalentDetail({
  talent,
  allTalent,
  detailTab,
  onDetailTabChange,
  onEdit,
  onDelete,
  onDuplicate,
  onToggleFavorite,
  onAvatarChange,
}: TalentDetailProps) {
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const { show } = useToast();

  function copyCreativeDna() {
    // Copy Creative DNA to clipboard
    const dna = { visual_style: talent.visual_style, best_for: talent.best_for, persona: talent.persona, trigger_words: talent.trigger_words };
    navigator.clipboard.writeText(JSON.stringify(dna, null, 2));
    show("Creative DNA copied to clipboard", "success");
    setShowMoreMenu(false);
  }

  function exportJson() {
    // Export as JSON
    const blob = new Blob([JSON.stringify(talent, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${(talent?.name as string || "talent").toLowerCase().replace(/\s+/g, "_")}.json`;
    a.click(); URL.revokeObjectURL(url);
    setShowMoreMenu(false);
  }

  return (
    <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
      {/* Profile header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-bold text-content-primary">{talent.name as string}</h3>
            <button
              onClick={() => {
                onToggleFavorite(talent.id as string);
              }}
              className="p-0.5"
              title={isFavorite(talent.id as string) ? "Remove from favorites" : "Add to favorites"}
            >
              <Star className={`h-4 w-4 cursor-pointer transition-colors ${isFavorite(talent.id as string) ? "text-amber-400 fill-amber-400" : "text-gray-600 hover:text-amber-400"}`} />
            </button>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <span className="rounded bg-interactive-muted px-2 py-0.5 text-xs font-medium text-status-info">
              {(talent.default_style as string) || "Model"}
            </span>
            <span className="flex items-center gap-1 text-xs text-status-success">
              <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> Active
            </span>
          </div>
        </div>
        <div className="flex gap-1">
          <button onClick={onEdit} className="rounded-lg border border-border-default px-3 py-1.5 text-xs text-content-secondary hover:bg-surface-hover">Edit</button>
          <button
            onClick={onDelete}
            className="rounded-lg border border-status-error/30 px-3 py-1.5 text-xs text-status-error hover:bg-red-400/10"
          >
            Delete
          </button>
          <div className="relative">
            <button
              aria-label="More options"
              onClick={() => setShowMoreMenu(!showMoreMenu)}
              className="rounded-lg border border-border-default p-1.5 text-content-tertiary hover:bg-surface-hover"
            >
              <MoreHorizontal className="h-4 w-4" />
            </button>
            {showMoreMenu && (
              <div className="absolute right-0 top-full z-20 mt-1 w-44 rounded-xl border border-border-strong bg-surface-raised p-1.5 shadow-2xl">
                <button
                  onClick={() => { onEdit(); setShowMoreMenu(false); }}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
                >
                  Edit Profile
                </button>
                <button
                  onClick={() => {
                    // Duplicate talent
                    onDuplicate();
                    setShowMoreMenu(false);
                  }}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
                >
                  Duplicate
                </button>
                <button
                  onClick={copyCreativeDna}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
                >
                  Copy DNA
                </button>
                <button
                  onClick={() => {
                    window.location.href = `/training?talent_id=${talent?.id}`;
                    setShowMoreMenu(false);
                  }}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
                >
                  Train LoRA
                </button>
                <button
                  onClick={exportJson}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
                >
                  Export JSON
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Avatar / Main Reference Image */}
      <TalentProfileImage talent={talent} onUpdate={(updated) => onAvatarChange(updated.avatar_url as string)} />

      <p className="text-sm text-content-tertiary">
        {(talent.bio as string) || "Fashion and commercial model with a versatile look suitable for luxury, lifestyle, and editorial campaigns."}
      </p>

      {/* Tabs - dynamic based on talent type */}
      <div className="mt-4 flex gap-1 border-b border-border-subtle overflow-x-auto scrollbar-hide">
        {getTabsForType((talent.default_style as string) || "model").map((t) => (
          <button
            key={t}
            onClick={() => onDetailTabChange(t)}
            className={`px-3 py-2 text-xs transition-colors whitespace-nowrap shrink-0 ${
              detailTab === t
                ? "text-status-info border-b border-purple-500"
                : "text-content-muted hover:text-content-secondary"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {detailTab === "Overview" && (
        <div className="mt-4 space-y-3">
          <h4 className="text-xs font-semibold text-content-tertiary uppercase">Profile</h4>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div><span className="text-content-muted">Full Name</span><p className="text-content-secondary">{(talent.name as string) || "—"}</p></div>
            <div><span className="text-content-muted">Age</span><p className="text-content-secondary">{(talent.age as string) || "—"}</p></div>
            <div><span className="text-content-muted">Height</span><p className="text-content-secondary">{(talent.height as string) || "—"}</p></div>
            <div><span className="text-content-muted">Ethnicity</span><p className="text-content-secondary">{(talent.ethnicity as string) || "—"}</p></div>
          </div>

          {/* Creative DNA */}
          <div className="mt-4 rounded-lg border border-border-subtle bg-white/[0.02] p-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-semibold text-content-primary">Creative DNA</h4>
              <button onClick={onEdit} className="text-[10px] text-status-info">Edit</button>
            </div>
            <div className="mt-2 space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-purple-500" />
                <span className="text-content-tertiary">Visual Style:</span>
                <span className="text-content-secondary">{(talent.visual_style as string) || "Not set"}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-pink-500" />
                <span className="text-content-tertiary">Best For:</span>
                <span className="text-content-secondary">{(talent.best_for as string) || "Not set"}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-blue-500" />
                <span className="text-content-tertiary">Persona:</span>
                <span className="text-content-secondary">{(talent.persona as string) || "Not set"}</span>
              </div>
            </div>
          </div>

          {/* Quick Training Photos */}
          <div className="mt-4">
            <TalentMediaSection talentId={talent.id as string} avatarUrl={talent.avatar_url as string} onAvatarChange={onAvatarChange} />
          </div>
        </div>
      )}

      {detailTab === "Details" && (
        <div className="mt-4 space-y-3">
          <h4 className="text-xs font-semibold text-content-tertiary uppercase">All Fields</h4>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Name</span><span className="text-content-secondary">{(talent.name as string) || "—"}</span></div>
            <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Bio</span><span className="text-content-secondary text-right max-w-[200px] truncate">{(talent.bio as string) || "—"}</span></div>
            <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Age</span><span className="text-content-secondary">{(talent.age as string) || "—"}</span></div>
            <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Height</span><span className="text-content-secondary">{(talent.height as string) || "—"}</span></div>
            <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Ethnicity</span><span className="text-content-secondary">{(talent.ethnicity as string) || "—"}</span></div>
            <div className="flex justify-between"><span className="text-content-muted">Default Style</span><span className="text-content-secondary">{(talent.default_style as string) || "—"}</span></div>
          </div>
        </div>
      )}

      {detailTab === "Wardrobe" && (
        <div className="mt-4 space-y-3">
          <TalentMediaSection talentId={talent.id as string} />
        </div>
      )}

      {detailTab === "LoRAs" && (
        <div className="mt-4 space-y-3">
          <TalentLoraSection talentId={talent.id as string} />
        </div>
      )}

      {(detailTab === "Voices" || detailTab === "Samples") && (
        <div className="mt-4 space-y-3">
          <TalentVoiceSection talentId={talent.id as string} talentName={talent.name as string} />
        </div>
      )}

      {detailTab === "Projects" && (
        <div className="mt-4 text-center py-6">
          <p className="text-sm text-gray-400">No projects associated.</p>
        </div>
      )}

      {detailTab === "Relationships" && (
        <div className="mt-4 space-y-3">
          <TalentRelationshipsSection talentId={talent.id as string} allTalent={allTalent} />
        </div>
      )}

      {detailTab === "Generations" && (
        <div className="mt-4">
          <TalentGenerationsSection talentId={talent.id as string} talentName={talent.name as string} />
        </div>
      )}

      {detailTab === "Stats" && (
        <div className="mt-4 text-center py-6">
          <p className="text-sm text-gray-400">Generation stats will appear once this talent is used in productions.</p>
        </div>
      )}
    </div>
  );
}
