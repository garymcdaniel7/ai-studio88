"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { AlertTriangle, Trash2, Loader2, CheckCircle, XCircle } from "lucide-react";

/**
 * Governed Confirmation Dialog — Story 139.
 *
 * One accessible pattern for all high-risk actions:
 * - Names exact target and consequence
 * - Risk-tiered (low, medium, high, critical)
 * - Optional typed confirmation for critical actions
 * - Focus trap and Escape handling
 * - Idempotent execution (prevents duplicate side effects)
 * - Waits for authoritative server result
 * - Shows unresolved outcomes truthfully
 *
 * Usage:
 *   <ConfirmationDialog
 *     open={showDelete}
 *     riskTier="high"
 *     title="Delete Talent"
 *     target="Melissa (AI Model)"
 *     consequence="This will permanently remove the talent, all generated assets, and training data."
 *     confirmLabel="Delete Forever"
 *     typedConfirmation="Melissa"
 *     onConfirm={handleDelete}
 *     onCancel={() => setShowDelete(false)}
 *   />
 */

// =============================================================================
// Types
// =============================================================================

export type RiskTier = "low" | "medium" | "high" | "critical";

export type ExecutionState = "idle" | "executing" | "success" | "failed" | "unknown";

export interface ConfirmationDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Risk level determines visual treatment and confirmation strength */
  riskTier: RiskTier;
  /** Dialog title (action being taken) */
  title: string;
  /** Exact target resource name */
  target: string;
  /** What will happen (consequences) */
  consequence: string;
  /** Button label for the confirm action */
  confirmLabel?: string;
  /** If set, user must type this exact text to confirm (critical actions) */
  typedConfirmation?: string;
  /** Cost disclosure (if action has financial impact) */
  costDisclosure?: string;
  /** Execute the action — returns true on success, false on failure, null on unknown */
  onConfirm: () => Promise<boolean | null>;
  /** Cancel/close the dialog */
  onCancel: () => void;
  /** Whether Escape key is disabled (for mandatory decisions) */
  escapeDisabled?: boolean;
}

// =============================================================================
// Risk Tier Configuration
// =============================================================================

const RISK_CONFIG: Record<RiskTier, {
  icon: typeof AlertTriangle;
  borderColor: string;
  buttonColor: string;
  buttonHover: string;
  iconColor: string;
}> = {
  low: {
    icon: AlertTriangle,
    borderColor: "border-status-info/30",
    buttonColor: "bg-status-info",
    buttonHover: "hover:bg-status-info/80",
    iconColor: "text-status-info",
  },
  medium: {
    icon: AlertTriangle,
    borderColor: "border-status-warning/30",
    buttonColor: "bg-status-warning",
    buttonHover: "hover:bg-status-warning/80",
    iconColor: "text-status-warning",
  },
  high: {
    icon: Trash2,
    borderColor: "border-status-error/30",
    buttonColor: "bg-status-error",
    buttonHover: "hover:bg-status-error/80",
    iconColor: "text-status-error",
  },
  critical: {
    icon: Trash2,
    borderColor: "border-status-error/50",
    buttonColor: "bg-status-error/90",
    buttonHover: "hover:bg-status-error",
    iconColor: "text-status-error",
  },
};

// =============================================================================
// Component
// =============================================================================

