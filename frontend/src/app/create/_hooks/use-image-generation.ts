"use client";

import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { useToast } from "@/components/toast";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface GenerationResult {
  image_base64?: string;
  filename?: string;
  generation_time?: number;
  error?: string;
  saved_to?: string;
  estimated_cost?: number;
  seed?: number;
}

export interface ActiveLora {
  id: string;
  name: string;
  strength: number;
}

/**
 * Image generation execution state + handlers for the Create page.
 * Owns generation settings, run state, results, and preset application.
 */
export function useImageGeneration({
  prompt,
  setPrompt,
  setSelectedModel,
  selectedModel,
  selectedStyle,
  selectedTalents,
  gpuReadyModels,
  talentList,
}: {
  prompt: string;
  setPrompt: Dispatch<SetStateAction<string>>;
  setSelectedModel: (model: string) => void;
  selectedModel: string;
  selectedStyle: string;
  selectedTalents: string[];
  gpuReadyModels: Set<string>;
  talentList: { id: string; name: string; trigger_words?: string; avatar_url?: string; visual_style?: string }[];
}) {
  const { show } = useToast();
  const [generating, setGenerating] = useState(false);
  const [generationAbort, setGenerationAbort] = useState<AbortController | null>(null);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [batchResults, setBatchResults] = useState<GenerationResult[]>([]);
  const [batchCount, setBatchCount] = useState(1);
  const [savedToLibrary, setSavedToLibrary] = useState<string | null>(null);
  const [savingToLibrary, setSavingToLibrary] = useState(false);

  // Advanced panel
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [activeLoras, setActiveLoras] = useState<ActiveLora[]>([]);
  const [negativePrompt, setNegativePrompt] = useState("");
  const [steps, setSteps] = useState(20);
  const [cfg, setCfg] = useState(7.5);
  const [seed, setSeed] = useState(-1);
  const [width, setWidth] = useState(1024);
  const [height, setHeight] = useState(1024);

  // Sync defaults when model changes
  useEffect(() => {
    const defaults: Record<string, { steps: number; cfg: number; width: number; height: number }> = {
      "flux2-dev": { steps: 20, cfg: 1.0, width: 1024, height: 1024 },
      "flux2-klein": { steps: 4, cfg: 1.0, width: 1024, height: 1024 },
      "sdxl-turbo": { steps: 1, cfg: 1.0, width: 512, height: 512 },
      "flux-dev": { steps: 20, cfg: 1.0, width: 1024, height: 1024 },
      "sd15": { steps: 20, cfg: 7.5, width: 512, height: 512 },
    };
    const d = defaults[selectedModel];
    if (d) { setSteps(d.steps); setCfg(d.cfg); setWidth(d.width); setHeight(d.height); }
  }, [selectedModel]);

  // Auto-inject talent LoRA when talent is selected
  useEffect(() => {
    if (selectedTalents.length === 0) return;
    const talentId = selectedTalents[0];
    // Fetch this talent's LoRAs and auto-activate the first one
    fetch(`${API_BASE}/api/v1/talent/${talentId}/loras`)
      .then((r) => r.json())
      .then((data) => {
        const versions = (data?.trained_versions || []) as { id: string; name?: string; version_name?: string; lora_file_key?: string }[];
        if (versions.length > 0) {
          const lora = versions[0];
          const loraId = lora.id || lora.lora_file_key || "";
          const loraName = lora.name || lora.version_name || "Talent LoRA";
          // Add to active LoRAs if not already there
          setActiveLoras((prev) => {
            if (prev.some((l) => l.id === loraId)) return prev;
            return [...prev, { id: loraId, name: loraName, strength: 0.8 }];
          });
        }
        // Also check for talent's trigger words and prepend to prompt
        const talent = talentList.find((t) => t.id === talentId);
        if (talent?.trigger_words && !prompt.includes(talent.trigger_words)) {
          setPrompt((prev) => prev ? `${talent.trigger_words}, ${prev}` : talent.trigger_words || "");
        }
      })
      .catch(() => {}); // Non-blocking — LoRA injection is optional
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTalents]);

  async function handleGenerate() {
    if (!prompt.trim() || generating) return;
    setGenerating(true);
    setResult(null);
    setBatchResults([]);
    setSavedToLibrary(null);

    // Pre-flight: check model availability before wasting time on a doomed request
    if (!gpuReadyModels.has(selectedModel)) {
      try {
        const pfResp = await fetch(`${API_BASE}/api/v1/generate/preflight?model=${encodeURIComponent(selectedModel)}`);
        const pfData = await pfResp.json();
        if (!pfData.ready) {
          const available = (pfData.available_models as string[]) || [];
          const suggestion = available.length > 0
            ? ` Try: ${available.join(", ")}.`
            : " Launch a GPU worker from Admin → GPU.";
          setResult({ error: pfData.message || `Model '${selectedModel}' is not available.${suggestion}` });
          setGenerating(false);
          return;
        }
      } catch {
        // Pre-flight failed — let the main request handle it
      }
    }

    // Auto-configure via AIOS Workflow Intelligence if model is default
    let finalModel = selectedModel;
    let finalSteps = steps;
    let finalCfg = cfg;
    let finalWidth = width;
    let finalHeight = height;
    let finalNegative = negativePrompt;

    // Apply recipe params if a recipe is selected (not "auto")
    if (selectedStyle && selectedStyle.startsWith("recipe-")) {
      try {
        const recipeResp = await fetch(`${API_BASE}/api/v1/recipes/${selectedStyle}`);
        if (recipeResp.ok) {
          const recipe = await recipeResp.json();
          finalModel = recipe.model || finalModel;
          finalSteps = recipe.steps || finalSteps;
          finalCfg = recipe.cfg || finalCfg;
          if (recipe.negative_prompt) finalNegative = recipe.negative_prompt;
          if (recipe.width) finalWidth = recipe.width;
          if (recipe.height) finalHeight = recipe.height;
          // Record recipe usage
          fetch(`${API_BASE}/api/v1/recipes/${selectedStyle}/use`, { method: "POST" }).catch(() => {});
        }
      } catch {
        // Recipe fetch failed — use manual settings
      }
    }

    try {
      const configResp = await fetch(`${API_BASE}/aios/v1/workflow/configure`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          talent_id: selectedTalents[0] || undefined,
          content_type: "image",
          quality: "auto",
        }),
      });
      if (configResp.ok) {
        const config = await configResp.json();
        // Only apply auto-config if user hasn't manually overridden
        if (!negativePrompt && config.negative_prompt) finalNegative = config.negative_prompt;
        // Use auto-config model/steps/cfg if user left defaults
        finalModel = selectedModel || config.model;
        finalSteps = steps || config.steps;
        finalCfg = cfg || config.cfg;
        finalWidth = width || config.width;
        finalHeight = height || config.height;
      }
    } catch {
      // Auto-config failure is non-blocking — proceed with manual settings
    }

    try {
      const payload: Record<string, unknown> = {
        prompt,
        model: finalModel,
        negative_prompt: finalNegative || undefined,
        steps: finalSteps,
        cfg: finalCfg,
        seed,
        width: finalWidth,
        height: finalHeight,
        talent_ids: selectedTalents,
      };
      if (activeLoras.length > 0) {
        payload.loras = activeLoras.map((l) => ({ id: l.id, strength: l.strength }));
      }

      const controller = new AbortController();
      setGenerationAbort(controller);

      const resp = await fetch(`${API_BASE}/api/v1/generate/image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const data = await resp.json();
      if (data.success) {
        setResult(data);
      } else {
        setResult({ error: data.detail || "Generation failed" });
      }

      // Batch mode: generate additional variations with different seeds
      if (batchCount > 1 && data.success) {
        const results = [{ ...data, seed: payload.seed }];
        for (let i = 1; i < batchCount; i++) {
          const batchSeed = Math.floor(Math.random() * 999999999);
          try {
            const bResp = await fetch(`${API_BASE}/api/v1/generate/image`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ...payload, seed: batchSeed }),
            });
            const bData = await bResp.json();
            results.push({ ...bData, seed: batchSeed });
          } catch {
            results.push({ error: "Request failed", seed: batchSeed });
          }
        }
        setBatchResults(results);
      }
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        // User cancelled — already handled by the Cancel button
      } else {
        setResult({ error: "Cannot reach backend. Is ComfyUI worker running?" });
      }
    } finally {
      setGenerating(false);
      setGenerationAbort(null);
    }
  }

  function cancelGeneration() {
    generationAbort?.abort();
    setGenerating(false);
    setResult({ error: "Generation cancelled." });
  }

  function addLora(lora: ActiveLora) {
    setActiveLoras((prev) => {
      if (prev.find((a) => a.id === lora.id)) return prev;
      return [...prev, lora];
    });
  }

  function updateLoraStrength(index: number, strength: number) {
    setActiveLoras((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], strength };
      return updated;
    });
  }

  function removeLoraAt(index: number) {
    setActiveLoras((prev) => prev.filter((_, i) => i !== index));
  }

  function applyPreset(preset: Record<string, unknown>) {
    // Apply preset settings
    const d = (preset.defaults as Record<string, unknown>) || {};
    setSelectedModel((preset.model as string) || "sdxl-turbo");
    if (d.steps) setSteps(d.steps as number);
    if (d.cfg) setCfg(d.cfg as number);
    if (d.width) setWidth(d.width as number);
    if (d.height) setHeight(d.height as number);
    if (preset.negative_prompt) setNegativePrompt(preset.negative_prompt as string);
    if (preset.prompt_template) {
      setPrompt((preset.prompt_template as string).replace(/\{[^}]+\}/g, ""));
    }
    setShowAdvanced(true);
  }

  async function saveToLibrary(projectId: string | null): Promise<void> {
    if (!result?.image_base64 || savingToLibrary) return;
    setSavingToLibrary(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/assets/save-generation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_base64: result.image_base64,
          prompt,
          model: selectedModel,
          seed,
          width,
          height,
          talent_ids: selectedTalents,
          project_id: projectId || undefined,
          filename: result.filename,
        }),
      });
      const data = await resp.json();
      if (data.success) {
        setSavedToLibrary(data.asset?.id || "saved");
      } else {
        show(data.detail || "Failed to save", "error");
      }
    } catch {
      show("Could not reach backend. Is it running?", "error");
    } finally {
      setSavingToLibrary(false);
    }
  }

  return {
    generating,
    result,
    batchResults,
    batchCount,
    setBatchCount,
    savedToLibrary,
    savingToLibrary,
    showAdvanced,
    setShowAdvanced,
    activeLoras,
    negativePrompt,
    setNegativePrompt,
    steps,
    setSteps,
    cfg,
    setCfg,
    seed,
    setSeed,
    width,
    setWidth,
    height,
    setHeight,
    handleGenerate,
    cancelGeneration,
    addLora,
    updateLoraStrength,
    removeLoraAt,
    applyPreset,
    saveToLibrary,
  };
}
