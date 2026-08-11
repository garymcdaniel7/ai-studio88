"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

export interface ModelOption {
  id: string;
  name: string;
  desc: string;
  vram: string;
  badge: string;
}

const DEFAULT_MODELS: ModelOption[] = [
  { id: "flux2-klein", name: "FLUX.2 Klein", desc: "Fast, high quality", vram: "12GB", badge: "Recommended" },
  { id: "flux-dev", name: "FLUX.1-dev", desc: "Best quality, slower", vram: "24GB", badge: "Pro" },
  { id: "sdxl", name: "SDXL", desc: "Stable Diffusion XL", vram: "12GB", badge: "Classic" },
  { id: "sd15", name: "SD 1.5", desc: "Lightweight, fast", vram: "8GB", badge: "Legacy" },
];

interface ModelSelectorProps {
  selectedModel: string;
  onModelChange: (modelId: string) => void;
  models?: ModelOption[];
  workerVram?: number | null;
}

/**
 * Model selection dropdown with VRAM badges.
 */
export function ModelSelector({
  selectedModel,
  onModelChange,
  models = DEFAULT_MODELS,
  workerVram,
}: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const current = models.find((m) => m.id === selectedModel) || models[0];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-left"
      >
        <div>
          <p className="text-sm font-medium text-gray-200">{current.name}</p>
          <p className="text-[10px] text-gray-500">{current.desc}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">
            {current.badge}
          </span>
          <ChevronDown className={`h-4 w-4 text-gray-500 transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>

      {open && (
        <div className="absolute top-full left-0 right-0 mt-1 z-20 rounded-lg border border-white/[0.08] bg-[#12122a] shadow-xl overflow-hidden">
          {models.map((model) => {
            const vramNum = parseInt(model.vram);
            const compatible = !workerVram || vramNum <= workerVram;
            return (
              <button
                key={model.id}
                onClick={() => { onModelChange(model.id); setOpen(false); }}
                disabled={!compatible}
                className={`w-full flex items-center justify-between px-3 py-2.5 text-left transition-colors ${
                  selectedModel === model.id ? "bg-purple-600/20" : "hover:bg-white/[0.04]"
                } ${!compatible ? "opacity-40 cursor-not-allowed" : ""}`}
              >
                <div>
                  <p className="text-sm text-gray-200">{model.name}</p>
                  <p className="text-[10px] text-gray-500">{model.desc}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-500">{model.vram}</span>
                  <span className="text-[10px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">
                    {model.badge}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
