"use client";

import { useState } from "react";
import { Sparkles, Star, ChevronDown } from "lucide-react";

interface PromptEditorProps {
  prompt: string;
  onPromptChange: (prompt: string) => void;
  onGenerate: () => void;
  generating: boolean;
  onCancel?: () => void;
}

/**
 * Prompt input with favorites, enhance button, and submit.
 */
export function PromptEditor({
  prompt,
  onPromptChange,
  onGenerate,
  generating,
  onCancel,
}: PromptEditorProps) {
  const [favorites, setFavorites] = useState<{ text: string; savedAt: string }[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("favorite_prompts") || "[]");
    } catch { return []; }
  });
  const [showFavorites, setShowFavorites] = useState(false);

  function saveFavorite() {
    if (!prompt.trim()) return;
    const updated = [{ text: prompt, savedAt: new Date().toISOString() }, ...favorites].slice(0, 20);
    setFavorites(updated);
    localStorage.setItem("favorite_prompts", JSON.stringify(updated));
  }

  function loadFavorite(text: string) {
    onPromptChange(text);
    setShowFavorites(false);
  }

  return (
    <div className="space-y-2">
      {/* Prompt textarea */}
      <div className="relative">
        <textarea
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          placeholder="Describe what you want to create..."
          rows={4}
          className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 placeholder:text-gray-600 outline-none resize-none focus:border-purple-500/50"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              if (!generating) onGenerate();
            }
          }}
        />
        {/* Favorites toggle */}
        <button
          onClick={() => setShowFavorites(!showFavorites)}
          className="absolute top-2 right-2 p-1.5 rounded text-gray-500 hover:text-amber-400"
          title="Saved prompts"
        >
          <Star className="h-3.5 w-3.5" fill={favorites.length > 0 ? "currentColor" : "none"} />
        </button>
      </div>

      {/* Favorites dropdown */}
      {showFavorites && favorites.length > 0 && (
        <div className="rounded-lg border border-white/[0.08] bg-[#12122a] p-2 max-h-40 overflow-y-auto">
          {favorites.map((fav, i) => (
            <button
              key={i}
              onClick={() => loadFavorite(fav.text)}
              className="w-full text-left px-2 py-1.5 rounded text-xs text-gray-300 hover:bg-white/[0.04] truncate"
            >
              {fav.text}
            </button>
          ))}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <button
          onClick={onGenerate}
          disabled={!prompt.trim() || generating}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Sparkles className="h-4 w-4" />
          {generating ? "Generating..." : "Generate"}
        </button>
        {generating && onCancel && (
          <button
            onClick={onCancel}
            className="rounded-lg border border-white/[0.08] px-4 py-2 text-sm text-gray-400 hover:text-white"
          >
            Cancel
          </button>
        )}
        <button
          onClick={saveFavorite}
          disabled={!prompt.trim()}
          className="rounded-lg border border-white/[0.08] px-3 py-2 text-xs text-gray-400 hover:text-amber-400 disabled:opacity-30"
          title="Save prompt"
        >
          <Star className="h-3.5 w-3.5" />
        </button>
        <span className="ml-auto text-[10px] text-gray-600">⌘+Enter to generate</span>
      </div>
    </div>
  );
}
