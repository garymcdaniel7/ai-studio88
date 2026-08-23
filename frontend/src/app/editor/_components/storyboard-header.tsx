"use client";

/**
 * Storyboard Header — title, talent selector, and primary actions.
 * Extracted verbatim from editor/page.tsx.
 */

import {
  CheckCircle,
  Download,
  FolderOpen,
  Loader2,
  Save,
  Sparkles,
} from "lucide-react";

interface StoryboardHeaderProps {
  storyboardName: string;
  onNameChange: (name: string) => void;
  talents: Record<string, unknown>[];
  selectedTalentId: string | null;
  onTalentChange: (value: string) => void;
  saving: boolean;
  saveStatus: "idle" | "saved" | "error";
  onSave: () => void;
  onLoad: () => void;
  generating: boolean;
  draftCount: number;
  onGenerateAll: () => void;
  assembling: boolean;
  completedCount: number;
  onAssemble: () => void;
}

export function StoryboardHeader({
  storyboardName,
  onNameChange,
  talents,
  selectedTalentId,
  onTalentChange,
  saving,
  saveStatus,
  onSave,
  onLoad,
  generating,
  draftCount,
  onGenerateAll,
  assembling,
  completedCount,
  onAssemble,
}: StoryboardHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div>
          <input
            value={storyboardName}
            onChange={(e) => onNameChange(e.target.value)}
            className="text-2xl font-bold text-white bg-transparent border-none outline-none focus:border-b focus:border-purple-500"
            placeholder="Storyboard name..."
          />
          <p className="text-sm text-gray-500">
            Plan shots, generate clips, assemble your production.
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {/* Talent Selector */}
        <select
          value={selectedTalentId || ""}
          onChange={(e) => onTalentChange(e.target.value)}
          className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none"
        >
          <option value="">No talent (raw prompts)</option>
          {talents.map((t) => (
            <option key={t.id as string} value={t.id as string}>
              {t.name as string} — DNA inject
            </option>
          ))}
        </select>
        {/* Save */}
        <button
          onClick={onSave}
          disabled={saving}
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm disabled:opacity-50 ${
            saveStatus === "saved" ? "border-green-500/30 bg-green-500/10 text-green-400" :
            saveStatus === "error" ? "border-red-500/30 bg-red-500/10 text-red-400" :
            "border-white/[0.08] bg-white/[0.03] text-gray-300 hover:bg-white/[0.06]"
          }`}
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : saveStatus === "saved" ? <CheckCircle className="h-4 w-4" /> : <Save className="h-4 w-4" />}
          {saveStatus === "saved" ? "Saved!" : saveStatus === "error" ? "Error" : "Save"}
        </button>
        {/* Load */}
        <button
          onClick={onLoad}
          className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]"
        >
          <FolderOpen className="h-4 w-4" /> Load
        </button>
        {/* Generate All */}
        <button
          onClick={onGenerateAll}
          disabled={generating || draftCount === 0}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
        >
          {generating ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Generating...</>
          ) : (
            <><Sparkles className="h-4 w-4" /> Generate All ({draftCount})</>
          )}
        </button>
        {/* Assemble */}
        <button
          onClick={onAssemble}
          disabled={assembling || completedCount < 2}
          className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-gray-300 hover:bg-white/[0.06] disabled:opacity-50"
        >
          {assembling ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Assembling...</>
          ) : (
            <><Download className="h-4 w-4" /> Assemble Video</>
          )}
        </button>
      </div>
    </div>
  );
}
