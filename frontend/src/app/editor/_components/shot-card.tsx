"use client";

/**
 * Shot Card — a single storyboard shot row with inline settings.
 * Extracted verbatim from editor/page.tsx.
 */

import { useState } from "react";
import {
  ChevronDown,
  GripVertical,
  Image as ImageIcon,
  Loader2,
  Play,
  Trash2,
  XCircle,
} from "lucide-react";
import {
  ASPECT_RATIOS,
  CAMERA_MOTIONS,
  MODELS,
  TRANSITIONS,
  type Shot,
} from "./editor-types";

export function ShotCard({
  shot,
  index,
  onUpdate,
  onRemove,
  onGenerate,
  onDragStart,
  onDragOver,
  onDragEnd,
  isDragging,
}: {
  shot: Shot;
  index: number;
  onUpdate: (updates: Partial<Shot>) => void;
  onRemove: () => void;
  onGenerate: () => void;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  isDragging: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  const statusColors: Record<Shot["status"], string> = {
    draft: "border-white/[0.06]",
    generating: "border-purple-500/50 bg-purple-500/5",
    completed: "border-green-500/30",
    failed: "border-red-500/30",
  };

  const statusBadge: Record<Shot["status"], { text: string; color: string }> = {
    draft: { text: "Draft", color: "text-gray-500" },
    generating: { text: "Generating...", color: "text-purple-400" },
    completed: { text: "Done", color: "text-green-400" },
    failed: { text: "Failed", color: "text-red-400" },
  };

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      className={`rounded-xl border bg-[#12122a] transition-all ${statusColors[shot.status]} ${
        isDragging ? "opacity-50 scale-[0.98]" : ""
      }`}
    >
      {/* Main Row */}
      <div className="flex items-center gap-4 p-4">
        {/* Drag Handle */}
        <div className="cursor-grab active:cursor-grabbing text-gray-600 hover:text-gray-400">
          <GripVertical className="h-5 w-5" />
        </div>

        {/* Shot Number */}
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-purple-600/20 text-sm font-bold text-purple-400">
          {index + 1}
        </div>

        {/* Thumbnail */}
        <div className="h-14 w-24 shrink-0 rounded-lg bg-gradient-to-br from-[#1a1a3a] to-[#0d0d20] border border-white/[0.04] flex items-center justify-center overflow-hidden">
          {shot.thumbnail_url ? (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img src={shot.thumbnail_url} alt={`Shot ${index + 1}`} className="h-full w-full object-cover rounded-lg" />
          ) : shot.status === "generating" ? (
            <Loader2 className="h-5 w-5 text-purple-400 animate-spin" />
          ) : (
            <ImageIcon className="h-5 w-5 text-gray-700" />
          )}
        </div>

        {/* Prompt */}
        <div className="flex-1 min-w-0">
          <input
            type="text"
            value={shot.prompt}
            onChange={(e) => onUpdate({ prompt: e.target.value })}
            placeholder="Describe this shot..."
            className="w-full bg-transparent text-sm text-gray-200 placeholder:text-gray-600 outline-none"
          />
          <div className="flex items-center gap-3 mt-1">
            <span className="text-[10px] text-gray-600">{shot.model}</span>
            <span className="text-[10px] text-gray-600">{shot.duration}s</span>
            <span className="text-[10px] text-gray-600">{shot.camera_motion}</span>
            <span className="text-[10px] text-gray-600">→ {shot.transition}</span>
          </div>
        </div>

        {/* Status */}
        <span className={`text-xs font-medium ${statusBadge[shot.status].color}`}>
          {statusBadge[shot.status].text}
        </span>

        {/* Actions */}
        <div className="flex items-center gap-1">
          {(shot.status === "draft" || shot.status === "failed") && (
            <button
              onClick={onGenerate}
              className="rounded-lg bg-purple-600/20 p-2 text-purple-400 hover:bg-purple-600/30"
              title="Generate this shot"
            >
              <Play className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="rounded-lg p-2 text-gray-500 hover:text-gray-300 hover:bg-white/[0.04]"
            title="Settings"
          >
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
          </button>
          <button
            onClick={onRemove}
            className="rounded-lg p-2 text-gray-500 hover:text-red-400 hover:bg-red-400/10"
            title="Remove shot"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Expanded Settings */}
      {expanded && (
        <div className="border-t border-white/[0.04] px-4 py-3 grid grid-cols-5 gap-3">
          {/* Model */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Model</label>
            <select
              value={shot.model}
              onChange={(e) => onUpdate({ model: e.target.value })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>

          {/* Duration */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Duration (s)</label>
            <input
              type="number"
              min={1}
              max={15}
              value={shot.duration}
              onChange={(e) => onUpdate({ duration: parseInt(e.target.value) || 3 })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            />
          </div>

          {/* Camera Motion */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Camera</label>
            <select
              value={shot.camera_motion}
              onChange={(e) => onUpdate({ camera_motion: e.target.value })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {CAMERA_MOTIONS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>

          {/* Transition */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Transition</label>
            <select
              value={shot.transition}
              onChange={(e) => onUpdate({ transition: e.target.value })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {TRANSITIONS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Aspect Ratio */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Aspect Ratio</label>
            <select
              value={shot.aspect_ratio}
              onChange={(e) => onUpdate({ aspect_ratio: e.target.value })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {ASPECT_RATIOS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Error */}
      {shot.error && (
        <div className="border-t border-red-500/10 px-4 py-2 flex items-center gap-2">
          <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
          <p className="text-xs text-red-300">{shot.error}</p>
        </div>
      )}
    </div>
  );
}
