"use client";

import { useState, useEffect } from "react";
import { getBrainHealth } from "@/lib/api";

/**
 * Brain health status, derived from /api/v1/brain/health:
 * - "healthy":  primary provider connected and serving models
 * - "degraded": service answers only via a fallback provider, or the
 *               provider is reachable but has no models loaded
 * - "offline":  request failed or no provider is reachable
 */
export type BrainHealthStatus = "healthy" | "degraded" | "offline";

type HealthPayload = Record<string, unknown>;

function deriveStatus(data: HealthPayload | null): BrainHealthStatus {
  if (!data || data.connected !== true) {
    // Primary down — but chat() falls back to other providers when available,
    // so an available fallback means degraded rather than offline.
    const fallbacks = Array.isArray(data?.fallbacks) ? data.fallbacks : [];
    const fallbackAvailable = fallbacks.some(
      (f) => f && typeof f === "object" && (f as HealthPayload).available === true
    );
    return fallbackAvailable ? "degraded" : "offline";
  }
  // Provider reachable: ollama reports its loaded models — empty means it
  // cannot serve anything yet.
  if (Array.isArray(data.available_models) && data.available_models.length === 0) {
    return "degraded";
  }
  return "healthy";
}

/**
 * Hook: Brain health polling.
 * Checks /api/v1/brain/health every 10s and exposes a tri-state status.
 */
export function useBrainHealth() {
  const [status, setStatus] = useState<BrainHealthStatus>("offline");
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const checkHealth = () => {
      getBrainHealth()
        .then((d) => {
          if (cancelled) return;
          setHealth(d);
          setStatus(deriveStatus(d));
          setError(null);
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          setHealth(null);
          setStatus("offline");
          setError(e instanceof Error ? e.message : "Brain unreachable");
        });
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return { status, brainOnline: status !== "offline", health, error };
}
