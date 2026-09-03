"use client";

import type { ModelOption } from "../_hooks/use-create-data";
import { Select, SelectItem } from "@/components/ui/select";

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
    <Select
      value={value}
      onValueChange={(v) => onChange(String(v))}
      className={`rounded-lg border px-3 py-2 text-sm outline-none ${
        gpuReadyModels.has(value)
          ? "border-green-500/30 bg-surface-raised text-content-secondary"
          : "border-orange-500/30 bg-surface-raised text-orange-300"
      }`}
    >
      {models.map((m) => {
        const isReady = gpuReadyModels.has(m.id);
        return (
          <SelectItem key={m.id} value={m.id} disabled={!isReady && gpuOnline === true}>
            {m.name}{isReady ? " ● Ready" : gpuOnline === false ? " ○ Offline" : " ○ Not Loaded"}
          </SelectItem>
        );
      })}
    </Select>
  );
}
