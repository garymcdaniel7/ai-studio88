"use client";

import { AlertTriangle, Info, X, Check, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Conflict Display — renders merge conflicts, warnings, dropped overrides,
 * and hard-dependency blocks from the Preset Composer's MergeResult.
 *
 * Drop this component into any page that dispatches generation jobs.
 * It expects the output shape from backend merge_presets().
 *
 * States:
 *   idle           — no merge result yet (hidden)
 *   success        — merge complete, no conflicts/blocks (shows green check)
 *   warnings       — merge complete, warnings present (collapsible)
 *   conflicts      — merge conflicts need user resolution (blocks dispatch)
 *   blocked        — hard_dependency_blocked = true (blocks dispatch, clear message)
 */

// ─── Types ───────────────────────────────────────────────────────────

export interface Conflict {
  param: string;
  base_value: unknown;
  lora_value: unknown;
  description: string;
}

export interface MergeResult {
  resolved_params: Record<string, unknown>;
  conflicts: Conflict[];
  warnings: string[];
  dropped_overrides: string[];
  applied_layers: string[];
  hard_dependency_blocked: boolean;
}

export type ConflictDisplayState =
  | { kind: "idle" }
  | { kind: "success" }
  | { kind: "warnings"; data: MergeResult; dismissed: boolean }
  | { kind: "conflicts"; data: MergeResult }
  | { kind: "blocked"; data: MergeResult };

// ─── Conflict Display Component ─────────────────────────────────────

interface ConflictDisplayProps {
  state: ConflictDisplayState;
  onDismissWarnings?: () => void;
  onResolveConflict?: (param: string) => void;
}

export function ConflictDisplay({
  state,
  onDismissWarnings,
  onResolveConflict,
}: ConflictDisplayProps) {
  // ── Hidden when idle ───
  if (state.kind === "idle") {
    return <div className="hidden" aria-hidden="true" />;
  }

  // ── Success ───
  if (state.kind === "success") {
    return (
      <div
        className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 p-3"
        data-testid="conflict-display-success"
      >
        <Check className="h-4 w-4 text-green-400" />
        <p className="text-sm text-green-300">
          Presets merged cleanly — no conflicts.
        </p>
      </div>
    );
  }

  // ── Warnings (collapsible, can be dismissed) ───
  if (state.kind === "warnings") {
    const { data, dismissed } = state;
    if (dismissed) {
      return (
        <div
          className="flex items-center gap-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-2"
          data-testid="conflict-display-warnings-dismissed"
        >
          <Info className="h-3 w-3 text-yellow-400" />
          <p className="text-xs text-yellow-300">
            {data.warnings.length} warning(s) — dismissed
          </p>
        </div>
      );
    }

    return (
      <details
        className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3"
        data-testid="conflict-display-warnings"
        open
      >
        <summary className="flex items-center gap-2 cursor-pointer text-sm font-medium text-yellow-300">
          <Info className="h-4 w-4" />
          <span>
            {data.warnings.length} preset warning{data.warnings.length !== 1 ? "s" : ""}
          </span>
          {onDismissWarnings && (
            <button
              type="button"
              onClick={onDismissWarnings}
              className="ml-auto text-[11px] text-content-muted hover:text-content-primary transition-colors"
              aria-label="Dismiss warnings"
            >
              Dismiss
            </button>
          )}
        </summary>
        <ul className="mt-2 space-y-1">
          {data.warnings.map((w, i) => (
            <li
              key={i}
              className="flex items-start gap-2 text-xs text-yellow-200"
            >
              <ArrowRight className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{w}</span>
            </li>
          ))}
        </ul>
        {data.dropped_overrides.length > 0 && (
          <div className="mt-2 border-t border-yellow-500/20 pt-2">
            <p className="text-xs font-medium text-yellow-300">
              Dropped overrides ({data.dropped_overrides.length})
            </p>
            <ul className="mt-1 space-y-0.5">
              {data.dropped_overrides.map((o, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-[11px] text-yellow-200"
                >
                  <X className="mt-0.5 h-3 w-3 shrink-0" />
                  <span>{o}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </details>
    );
  }

  // ── Conflicts (blocks dispatch until resolved) ───
  if (state.kind === "conflicts") {
    const { data } = state;
    return (
      <div
        className="rounded-lg border border-red-500/40 bg-red-500/10 p-4"
        data-testid="conflict-display-conflicts"
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-400" />
          <p className="text-sm font-medium text-red-300">
            {data.conflicts.length} conflict{data.conflicts.length !== 1 ? "s" : ""} require resolution
          </p>
        </div>
        <p className="mt-1 text-xs text-red-200">
          Resolve all conflicts before dispatching.
        </p>
        <ul className="mt-3 space-y-2">
          {data.conflicts.map((c, i) => (
            <li
              key={i}
              className="flex flex-col gap-1 rounded-lg border border-red-500/20 bg-red-500/5 p-3"
            >
              <div className="flex items-center justify-between">
                <p className="text-xs font-mono font-medium text-red-200">
                  {c.param}
                </p>
                {onResolveConflict && (
                  <button
                    type="button"
                    onClick={() => onResolveConflict(c.param)}
                    className="text-[11px] text-content-muted hover:text-content-primary transition-colors"
                    aria-label={`Resolve conflict for ${c.param}`}
                  >
                    Resolve
                  </button>
                )}
              </div>
              <p className="text-[11px] text-red-100">{c.description}</p>
              <div className="flex items-center gap-3 mt-1 text-[11px] text-content-muted">
                <span>
                  Base: <span className="font-mono text-content-primary">{String(c.base_value)}</span>
                </span>
                <ArrowRight className="h-3 w-3" />
                <span>
                  LoRA: <span className="font-mono text-content-primary">{String(c.lora_value)}</span>
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  // ── Hard-dependency blocked (dispatch refused) ───
  if (state.kind === "blocked") {
    const { data } = state;
    return (
      <div
        className="rounded-lg border border-red-500/50 bg-red-500/20 p-4"
        data-testid="conflict-display-blocked"
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-400" />
          <p className="text-sm font-semibold text-red-300">
            Cannot dispatch — missing hard dependencies
          </p>
        </div>
        <p className="mt-1 text-xs text-red-200">
          Some required LoRAs or model components are missing. Add them before queuing.
        </p>
        {data.warnings.length > 0 && (
          <ul className="mt-2 space-y-1">
            {data.warnings.map((w, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-xs text-red-100"
              >
                <X className="mt-0.5 h-3 w-3 shrink-0" />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[11px] text-content-muted">
          Applied layers: <span className="font-mono text-content-primary">{data.applied_layers.join(", ")}</span>
        </p>
      </div>
    );
  }

  // Fallback — should never reach here
  return <div className="hidden" aria-hidden="true" />;
}