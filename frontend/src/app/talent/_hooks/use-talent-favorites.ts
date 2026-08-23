"use client";

const FAVORITES_KEY = "talent_favorites";

/**
 * localStorage-backed talent favorites. Kept as plain helpers so callers
 * control re-render/refresh semantics (favorites affect sort order).
 */
export function readFavorites(): string[] {
  return JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]") as string[];
}

export function isFavorite(id: string): boolean {
  return readFavorites().includes(id);
}

/** Toggles a favorite and returns the updated list. */
export function toggleFavorite(id: string): string[] {
  const favs = readFavorites();
  const updated = favs.includes(id) ? favs.filter((f) => f !== id) : [id, ...favs];
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(updated));
  return updated;
}
