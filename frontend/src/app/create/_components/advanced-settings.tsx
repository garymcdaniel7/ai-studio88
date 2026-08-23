"use client";

import { TalentSelector } from "./talent-selector";
import { LoraPanel } from "./lora-panel";
import type { TalentOption, LoraOption } from "../_hooks/use-create-data";
import type { ActiveLora } from "../_hooks/use-image-generation";

interface AdvancedSettingsProps {
  apiBase: string;
  talentList: TalentOption[];
  selectedTalents: string[];
  onChangeTalents: (next: string[]) => void;
  activeLoras: ActiveLora[];
  availableLoras: LoraOption[];
  onAddLora: (lora: ActiveLora) => void;
  onUpdateLoraStrength: (index: number, strength: number) => void;
  onRemoveLoraAt: (index: number) => void;
  negativePrompt: string;
  onChangeNegativePrompt: (value: string) => void;
  steps: number;
  onChangeSteps: (value: number) => void;
  cfg: number;
  onChangeCfg: (value: number) => void;
  seed: number;
  onChangeSeed: (value: number) => void;
  width: number;
  onChangeWidth: (value: number) => void;
  height: number;
  onChangeHeight: (value: number) => void;
}

/**
 * Collapsible advanced generation settings — talents, LoRAs, negative prompt,
 * steps/CFG/seed, resolution.
 */
export function AdvancedSettings({
  apiBase,
  talentList,
  selectedTalents,
  onChangeTalents,
  activeLoras,
  availableLoras,
  onAddLora,
  onUpdateLoraStrength,
  onRemoveLoraAt,
  negativePrompt,
  onChangeNegativePrompt,
  steps,
  onChangeSteps,
  cfg,
  onChangeCfg,
  seed,
  onChangeSeed,
  width,
  onChangeWidth,
  height,
  onChangeHeight,
}: AdvancedSettingsProps) {
  return (
    <div className="mt-3 rounded-lg border border-border-subtle bg-surface-hover p-4 space-y-3">
      <p className="text-xs font-semibold text-content-secondary">Advanced Settings</p>

      {/* Talent Selection */}
      <TalentSelector
        apiBase={apiBase}
        talentList={talentList}
        selectedTalents={selectedTalents}
        onChange={onChangeTalents}
      />

      {/* Row 1: LoRA + Negative */}
      <div>
        <LoraPanel
          activeLoras={activeLoras}
          availableLoras={availableLoras}
          onAddLora={onAddLora}
          onUpdateStrength={onUpdateLoraStrength}
          onRemoveAt={onRemoveLoraAt}
        />
      </div>

      {/* Row 2: Negative prompt */}
      <div>
        <label className="block text-[10px] text-content-muted mb-1">Negative Prompt</label>
        <input
          type="text"
          value={negativePrompt}
          onChange={(e) => onChangeNegativePrompt(e.target.value)}
          placeholder="blurry, low quality, deformed, watermark..."
          className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-xs text-content-secondary placeholder:text-content-muted outline-none"
        />
      </div>

      {/* Row 3: Steps, CFG, Seed */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-[10px] text-content-muted mb-1">Steps: {steps}</label>
          <input type="range" min="1" max="50" value={steps} onChange={(e) => onChangeSteps(parseInt(e.target.value))} className="w-full accent-purple-500" />
        </div>
        <div>
          <label className="block text-[10px] text-content-muted mb-1">CFG Scale: {cfg.toFixed(1)}</label>
          <input type="range" min="1" max="20" step="0.5" value={cfg} onChange={(e) => onChangeCfg(parseFloat(e.target.value))} className="w-full accent-purple-500" />
        </div>
        <div>
          <label className="block text-[10px] text-content-muted mb-1">Seed (-1 = random)</label>
          <input
            type="number"
            value={seed}
            onChange={(e) => onChangeSeed(parseInt(e.target.value))}
            className="w-full rounded-lg border border-border-default bg-surface-hover px-2 py-1.5 text-xs text-content-secondary outline-none"
          />
        </div>
      </div>

      {/* Row 4: Resolution */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[10px] text-content-muted mb-1">Width: {width}px</label>
          <select value={width} onChange={(e) => onChangeWidth(parseInt(e.target.value))} className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-1.5 text-xs text-content-secondary outline-none">
            {[512, 768, 1024, 1280, 1536].map((v) => <option key={v} value={v}>{v}px</option>)}
          </select>
        </div>
        <div>
          <label className="block text-[10px] text-content-muted mb-1">Height: {height}px</label>
          <select value={height} onChange={(e) => onChangeHeight(parseInt(e.target.value))} className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-1.5 text-xs text-content-secondary outline-none">
            {[512, 768, 1024, 1280, 1536].map((v) => <option key={v} value={v}>{v}px</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}
