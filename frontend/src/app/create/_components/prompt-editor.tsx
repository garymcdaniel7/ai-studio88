"use client";

import { Loader2, ChevronDown, Settings2, Sparkles } from "lucide-react";
import { ModelSelector } from "./model-selector";
import type { ModelOption } from "../_hooks/use-create-data";

interface PromptEditorProps {
  prompt: string;
  onPromptChange: (prompt: string) => void;
  onGenerate: () => void;
  generating: boolean;
  // Model selection
  selectedModel: string;
  onSelectModel: (modelId: string) => void;
  imageModelList: ModelOption[];
  gpuReadyModels: Set<string>;
  gpuOnline: boolean | null;
  // Advanced toggle
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
  // Batch
  batchCount: number;
  onBatchCountChange: (count: number) => void;
  // Cost estimate
  steps: number;
  width: number;
  height: number;
  // Favorites
  favoritePrompts: { text: string; savedAt: string }[];
  showFavorites: boolean;
  onToggleFavorites: () => void;
  onSaveFavorite: () => void;
  onRemoveFavorite: (text: string) => void;
}

/**
 * Main generation row — prompt input with favorites, model picker,
 * advanced toggle, batch count, generate button, cost estimate.
 */
export function PromptEditor({
  prompt,
  onPromptChange,
  onGenerate,
  generating,
  selectedModel,
  onSelectModel,
  imageModelList,
  gpuReadyModels,
  gpuOnline,
  showAdvanced,
  onToggleAdvanced,
  batchCount,
  onBatchCountChange,
  steps,
  width,
  height,
  favoritePrompts,
  showFavorites,
  onToggleFavorites,
  onSaveFavorite,
  onRemoveFavorite,
}: PromptEditorProps) {
  return (
    <>
      {/* Main row: prompt + model + generate */}
      <div className="flex gap-3 mb-2">
        <div className="flex-1 relative">
          <input
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) onGenerate(); }}
            className="w-full rounded-lg border border-border-default bg-surface-hover px-4 py-3 pr-10 text-sm text-content-secondary placeholder:text-content-muted outline-none focus:border-purple-500/50"
            placeholder="A luxury penthouse at sunset, photorealistic..."
          />
          {/* Star/Favorite button */}
          <button
            onClick={onSaveFavorite}
            disabled={!prompt.trim()}
            className={`absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded transition-colors ${
              favoritePrompts.some((f) => f.text === prompt.trim())
                ? "text-yellow-400"
                : "text-gray-600 hover:text-yellow-400"
            } disabled:opacity-30`}
            title="Save to favorites"
          >
            <svg className="h-4 w-4" fill={favoritePrompts.some((f) => f.text === prompt.trim()) ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" /></svg>
          </button>
        </div>
        <ModelSelector
          value={selectedModel}
          onChange={onSelectModel}
          models={imageModelList}
          gpuReadyModels={gpuReadyModels}
          gpuOnline={gpuOnline}
        />
        <button
          onClick={onToggleAdvanced}
          className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ${showAdvanced ? "border-purple-500/50 bg-purple-600/10 text-status-info" : "border-border-default bg-surface-hover text-content-tertiary hover:text-content-secondary"}`}
        >
          <Settings2 className="h-4 w-4" />
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
        </button>
        {/* Batch count selector */}
        <select
          value={batchCount}
          onChange={(e) => onBatchCountChange(parseInt(e.target.value))}
          className="rounded-lg border border-border-default bg-surface-raised px-2 py-2 text-sm text-content-secondary outline-none"
          title="Number of variations to generate"
        >
          <option value={1}>×1</option>
          <option value={2}>×2</option>
          <option value={4}>×4</option>
        </select>
        <button
          onClick={onGenerate}
          disabled={generating || !prompt.trim() || gpuOnline === false}
          className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700 flex items-center gap-2 disabled:opacity-50"
          title={gpuOnline === false ? "GPU worker offline — cannot generate" : ""}
        >
          {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {generating ? "Generating..." : gpuOnline === false ? "GPU Offline" : batchCount > 1 ? `Generate ${batchCount}` : "Generate"}
        </button>
      </div>

      {/* Pre-generation cost estimate */}
      {prompt.trim() && gpuOnline !== false && (
        <p className="text-[10px] text-content-muted mb-1">
          Est. cost: ~${(steps * (
            selectedModel === "flux-dev" ? 0.0003 :
            selectedModel === "flux2-dev" ? 0.0003 :
            selectedModel === "flux2-klein" ? 0.0001 :
            selectedModel === "sdxl-turbo" ? 0.00005 :
            0.0001
          ) * batchCount).toFixed(4)} • {batchCount > 1 ? `${batchCount} images` : "1 image"} • {width}×{height}
        </p>
      )}

      {/* Favorites Bar */}
      {favoritePrompts.length > 0 && (
        <div className="mb-2">
          <button
            onClick={onToggleFavorites}
            className="text-[10px] text-yellow-400/70 hover:text-yellow-400 transition-colors"
          >
            ★ {favoritePrompts.length} saved prompt{favoritePrompts.length > 1 ? "s" : ""} {showFavorites ? "▾" : "▸"}
          </button>
          {showFavorites && (
            <div className="mt-2 max-h-32 overflow-y-auto space-y-1 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2">
              {favoritePrompts.slice(0, 10).map((fav, idx) => (
                <div key={idx} className="flex items-center gap-2 group/fav">
                  <button
                    onClick={() => onPromptChange(fav.text)}
                    className="flex-1 text-left text-[11px] text-gray-400 hover:text-white truncate py-0.5 px-1 rounded hover:bg-white/[0.04]"
                  >
                    {fav.text}
                  </button>
                  <button
                    onClick={() => onRemoveFavorite(fav.text)}
                    className="opacity-0 group-hover/fav:opacity-100 text-[10px] text-gray-600 hover:text-red-400"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
