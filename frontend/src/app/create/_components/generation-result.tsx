"use client";

import { Loader2 } from "lucide-react";
import { FeedbackButtons } from "@/components/feedback-buttons";
import type { GenerationResult } from "../_hooks/use-generation-state";

interface GenerationResultProps {
  generating: boolean;
  result: GenerationResult | null;
  batchResults: GenerationResult[];
  onSaveToLibrary?: (result: GenerationResult) => void;
}

/**
 * Generation output display — single result or batch grid.
 */
export function GenerationResultPanel({
  generating,
  result,
  batchResults,
  onSaveToLibrary,
}: GenerationResultProps) {
  if (generating) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <Loader2 className="h-8 w-8 text-purple-400 animate-spin" />
        <p className="text-sm text-gray-400">Generating...</p>
      </div>
    );
  }

  // Batch results
  if (batchResults.length > 1) {
    return (
      <div className="grid grid-cols-2 gap-3 p-4 overflow-y-auto">
        {batchResults.map((r, i) => (
          <div key={i} className="rounded-lg border border-white/[0.06] overflow-hidden">
            {r.image_base64 ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`data:image/png;base64,${r.image_base64}`}
                  alt={`Variation ${i + 1}`}
                  className="w-full aspect-square object-cover"
                />
                <div className="flex items-center justify-between px-2 py-1.5 bg-white/[0.02]">
                  <span className="text-[10px] text-gray-500">
                    {r.generation_time ? `${r.generation_time.toFixed(1)}s` : ""}
                    {r.seed ? ` · seed: ${r.seed}` : ""}
                  </span>
                  {onSaveToLibrary && (
                    <button
                      onClick={() => onSaveToLibrary(r)}
                      className="text-[10px] text-purple-400 hover:text-purple-300"
                    >
                      Save
                    </button>
                  )}
                </div>
              </>
            ) : r.error ? (
              <div className="p-3">
                <p className="text-xs text-red-400">{r.error}</p>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    );
  }

  // Single result
  if (result?.image_base64) {
    return (
      <div className="flex flex-col items-center gap-3 p-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`data:image/png;base64,${result.image_base64}`}
          alt="Generated"
          className="max-w-full max-h-[500px] rounded-xl border border-white/[0.06]"
        />
        <div className="flex items-center gap-4 text-xs text-gray-500">
          {result.generation_time && <span>{result.generation_time.toFixed(1)}s</span>}
          {result.estimated_cost != null && <span>${result.estimated_cost.toFixed(4)}</span>}
          {result.filename && <span>{result.filename}</span>}
        </div>
        <FeedbackButtons agent="generation" outputType="image" context={{ filename: result.filename }} />
        {onSaveToLibrary && (
          <button
            onClick={() => onSaveToLibrary(result)}
            className="rounded-lg bg-purple-600/20 px-4 py-2 text-xs font-medium text-purple-400 hover:bg-purple-600/30"
          >
            Save to Library
          </button>
        )}
      </div>
    );
  }

  if (result?.error) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-red-400">{result.error}</p>
      </div>
    );
  }

  // Empty state
  return (
    <div className="flex flex-col items-center justify-center h-full gap-2">
      <p className="text-sm text-gray-500">Enter a prompt and generate</p>
      <p className="text-xs text-gray-600">Results will appear here</p>
    </div>
  );
}
