"use client";

import { useState } from "react";
import { Plus, X, Sparkles } from "lucide-react";

export interface LoraOption {
  id: string;
  name: string;
  trigger_words?: string;
  strength?: number;
}

export interface ActiveLora {
  id: string;
  name: string;
  strength: number;
}

interface LoraPanelProps {
  activeLoras: ActiveLora[];
  availableLoras: LoraOption[];
  onAddLora: (lora: ActiveLora) => void;
  onRemoveLora: (id: string) => void;
  onStrengthChange: (id: string, strength: number) => void;
}

/**
 * LoRA selection and management panel.
 * Supports multiple active LoRAs with individual strength sliders.
 */
export function LoraPanel({
  activeLoras,
  availableLoras,
  onAddLora,
  onRemoveLora,
  onStrengthChange,
}: LoraPanelProps) {
  const [showSelector, setShowSelector] = useState(false);

  function handleAdd(lora: LoraOption) {
    onAddLora({
      id: lora.id,
      name: lora.name,
      strength: lora.strength || 0.7,
    });
    setShowSelector(false);
  }

  const unselected = availableLoras.filter(
    (l) => !activeLoras.some((a) => a.id === l.id)
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-gray-400 flex items-center gap-1.5">
          <Sparkles className="h-3 w-3 text-purple-400" />
          LoRA Models
        </label>
        <button
          onClick={() => setShowSelector(!showSelector)}
          disabled={unselected.length === 0}
          className="flex items-center gap-1 text-[10px] text-purple-400 hover:text-purple-300 disabled:opacity-30"
        >
          <Plus className="h-3 w-3" /> Add LoRA
        </button>
      </div>

      {/* Active LoRAs */}
      {activeLoras.length > 0 && (
        <div className="space-y-2">
          {activeLoras.map((lora) => (
            <div
              key={lora.id}
              className="flex items-center gap-2 rounded-lg border border-purple-500/20 bg-purple-500/5 px-3 py-2"
            >
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-purple-300 truncate">{lora.name}</p>
                <div className="flex items-center gap-2 mt-1">
                  <input
                    type="range"
                    min={0}
                    max={1.5}
                    step={0.05}
                    value={lora.strength}
                    onChange={(e) => onStrengthChange(lora.id, Number(e.target.value))}
                    className="flex-1 h-1"
                  />
                  <span className="text-[10px] text-gray-500 w-8">{lora.strength.toFixed(2)}</span>
                </div>
              </div>
              <button
                onClick={() => onRemoveLora(lora.id)}
                className="p-1 text-gray-500 hover:text-red-400"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Selector dropdown */}
      {showSelector && unselected.length > 0 && (
        <div className="rounded-lg border border-white/[0.08] bg-[#12122a] p-2 max-h-40 overflow-y-auto">
          {unselected.map((lora) => (
            <button
              key={lora.id}
              onClick={() => handleAdd(lora)}
              className="w-full flex items-center justify-between px-2 py-1.5 rounded text-left hover:bg-white/[0.04]"
            >
              <div>
                <p className="text-xs text-gray-200">{lora.name}</p>
                {lora.trigger_words && (
                  <p className="text-[10px] text-gray-500">Trigger: {lora.trigger_words}</p>
                )}
              </div>
              <Plus className="h-3 w-3 text-gray-500" />
            </button>
          ))}
        </div>
      )}

      {activeLoras.length === 0 && !showSelector && (
        <p className="text-[10px] text-gray-600">No LoRA active. Add one for character-specific generation.</p>
      )}
    </div>
  );
}
