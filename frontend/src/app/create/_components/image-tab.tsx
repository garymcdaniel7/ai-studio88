"use client";

import type { Dispatch, SetStateAction } from "react";
import { Image as ImageIcon } from "lucide-react";
import { Select, SelectItem } from "@/components/ui/select";
import { AdvancedSettings } from "./advanced-settings";
import { GenerationResultPanel } from "./generation-result";
import { GpuStatusBanners } from "./gpu-status-banner";
import { PresetPacks } from "./preset-packs";
import { PromptEditor } from "./prompt-editor";
import type { LoraOption, ModelOption, TalentOption } from "../_hooks/use-create-data";
import type { useFavoritePrompts } from "../_hooks/use-favorite-prompts";
import type { useImageGeneration } from "../_hooks/use-image-generation";

interface ImageTabProps {
  apiBase: string;
  imageModelList: ModelOption[];
  gpuReadyModels: Set<string>;
  gpuOnline: boolean | null;
  presets: Record<string, unknown>[];
  workerVram: number | null;
  generationHistory: Record<string, unknown>[];
  talentList: TalentOption[];
  projectList: { id: string; name: string }[];
  availableLoras: LoraOption[];
  prompt: string;
  setPrompt: Dispatch<SetStateAction<string>>;
  selectedModel: string;
  setSelectedModel: (id: string) => void;
  selectedTalent: string | null;
  onSelectTalent: (talentId: string | null) => void;
  selectedProject: string | null;
  onSelectProject: (projectId: string | null) => void;
  selectedStyle: string;
  onSelectStyle: (style: string) => void;
  selectedTalents: string[];
  onChangeTalents: (next: string[]) => void;
  img: ReturnType<typeof useImageGeneration>;
  favorites: ReturnType<typeof useFavoritePrompts>;
}

/**
 * Image generation tab — quick generate card (talent/style, GPU status,
 * prompt editor, advanced panel), preset packs, results, history gallery.
 */
