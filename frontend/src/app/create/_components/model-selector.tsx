"use client";

import type { ModelOption } from "../_hooks/use-create-data";

interface ModelSelectorProps {
  value: string;
  onChange: (modelId: string) => void;
  models: ModelOption[];
  gpuReadyModels: Set<string>;
  gpuOnline: boolean | null;
}

/**
 * GPU-aware image model dropdown — ready models highlighted, offline models disabled.
 */
export function ModelSelector({ value, onChange, models, gpuReadyModels, gpuOnline }: ModelSelectorProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`rounded-lg border px-3 py-2 text-sm outline-none ${
        gpuReadyModels.has(value)
          ? "border-green-500/30 bg-surface-raised text-content-secondary"
          : "border-orange-500/30 bg-surface-raised text-orange-300"
      }`}
    >
      {models.map((m) => {
        const isReady = gpuReadyModels.has(m.id);
        return (
          <option key={m.id} value={m.id} disabled={!isReady && gpuOnline === true}>
            {m.name}{isReady ? " ● Ready" : gpuOnline === false ? " ○ Offline" : " ○ Not Loaded"}
          </option>
        );
      })}
    </select>
  );
}
