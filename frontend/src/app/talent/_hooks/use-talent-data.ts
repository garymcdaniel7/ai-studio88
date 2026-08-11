"use client";

import { useState, useEffect, useCallback } from "react";
import { getTalent, createTalent, deleteTalent, updateTalent } from "@/lib/api";

export type TalentRecord = Record<string, unknown>;

/**
 * Hook: Talent data loading, CRUD, and favorites.
 */
export function useTalentData() {
  const [talentData, setTalentData] = useState<TalentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTalent, setSelectedTalent] = useState<TalentRecord | null>(null);

  const loadTalent = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getTalent();
      const items = Array.isArray(data) ? data : [];
      const favs = JSON.parse(localStorage.getItem("talent_favorites") || "[]") as string[];
      items.sort((a, b) => {
        const aFav = favs.includes(a.id as string) ? 0 : 1;
        const bFav = favs.includes(b.id as string) ? 0 : 1;
        return aFav - bFav;
      });
      setTalentData(items);
      if (items.length > 0 && !selectedTalent) setSelectedTalent(items[0]);
    } catch {
      setTalentData([]);
    } finally {
      setLoading(false);
    }
  }, [selectedTalent]);

  useEffect(() => { loadTalent(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCreate(name: string, bio: string): Promise<boolean> {
    if (!name.trim()) return false;
    try {
      await createTalent({ name, bio });
      await loadTalent();
      return true;
    } catch {
      return false;
    }
  }

  async function handleDelete(id: string): Promise<boolean> {
    try {
      await deleteTalent(id);
      setTalentData((prev) => prev.filter((t) => t.id !== id));
      if (selectedTalent?.id === id) setSelectedTalent(null);
      return true;
    } catch {
      return false;
    }
  }

  async function handleUpdate(id: string, updates: Record<string, unknown>): Promise<boolean> {
    try {
      await updateTalent(id, updates);
      await loadTalent();
      return true;
    } catch {
      return false;
    }
  }

  function toggleFavorite(id: string) {
    const favs = JSON.parse(localStorage.getItem("talent_favorites") || "[]") as string[];
    const updated = favs.includes(id) ? favs.filter((f) => f !== id) : [...favs, id];
    localStorage.setItem("talent_favorites", JSON.stringify(updated));
    loadTalent();
  }

  function isFavorite(id: string): boolean {
    const favs = JSON.parse(localStorage.getItem("talent_favorites") || "[]") as string[];
    return favs.includes(id);
  }

  return {
    talentData,
    loading,
    selectedTalent,
    setSelectedTalent,
    handleCreate,
    handleDelete,
    handleUpdate,
    toggleFavorite,
    isFavorite,
    reload: loadTalent,
  };
}
