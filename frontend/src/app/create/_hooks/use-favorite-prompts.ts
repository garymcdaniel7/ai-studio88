"use client";

import { useEffect, useState } from "react";

/**
 * Favorite prompts with localStorage persistence (key: "favorite_prompts").
 */
export function useFavoritePrompts() {
  const [favoritePrompts, setFavoritePrompts] = useState<{ text: string; savedAt: string }[]>([]);
  const [showFavorites, setShowFavorites] = useState(false);

  // Load favorite prompts from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("favorite_prompts");
      if (saved) setFavoritePrompts(JSON.parse(saved));
    } catch {}
  }, []);

  function saveFavorite(prompt: string) {
    if (!prompt.trim()) return;
    const updated = [{ text: prompt.trim(), savedAt: new Date().toISOString() }, ...favoritePrompts.filter((f) => f.text !== prompt.trim())].slice(0, 50);
    setFavoritePrompts(updated);
    localStorage.setItem("favorite_prompts", JSON.stringify(updated));
  }

  function removeFavorite(text: string) {
    const updated = favoritePrompts.filter((f) => f.text !== text);
    setFavoritePrompts(updated);
    localStorage.setItem("favorite_prompts", JSON.stringify(updated));
  }

  return {
    favoritePrompts,
    showFavorites,
    setShowFavorites,
    saveFavorite,
    removeFavorite,
  };
}
