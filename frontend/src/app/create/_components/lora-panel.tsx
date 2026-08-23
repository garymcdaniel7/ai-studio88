"use client";

import type { ActiveLora } from "../_hooks/use-image-generation";
import type { LoraOption } from "../_hooks/use-create-data";

interface LoraPanelProps {
  activeLoras: ActiveLora[];
  availableLoras: LoraOption[];
  onAddLora: (lora: ActiveLora) => void;
  onUpdateStrength: (index: number, strength: number) => void;
  onRemoveAt: (index: number) => void;
}

/**
 * Active LoRA list with strength sliders + add dropdown.
 */
export function LoraPanel({ activeLoras, availableLoras, onAddLora, onUpdateStrength, onRemoveAt }: LoraPanelProps) {
  return (
    <div>
      <label className="block text-[10px] text-content-muted mb-1">LoRA Models</label>
      {/* Active LoRAs */}
      {activeLoras.map((lora, idx) => (
        <div key={lora.id} className="flex items-center gap-2 mb-2 rounded-lg border border-border-subtle bg-surface-hover px-2 py-1.5">
          <span className="text-xs text-content-secondary flex-1 truncate">{lora.name}</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={lora.strength}
            onChange={(e) => onUpdateStrength(idx, parseFloat(e.target.value))}
            className="w-20 accent-purple-500"
          />
          <span className="text-[10px] text-content-muted w-8">{lora.strength.toFixed(2)}</span>
          <button
            onClick={() => onRemoveAt(idx)}
            className="text-content-muted hover:text-status-error text-xs"
          >
            ×
          </button>
        </div>
      ))}
      {/* Add LoRA dropdown */}
      <select
        value=""
        onChange={(e) => {
          const id = e.target.value;
          if (!id) return;
          const lora = availableLoras.find((l) => l.id === id);
          if (lora && !activeLoras.find((a) => a.id === id)) {
            onAddLora({ id: lora.id, name: lora.name, strength: lora.strength || 0.7 });
          }
        }}
        className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-xs text-content-secondary outline-none"
      >
        <option value="">+ Add LoRA...</option>
        {availableLoras
          .filter((l) => !activeLoras.find((a) => a.id === l.id))
          .map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
      </select>
      {activeLoras.length === 0 && (
        <p className="text-[10px] text-content-muted mt-1">No LoRAs active. Add one above to apply style/character training.</p>
      )}
    </div>
  );
}
