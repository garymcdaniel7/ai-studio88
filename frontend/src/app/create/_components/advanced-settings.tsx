"use client";

import { Settings2 } from "lucide-react";
import type { GenerationSettings } from "../_hooks/use-generation-state";

interface AdvancedSettingsProps {
  settings: GenerationSettings;
  onUpdate: <K extends keyof GenerationSettings>(key: K, value: GenerationSettings[K]) => void;
  open: boolean;
  onToggle: () => void;
}

/**
 * Collapsible advanced generation settings panel.
 */
export function AdvancedSettings({ settings, onUpdate, open, onToggle }: AdvancedSettingsProps) {
  return (
    <div>
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-xs text-gray-400 hover:text-gray-200 mb-2"
      >
        <Settings2 className="h-3.5 w-3.5" />
        Advanced Settings
      </button>

      {open && (
        <div className="grid grid-cols-2 gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
          {/* Negative Prompt */}
          <div className="col-span-2">
            <label className="text-[10px] text-gray-500 block mb-1">Negative Prompt</label>
            <input
              value={settings.negativePrompt}
              onChange={(e) => onUpdate("negativePrompt", e.target.value)}
              placeholder="What to avoid..."
              className="w-full rounded border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            />
          </div>

          {/* Steps */}
          <div>
            <label className="text-[10px] text-gray-500 block mb-1">Steps ({settings.steps})</label>
            <input
              type="range"
              min={1}
              max={50}
              value={settings.steps}
              onChange={(e) => onUpdate("steps", Number(e.target.value))}
              className="w-full"
            />
          </div>

          {/* CFG */}
          <div>
            <label className="text-[10px] text-gray-500 block mb-1">CFG ({settings.cfg})</label>
            <input
              type="range"
              min={1}
              max={20}
              step={0.5}
              value={settings.cfg}
              onChange={(e) => onUpdate("cfg", Number(e.target.value))}
              className="w-full"
            />
          </div>

          {/* Width */}
          <div>
            <label className="text-[10px] text-gray-500 block mb-1">Width</label>
            <select
              value={settings.width}
              onChange={(e) => onUpdate("width", Number(e.target.value))}
              className="w-full rounded border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {[512, 768, 1024, 1280, 1536].map((w) => (
                <option key={w} value={w}>{w}</option>
              ))}
            </select>
          </div>

          {/* Height */}
          <div>
            <label className="text-[10px] text-gray-500 block mb-1">Height</label>
            <select
              value={settings.height}
              onChange={(e) => onUpdate("height", Number(e.target.value))}
              className="w-full rounded border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {[512, 768, 1024, 1280, 1536].map((h) => (
                <option key={h} value={h}>{h}</option>
              ))}
            </select>
          </div>

          {/* Seed */}
          <div>
            <label className="text-[10px] text-gray-500 block mb-1">Seed</label>
            <input
              type="number"
              value={settings.seed}
              onChange={(e) => onUpdate("seed", Number(e.target.value))}
              className="w-full rounded border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            />
          </div>

          {/* Batch Count */}
          <div>
            <label className="text-[10px] text-gray-500 block mb-1">Variations ({settings.batchCount})</label>
            <input
              type="range"
              min={1}
              max={8}
              value={settings.batchCount}
              onChange={(e) => onUpdate("batchCount", Number(e.target.value))}
              className="w-full"
            />
          </div>
        </div>
      )}
    </div>
  );
}
