"use client";

import { useState } from "react";

interface PresetPacksProps {
  presets: Record<string, unknown>[];
  workerVram: number | null;
  onApplyPreset: (preset: Record<string, unknown>) => void;
}

/**
 * Style preset packs browser — filterable grid of preset cards.
 */
export function PresetPacks({ presets, workerVram, onApplyPreset }: PresetPacksProps) {
  const [presetFilter, setPresetFilter] = useState("image");

  return (
    <>
      {presets.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white">Style Presets</h3>
            <div className="flex gap-1">
              {["all", "image", "utility", "advanced"].map((cat) => (
                <button
                  key={cat}
                  onClick={() => setPresetFilter(cat)}
                  className={`px-2 py-1 rounded text-[10px] font-medium ${presetFilter === cat ? "bg-purple-600 text-white" : "bg-surface-hover text-content-muted hover:text-content-secondary"}`}
                >
                  {cat === "all" ? "All" : cat.charAt(0).toUpperCase() + cat.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-4 gap-3">
            {presets
              .filter((p) => presetFilter === "all" || p.category === presetFilter)
              .slice(0, 8)
              .map((preset) => (
                <button
                  key={preset.id as string}
                  onClick={() => onApplyPreset(preset)}
                  className="rounded-xl border border-border-subtle bg-surface-raised p-3 text-left hover:border-purple-500/30 transition-all group"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-content-primary group-hover:text-purple-300">{preset.name as string}</span>
                    {Boolean(preset.badge) && (
                      <span className="rounded px-1 py-0.5 text-[8px] font-medium bg-interactive-muted text-status-info">
                        {String(preset.badge)}
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-content-muted line-clamp-2">{preset.description as string}</p>
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-[9px] text-content-muted">{preset.model as string}</span>
                    <span className={`text-[9px] px-1 py-0.5 rounded ${
                      workerVram && (preset.required_vram_gb as number) <= workerVram
                        ? "bg-status-success-muted text-status-success"
                        : (preset.required_vram_gb as number) <= 12
                          ? "bg-status-success-muted text-status-success"
                          : (preset.required_vram_gb as number) <= 32
                            ? "bg-status-warning-muted text-status-warning"
                            : "bg-status-error-muted text-status-error"
                    }`}>
                      {workerVram && (preset.required_vram_gb as number) <= workerVram ? "✓ " : ""}
                      {preset.required_vram_gb as number}GB
                    </span>
                  </div>
                </button>
              ))}
          </div>
        </div>
      )}
    </>
  );
}
