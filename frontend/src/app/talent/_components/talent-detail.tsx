"use client";

import { Trash2, Sparkles, Maximize2 } from "lucide-react";
import type { TalentRecord } from "../_hooks/use-talent-data";

interface TalentDetailProps {
  talent: TalentRecord | null;
  detailTab: string;
  onDetailTabChange: (tab: string) => void;
  onEdit: () => void;
  onDelete: (id: string) => void;
}

const DETAIL_TABS = ["Overview", "Gallery", "Relationships", "LoRA", "Voice", "History"];

/**
 * Talent detail panel — displays selected talent's info, tabs, and actions.
 */
export function TalentDetail({
  talent,
  detailTab,
  onDetailTabChange,
  onEdit,
  onDelete,
}: TalentDetailProps) {
  if (!talent) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-gray-500">Select a talent to view details</p>
      </div>
    );
  }

  const name = (talent.name as string) || "Untitled";
  const bio = (talent.bio as string) || "";
  const type = (talent.type as string) || (talent.default_style as string) || "model";

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-white/[0.06] px-6 py-4">
        <div className="flex items-center gap-4">
          <div className="h-16 w-16 rounded-xl bg-gradient-to-br from-purple-500/20 to-blue-500/20 flex items-center justify-center">
            <span className="text-2xl font-bold text-purple-300">{name[0]?.toUpperCase()}</span>
          </div>
          <div>
            <h2 className="text-lg font-bold text-white">{name}</h2>
            <p className="text-xs text-gray-500 capitalize">{type}</p>
            {bio && <p className="text-xs text-gray-400 mt-1 max-w-md truncate">{bio}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onEdit}
            className="rounded-lg border border-white/[0.08] px-3 py-1.5 text-xs text-gray-400 hover:text-white hover:bg-white/[0.04]"
          >
            Edit
          </button>
          <button
            onClick={() => onDelete(talent.id as string)}
            className="rounded-lg border border-red-500/20 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Detail Tabs */}
      <div className="flex items-center gap-1 border-b border-white/[0.06] px-6">
        {DETAIL_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => onDetailTabChange(tab)}
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
              detailTab === tab
                ? "border-purple-500 text-purple-300"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {detailTab === "Overview" && <OverviewTab talent={talent} />}
        {detailTab === "Gallery" && <GalleryTab talent={talent} />}
        {detailTab === "Relationships" && <RelationshipsTab talent={talent} />}
        {detailTab === "LoRA" && <LoRATab talent={talent} />}
        {detailTab === "Voice" && <VoiceTab talent={talent} />}
        {detailTab === "History" && <HistoryTab talent={talent} />}
      </div>
    </div>
  );
}

// =============================================================================
// Tab Content Components
// =============================================================================

function OverviewTab({ talent }: { talent: TalentRecord }) {
  const fields: { label: string; value: string }[] = [
    { label: "Height", value: talent.height as string || "" },
    { label: "Hair Color", value: talent.hair_color as string || "" },
    { label: "Eye Color", value: talent.eye_color as string || "" },
    { label: "Body Type", value: talent.body_type as string || "" },
    { label: "Visual Style", value: talent.visual_style as string || "" },
    { label: "Persona", value: talent.persona as string || "" },
    { label: "Trigger Word", value: talent.trigger_word as string || "" },
  ].filter((f) => f.value);

  return (
    <div className="space-y-4">
      {fields.length > 0 ? (
        <div className="grid grid-cols-2 gap-3">
          {fields.map((f) => (
            <div key={f.label} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="text-[10px] text-gray-500 uppercase">{f.label}</p>
              <p className="text-sm text-gray-200 mt-0.5">{f.value}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-500">No attributes set. Click Edit to add details.</p>
      )}
      {Boolean(talent.negative_prompt) && (
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
          <p className="text-[10px] text-gray-500 uppercase">Negative Prompt</p>
          <p className="text-xs text-gray-300 mt-1">{String(talent.negative_prompt as string)}</p>
        </div>
      )}
    </div>
  );
}

function GalleryTab({ talent }: { talent: TalentRecord }) {
  return (
    <div className="flex items-center justify-center h-32">
      <div className="text-center">
        <Maximize2 className="h-6 w-6 text-gray-600 mx-auto mb-2" />
        <p className="text-xs text-gray-500">No gallery images yet</p>
        <p className="text-[10px] text-gray-600">Generate images with this talent to populate</p>
      </div>
    </div>
  );
}

function RelationshipsTab({ talent }: { talent: TalentRecord }) {
  return (
    <div className="flex items-center justify-center h-32">
      <div className="text-center">
        <p className="text-xs text-gray-500">No relationships defined</p>
        <p className="text-[10px] text-gray-600">Link this talent to wardrobe, locations, or other characters</p>
      </div>
    </div>
  );
}

function LoRATab({ talent }: { talent: TalentRecord }) {
  const hasLora = Boolean(talent.lora_model_id || talent.trigger_word);
  const triggerWord = talent.trigger_word ? String(talent.trigger_word) : "";
  return (
    <div className="space-y-3">
      {hasLora ? (
        <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="h-4 w-4 text-purple-400" />
            <p className="text-sm font-medium text-purple-300">LoRA Model Active</p>
          </div>
          {triggerWord && (
            <p className="text-xs text-gray-400">Trigger: <code className="text-purple-300">{triggerWord}</code></p>
          )}
        </div>
      ) : (
        <div className="text-center py-8">
          <Sparkles className="h-6 w-6 text-gray-600 mx-auto mb-2" />
          <p className="text-xs text-gray-500">No LoRA model trained yet</p>
          <p className="text-[10px] text-gray-600">Go to Training to create a LoRA for this talent</p>
        </div>
      )}
    </div>
  );
}

function VoiceTab({ talent }: { talent: TalentRecord }) {
  return (
    <div className="flex items-center justify-center h-32">
      <div className="text-center">
        <p className="text-xs text-gray-500">No voice profile assigned</p>
        <p className="text-[10px] text-gray-600">Assign a voice in the Audio section</p>
      </div>
    </div>
  );
}

function HistoryTab({ talent }: { talent: TalentRecord }) {
  return (
    <div className="flex items-center justify-center h-32">
      <p className="text-xs text-gray-500">Generation history will appear here</p>
    </div>
  );
}
