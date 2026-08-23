"use client";

import { useState, useEffect } from "react";
import type { BrainMemory } from "../types";
import { authFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Hook: Brain memory fetching.
 * Loads persistent memory preferences from backend on mount.
 */
export function useBrainMemory() {
  const [brainMemory, setBrainMemory] = useState<BrainMemory | null>(null);

  useEffect(() => {
    authFetch(`${API_BASE}/api/v1/brain/memory`)
      .then((r) => r.json())
      .then((data) => setBrainMemory(data as BrainMemory))
      .catch(() => setBrainMemory(null));
  }, []);

  return { brainMemory };
}
