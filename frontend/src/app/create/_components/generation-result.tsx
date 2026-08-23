"use client";

import { Loader2, Sparkles } from "lucide-react";
import { FeedbackButtons } from "@/components/feedback-buttons";
import type { GenerationResult } from "../_hooks/use-image-generation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface GenerationResultProps {
  generating: boolean;
  result: GenerationResult | null;
  batchResults: GenerationResult[];
  // Progress + feedback context
  selectedModel: string;
  width: number;
  height: number;
  onCancel: () => void;
  selectedStyle: string;
  prompt: string;
  // Save to Library
  savedToLibrary: string | null;
  savingToLibrary: boolean;
  onSaveToLibrary: () => void;
}

/**
 * Image generation output — progress card, single result (with save/download),
 * or batch variations grid.
 */
export function GenerationResultPanel({
  generating,
  result,
  batchResults,
  selectedModel,
  width,
  height,
  onCancel,
  selectedStyle,
  prompt,
  savedToLibrary,
  savingToLibrary,
  onSaveToLibrary,
}: GenerationResultProps) {
  return (
    <>
      {/* Generation Progress */}
      {generating && (
        <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-6">
          <div className="flex items-center gap-4 mb-4">
            <div className="relative">
              <Loader2 className="h-10 w-10 animate-spin text-purple-500" />
              <Sparkles className="h-4 w-4 text-purple-300 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
            </div>
            <div>
              <p className="text-sm font-medium text-purple-300">Generating with {selectedModel}</p>
              <p className="text-xs text-gray-500">
                {selectedModel === "sdxl-turbo" ? "~3-5 seconds (1 step)" :
                 selectedModel === "flux2-klein" ? "~8-12 seconds (4 steps)" :
                 selectedModel === "flux-dev" ? "~45-60 seconds (20 steps)" :
                 "Processing..."}
              </p>
            </div>
          </div>
          {/* Animated progress bar */}
          <div className="w-full h-1.5 bg-surface-active rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-purple-600 to-purple-400 rounded-full animate-pulse" style={{ width: "60%", animation: "progress 2s ease-in-out infinite" }} />
          </div>
          <div className="mt-3 flex items-center justify-between text-[10px] text-content-muted">
            <span>Model: {selectedModel} • {width}x{height}</span>
            <button
              onClick={onCancel}
              className="text-[11px] text-red-400 hover:text-red-300 underline"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Result Display */}
      {result && !generating && (
        <div className="rounded-xl border border-border-subtle bg-surface-raised p-6">
          {result.error ? (
            <div className="text-center py-4">
              <p className="text-sm text-status-error">{result.error}</p>
              <p className="text-xs text-content-muted mt-1">Make sure a GPU worker is running with the model loaded.</p>
            </div>
          ) : result.image_base64 ? (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-content-primary">Generated Image</h3>
                <span className="text-xs text-content-muted">{result.generation_time}s • {result.filename}</span>
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`data:image/png;base64,${result.image_base64}`}
                alt="Generated content"
                className="rounded-lg w-full max-w-lg mx-auto"
              />
              {result.saved_to && (
                <div className="mt-3 flex items-center justify-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-lg bg-green-500/10 border border-green-500/20 px-3 py-1.5">
                    <svg className="h-3.5 w-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                    <span className="text-[11px] text-green-400 font-medium">Saved</span>
                  </span>
                  {typeof window !== "undefined" && window.location.hostname === "localhost" ? (
                    <button
                      onClick={() => {
                        // Open folder in Finder (calls backend endpoint)
                        fetch(`${API_BASE}/api/v1/generate/open-folder`, { method: "POST" }).catch(() => {});
                      }}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] px-3 py-1.5 text-[11px] text-gray-300 hover:text-white hover:bg-white/[0.08] transition-colors"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z" /></svg>
                      Open Folder
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        const link = document.createElement("a");
                        link.href = `data:image/png;base64,${result.image_base64}`;
                        link.download = result.filename || "generated.png";
                        link.click();
                      }}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] px-3 py-1.5 text-[11px] text-gray-300 hover:text-white hover:bg-white/[0.08] transition-colors"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                      Download
                    </button>
                  )}
                </div>
              )}
              {result.estimated_cost !== undefined && result.estimated_cost > 0 && (
                <p className="text-[10px] text-content-muted mt-2 text-center">
                  Cost: ${(result.estimated_cost as number).toFixed(5)}
                </p>
              )}
              {/* Feedback — helps the AI learn what works */}
              <div className="mt-3 flex justify-center">
                <FeedbackButtons
                  agent="akose"
                  outputType="generation"
                  context={{ model: selectedModel, recipe: selectedStyle, prompt: prompt.slice(0, 100) }}
                  compact
                />
              </div>
              {/* Save to Library */}
              <div className="mt-3 flex justify-center">
                {savedToLibrary ? (
                  <a
                    href="/assets"
                    className="inline-flex items-center gap-2 rounded-lg bg-green-500/10 border border-green-500/30 px-4 py-2 text-sm text-green-400 hover:bg-green-500/20 transition-colors"
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                    Saved to Library — View in Assets
                  </a>
                ) : (
                  <button
                    onClick={onSaveToLibrary}
                    disabled={savingToLibrary}
                    className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 transition-colors"
                  >
                    {savingToLibrary ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
                    )}
                    {savingToLibrary ? "Saving..." : "Save to Library"}
                  </button>
                )}
              </div>
            </div>
          ) : null}
        </div>
      )}

      {/* Batch Results Grid */}
      {batchResults.length > 1 && !generating && (
        <div className="rounded-xl border border-border-subtle bg-surface-raised p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-content-primary">{batchResults.length} Variations</h3>
            <span className="text-[10px] text-content-muted">Same prompt, different seeds</span>
          </div>
          <div className={`grid gap-3 ${batchResults.length <= 2 ? "grid-cols-2" : "grid-cols-2 md:grid-cols-4"}`}>
            {batchResults.map((br, idx) => (
              <div key={idx} className="rounded-lg border border-border-subtle overflow-hidden bg-surface-hover">
                {br.image_base64 ? (
                  <div className="relative group">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`data:image/png;base64,${br.image_base64}`}
                      alt={`Variation ${idx + 1}`}
                      className="w-full aspect-square object-cover"
                    />
                    <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <p className="text-[9px] text-gray-300">Seed: {br.seed} • {br.generation_time}s</p>
                    </div>
                  </div>
                ) : (
                  <div className="aspect-square flex items-center justify-center">
                    <p className="text-[10px] text-red-400">{br.error || "Failed"}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
