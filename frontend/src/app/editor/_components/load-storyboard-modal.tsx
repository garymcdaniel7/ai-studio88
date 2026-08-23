"use client";

/**
 * Load Storyboard Modal — pick a previously saved storyboard.
 * Extracted verbatim from editor/page.tsx.
 */

import { XCircle } from "lucide-react";

interface LoadStoryboardModalProps {
  storyboards: Record<string, unknown>[];
  onSelect: (storyboard: Record<string, unknown>) => void;
  onClose: () => void;
}

export function LoadStoryboardModal({ storyboards, onSelect, onClose }: LoadStoryboardModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl max-h-[70vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white">Load Storyboard</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">
            <XCircle className="h-5 w-5" />
          </button>
        </div>
        {storyboards.length > 0 ? (
          <div className="space-y-2">
            {storyboards.map((sb) => (
              <button
                key={sb.id as string}
                onClick={() => onSelect(sb)}
                className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 text-left hover:border-purple-500/30"
              >
                <p className="text-sm font-medium text-white">{sb.name as string || "Untitled"}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {Array.isArray(sb.shots) ? `${(sb.shots as unknown[]).length} shots` : "0 shots"}
                  {sb.updated_at ? ` · ${new Date(sb.updated_at as string).toLocaleDateString()}` : ""}
                </p>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500 text-center py-6">No saved storyboards yet.</p>
        )}
      </div>
    </div>
  );
}