export function ImageTab({
  apiBase,
  imageModelList,
  gpuReadyModels,
  gpuOnline,
  presets,
  workerVram,
  generationHistory,
  talentList,
  projectList,
  prompt,
  setPrompt,
  selectedModel,
  setSelectedModel,
  selectedTalent,
  onSelectTalent,
  selectedProject,
  onSelectProject,
  selectedStyle,
  onSelectStyle,
  selectedTalents,
  onChangeTalents,
  availableLoras,
  img,
  favorites,
}: ImageTabProps) {
  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border-subtle bg-surface-raised p-6">
        <h3 className="text-sm font-semibold text-content-primary mb-1">Quick Generate</h3>
        <p className="text-xs text-content-muted mb-4">Describe what you want — AI handles the rest.</p>

        {/* Talent + Style Row */}
        <div className="flex gap-3 mb-3">
          <div className="flex-1">
            <label className="block text-[10px] font-medium text-content-muted mb-1">Generate as talent (optional)</label>
            <Select
              value={selectedTalent || ""}
              onValueChange={(v) => onSelectTalent(v === "" ? null : String(v))}
              className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-secondary outline-none"
            >
              <SelectItem value="">No talent (freestyle)</SelectItem>
              {talentList.map((t) => (
                <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
              ))}
            </Select>
          </div>
          <div className="flex-1">
            <label className="block text-[10px] font-medium text-content-muted mb-1">Recipe (style + settings)</label>
            <Select
              value={selectedStyle}
              onValueChange={(v) => onSelectStyle(String(v))}
              className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-secondary outline-none"
            >
              <SelectItem value="auto">Auto — AI picks best settings</SelectItem>
              <SelectItem value="recipe-studio-portrait">Studio Portrait ★4.5</SelectItem>
              <SelectItem value="recipe-golden-hour">Golden Hour ★4.7</SelectItem>
              <SelectItem value="recipe-magazine-cover">Magazine Cover ★4.8</SelectItem>
              <SelectItem value="recipe-street-style">Street Style ★4.2</SelectItem>
              <SelectItem value="recipe-product-clean">Clean Product ★4.6</SelectItem>
              <SelectItem value="recipe-product-luxury">Luxury Product ★4.7</SelectItem>
              <SelectItem value="recipe-cinematic">Cinematic Landscape ★4.4</SelectItem>
              <SelectItem value="recipe-instagram">Instagram Square ★4.0</SelectItem>
              <SelectItem value="recipe-tiktok">TikTok / Reel ★3.9</SelectItem>
              <SelectItem value="recipe-fast-draft">Fast Draft ★3.8</SelectItem>
            </Select>
          </div>
        </div>

        {/* GPU / Model Status Banner */}
        <GpuStatusBanners
          gpuOnline={gpuOnline}
          gpuReadyModels={gpuReadyModels}
          selectedModel={selectedModel}
          onSelectModel={setSelectedModel}
        />

        {/* Project Context Bar */}
        {projectList.length > 0 && (
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[10px] text-content-muted">Project:</span>
            <Select
              value={selectedProject || ""}
              onValueChange={(v) => onSelectProject(v === "" ? null : String(v))}
              className="rounded border border-border-default bg-surface-hover px-2 py-1 text-[11px] text-content-secondary outline-none"
            >
              <SelectItem value="">No project (standalone)</SelectItem>
              {projectList.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </Select>
            {selectedProject && (
              <span className="text-[10px] text-status-info">Saves will auto-link to this project</span>
            )}
          </div>
        )}

        {/* Main row: prompt + model + generate */}
        <PromptEditor
          prompt={prompt}
          onPromptChange={setPrompt}
          onGenerate={img.handleGenerate}
          generating={img.generating}
          selectedModel={selectedModel}
          onSelectModel={setSelectedModel}
          imageModelList={imageModelList}
          gpuReadyModels={gpuReadyModels}
          gpuOnline={gpuOnline}
          showAdvanced={img.showAdvanced}
          onToggleAdvanced={() => img.setShowAdvanced(!img.showAdvanced)}
          batchCount={img.batchCount}
          onBatchCountChange={img.setBatchCount}
          steps={img.steps}
          width={img.width}
          height={img.height}
          favoritePrompts={favorites.favoritePrompts}
          showFavorites={favorites.showFavorites}
          onToggleFavorites={() => favorites.setShowFavorites(!favorites.showFavorites)}
          onSaveFavorite={() => favorites.saveFavorite(prompt)}
          onRemoveFavorite={favorites.removeFavorite}
        />

        {/* Advanced Panel */}
        {img.showAdvanced && (
          <AdvancedSettings
            apiBase={apiBase}
            talentList={talentList}
            selectedTalents={selectedTalents}
            onChangeTalents={onChangeTalents}
            activeLoras={img.activeLoras}
            availableLoras={availableLoras}
            onAddLora={img.addLora}
            onUpdateLoraStrength={img.updateLoraStrength}
            onRemoveLoraAt={img.removeLoraAt}
            negativePrompt={img.negativePrompt}
            onChangeNegativePrompt={img.setNegativePrompt}
            steps={img.steps}
            onChangeSteps={img.setSteps}
            cfg={img.cfg}
            onChangeCfg={img.setCfg}
            seed={img.seed}
            onChangeSeed={img.setSeed}
            width={img.width}
            onChangeWidth={img.setWidth}
            height={img.height}
            onChangeHeight={img.setHeight}
          />
        )}
      </div>

      {/* Preset Packs Browser */}
      <PresetPacks presets={presets} workerVram={workerVram} onApplyPreset={img.applyPreset} />

      {/* Progress / Result Display / Batch Results Grid */}
      <GenerationResultPanel
        generating={img.generating}
        result={img.result}
        batchResults={img.batchResults}
        selectedModel={selectedModel}
        width={img.width}
        height={img.height}
        onCancel={img.cancelGeneration}
        selectedStyle={selectedStyle}
        prompt={prompt}
        savedToLibrary={img.savedToLibrary}
        savingToLibrary={img.savingToLibrary}
        onSaveToLibrary={() => img.saveToLibrary(selectedProject)}
      />

      {/* Generation History Gallery */}
      {generationHistory.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-content-primary mb-3">Recent Generations</h3>
          <div className="grid grid-cols-4 gap-3">
            {generationHistory.map((job, idx) => {
              const input = (job.input as Record<string, unknown>) || {};
              const jobPrompt = String(input.prompt || job.prompt || "");
              return (
                <button
                  key={(job.id as string) || idx}
                  onClick={() => {
                    if (jobPrompt) setPrompt(jobPrompt);
                    if (input.model) setSelectedModel(String(input.model));
                  }}
                  className="rounded-xl border border-border-subtle bg-surface-raised p-3 text-left hover:border-purple-500/30 transition-all"
                >
                  <div className="aspect-square rounded-lg bg-gradient-to-br from-purple-900/30 to-blue-900/30 mb-2 flex items-center justify-center">
                    <ImageIcon className="h-6 w-6 text-gray-700" />
                  </div>
                  <p className="text-[10px] text-content-tertiary line-clamp-2">{jobPrompt.slice(0, 60) || "Generation"}</p>
                  <p className="text-[9px] text-content-muted mt-1">{String(input.model || job.type || "")}</p>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
