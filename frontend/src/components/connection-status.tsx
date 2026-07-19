"use client";

import { useEffect, useState } from "react";
import { WifiOff, RefreshCw } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * ConnectionStatus — Global health check banner.
 *
 * Checks backend connectivity on mount and periodically.
 * Shows a full-width banner when the backend is unreachable.
 * Auto-dismisses when connection is restored.
 */
export function ConnectionStatus() {
  const [online, setOnline] = useState<boolean | null>(null); // null = checking
  const [checking, setChecking] = useState(false);

  async function checkHealth() {
    setChecking(true);
    try {
      const resp = await fetch(`${API_BASE}/`, {
        signal: AbortSignal.timeout(5000),
      });
      setOnline(resp.ok);
    } catch {
      setOnline(false);
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    checkHealth();
    // Re-check every 30 seconds
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  // Don't show anything while first checking or when online
  if (online === null || online === true) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-[100] bg-red-900/95 border-b border-red-500/50 px-4 py-2.5 flex items-center justify-center gap-3 backdrop-blur-sm">
      <WifiOff className="h-4 w-4 text-red-300 shrink-0" />
      <span className="text-sm text-red-200">
        Backend offline — cannot reach API at <code className="text-red-300">{API_BASE}</code>
      </span>
      <button
        onClick={checkHealth}
        disabled={checking}
        className="flex items-center gap-1.5 rounded bg-red-800 px-2.5 py-1 text-xs text-red-200 hover:bg-red-700 disabled:opacity-50"
      >
        <RefreshCw className={`h-3 w-3 ${checking ? "animate-spin" : ""}`} />
        Retry
      </button>
      <span className="text-[10px] text-red-400 ml-2">
        Start backend: <code>uv run uvicorn backend.main:app --reload</code>
      </span>
    </div>
  );
}
