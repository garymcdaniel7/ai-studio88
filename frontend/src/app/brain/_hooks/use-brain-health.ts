"use client";

import { useState, useEffect } from "react";
import { getBrainHealth } from "@/lib/api";

/**
 * Hook: Brain health polling.
 * Checks /brain/health every 10s and exposes online status.
 */
export function useBrainHealth() {
  const [brainOnline, setBrainOnline] = useState(false);

  useEffect(() => {
    const checkHealth = () => {
      getBrainHealth()
        .then((d) => setBrainOnline(Boolean(d.connected)))
        .catch(() => setBrainOnline(false));
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  return { brainOnline };
}