export function ConfirmationDialog({
  open,
  riskTier,
  title,
  target,
  consequence,
  confirmLabel,
  typedConfirmation,
  costDisclosure,
  onConfirm,
  onCancel,
  escapeDisabled = false,
}: ConfirmationDialogProps) {
  const [executionState, setExecutionState] = useState<ExecutionState>("idle");
  const [typedValue, setTypedValue] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const config = RISK_CONFIG[riskTier];
  const Icon = config.icon;

  // Typed confirmation match
  const typedMatch = !typedConfirmation || typedValue === typedConfirmation;
  const canConfirm = executionState === "idle" && typedMatch;

  // Focus trap: store previous focus and restore on close
  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement;
      // Focus the dialog or confirm button after render
      setTimeout(() => {
        if (typedConfirmation) {
          // Focus the input for typed confirmation
          dialogRef.current?.querySelector("input")?.focus();
        } else {
          confirmButtonRef.current?.focus();
        }
      }, 50);
    } else {
      // Restore focus
      previousFocusRef.current?.focus();
      // Reset state when dialog closes
      setExecutionState("idle");
      setTypedValue("");
    }
  }, [open, typedConfirmation]);

  // Keyboard handling
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!open) return;

    if (e.key === "Escape" && !escapeDisabled && executionState !== "executing") {
      e.preventDefault();
      onCancel();
    }

    // Trap focus within dialog
    if (e.key === "Tab" && dialogRef.current) {
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }, [open, escapeDisabled, executionState, onCancel]);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Execute action (idempotent — cannot fire twice)
  async function handleConfirm() {
    if (!canConfirm) return;

    setExecutionState("executing");
    try {
      const result = await onConfirm();
      if (result === true) {
        setExecutionState("success");
        // Auto-close after success
        setTimeout(() => onCancel(), 1200);
      } else if (result === false) {
        setExecutionState("failed");
      } else {
        // null = unknown outcome
        setExecutionState("unknown");
      }
    } catch {
      setExecutionState("failed");
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !escapeDisabled && executionState !== "executing") {
          onCancel();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-desc"
        className={`w-full max-w-md rounded-2xl border ${config.borderColor} bg-surface-overlay p-6 shadow-2xl`}
      >
        {/* Icon + Title */}
        <div className="flex items-start gap-3 mb-4">
          <div className={`p-2 rounded-lg bg-surface-hover ${config.iconColor}`}>
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <h2 id="confirm-title" className="text-lg font-bold text-content-primary">{title}</h2>
            <p className="text-sm text-content-secondary mt-0.5">
              Target: <span className="font-medium text-content-primary">{target}</span>
            </p>
          </div>
        </div>

        {/* Consequence */}
        <div id="confirm-desc" className={`rounded-lg border ${config.borderColor} bg-surface-hover/50 p-3 mb-4`}>
          <p className="text-sm text-content-secondary">{consequence}</p>
        </div>

        {/* Cost disclosure */}
        {costDisclosure && (
          <div className="rounded-lg border border-status-warning/20 bg-status-warning-muted px-3 py-2 mb-4">
            <p className="text-xs text-status-warning">💰 {costDisclosure}</p>
          </div>
        )}

        {/* Typed confirmation (critical actions) */}
        {typedConfirmation && executionState === "idle" && (
          <div className="mb-4">
            <label className="text-xs text-content-tertiary block mb-1">
              Type <span className="font-mono text-status-error">{typedConfirmation}</span> to confirm:
            </label>
            <input
              type="text"
              value={typedValue}
              onChange={(e) => setTypedValue(e.target.value)}
              placeholder={typedConfirmation}
              className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-secondary outline-none focus:border-status-error/50"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        )}

        {/* Execution state feedback */}
        {executionState === "executing" && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-surface-hover">
            <Loader2 className="h-4 w-4 text-status-info animate-spin" />
            <p className="text-sm text-content-secondary">Executing...</p>
          </div>
        )}
        {executionState === "success" && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-status-success-muted">
            <CheckCircle className="h-4 w-4 text-status-success" />
            <p className="text-sm text-status-success">Action completed successfully</p>
          </div>
        )}
        {executionState === "failed" && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-status-error-muted">
            <XCircle className="h-4 w-4 text-status-error" />
            <p className="text-sm text-status-error">Action failed. You can retry.</p>
          </div>
        )}
        {executionState === "unknown" && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-status-warning-muted">
            <AlertTriangle className="h-4 w-4 text-status-warning" />
            <p className="text-sm text-status-warning">Outcome unknown. Check status before retrying.</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2">
          {executionState !== "success" && (
            <button
              onClick={onCancel}
              disabled={executionState === "executing"}
              className="px-4 py-2 rounded-lg text-sm text-content-tertiary hover:text-content-primary hover:bg-surface-hover disabled:opacity-50"
            >
              Cancel
            </button>
          )}
          {(executionState === "idle" || executionState === "failed") && (
            <button
              ref={confirmButtonRef}
              onClick={handleConfirm}
              disabled={!canConfirm}
              className={`px-4 py-2 rounded-lg text-sm font-medium text-white ${config.buttonColor} ${config.buttonHover} disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {executionState === "failed" ? "Retry" : (confirmLabel || title)}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
