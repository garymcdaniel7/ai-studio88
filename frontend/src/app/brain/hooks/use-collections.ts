"use client";

import { useState, useEffect, useCallback } from "react";
import type { Collection } from "../types";
import { COLLECTION_COLORS } from "../constants";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Hook: Brain collections CRUD with localStorage cache + backend sync.
 */
export function useCollections() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [filterCollection, setFilterCollection] = useState<string | null>(null);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("brain_collections");
      if (saved) setCollections(JSON.parse(saved));
    } catch {
      // Ignore parse errors
    }
  }, []);

  // Persist to localStorage when collections change
  useEffect(() => {
    localStorage.setItem("brain_collections", JSON.stringify(collections));
  }, [collections]);

  const createCollection = useCallback((name: string) => {
    if (!name.trim()) return;
    const newCol: Collection = {
      id: crypto.randomUUID(),
      name: name.trim(),
      color: COLLECTION_COLORS[collections.length % COLLECTION_COLORS.length],
      conversationIds: [],
    };
    setCollections((prev) => [...prev, newCol]);

    // Sync to backend (non-blocking)
    fetch(`${API_BASE}/api/v1/brain/collections`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newCol.name, color: newCol.color }),
    }).catch(() => {});
  }, [collections.length]);

  const addToCollection = useCallback((sessionId: string, collectionId: string) => {
    setCollections((prev) =>
      prev.map((c) =>
        c.id === collectionId && !c.conversationIds.includes(sessionId)
          ? { ...c, conversationIds: [...c.conversationIds, sessionId] }
          : c
      )
    );
  }, []);

  return {
    collections,
    filterCollection,
    setFilterCollection,
    createCollection,
    addToCollection,
  };
}
