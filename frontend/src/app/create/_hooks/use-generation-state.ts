"use client";

import { useState, useCallback } from "react";

export interface GenerationResult {
  image_base64?: string;
  filename?: string;
  generation_time?: number;
  error?: string;
  saved_to?: string;
  estimated_cost?: number;
  seed?: number;
}

export interface GenerationSettings {
  prompt: string;
  negativePrompt: string;
  model: string;
  steps: number;
  cfg: number;
  seed: number;
  width: number;
  height: number;
  batchCount: number;
  loras: { id: string; name: string; strength: number }[];
  controlType: string;
  controlStrength: number;
}

const DEFAULT_SETTINGS: GenerationSettings = {
  prompt: "",
  negativePrompt: "",
  model: "flux2-klein",
  steps: 20,
  cfg: 7.5,
  seed: -1,
  width: 1024,
  height: 1024,
  batchCount: 1,
  loras: [],
  controlType: "none",
  controlStrength: 0.7,
};

/**
 * Hook: Generation state machine for the Create page.
 * Manages settings, execution state, results, and history.
 */
export function useGenerationState() {
  const [settings, setSettings] = useState<GenerationSettings>(DEFAULT_SETTINGS);
  const [generating, setGenerating] = useState(false);
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [batchResults, setBatchResults] = useState<GenerationResult[]>([]);
  const [history, setHistory] = useState<GenerationResult[]>([]);

  const updateSetting = useCallback(<K extends keyof GenerationSettings>(
    key: K,
    value: GenerationSettings[K],
  ) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }, []);

  const resetSettings = useCallback(() => {
    setSettings(DEFAULT_SETTINGS);
  }, []);

  const startGeneration = useCallback(() => {
    const controller = new AbortController();
    setAbortController(controller);
    setGenerating(true);
    setResult(null);
    setBatchResults([]);
    return controller;
  }, []);

  const completeGeneration = useCallback((res: GenerationResult) => {
    setResult(res);
    setGenerating(false);
    setAbortController(null);
    if (!res.error) {
      setHistory((prev) => [res, ...prev].slice(0, 50));
    }
  }, []);

  const completeBatch = useCallback((results: GenerationResult[]) => {
    setBatchResults(results);
    setGenerating(false);
    setAbortController(null);
    const successes = results.filter((r) => !r.error);
    if (successes.length > 0) {
      setHistory((prev) => [...successes, ...prev].slice(0, 50));
    }
  }, []);

  const cancelGeneration = useCallback(() => {
    abortController?.abort();
    setGenerating(false);
    setAbortController(null);
  }, [abortController]);

  return {
    settings,
    updateSetting,
    resetSettings,
    generating,
    result,
    batchResults,
    history,
    startGeneration,
    completeGeneration,
    completeBatch,
    cancelGeneration,
  };
}
