"use client";

import { useState, useCallback } from "react";
import { ConfirmationDialog, type RiskTier } from "./confirmation-dialog";

/**
 * Governed Action — hook + dialog for high-risk actions.
 *
 * Provides a unified confirmation pattern for all destructive/costly actions:
 * - Delete talent, assets, photos, scheduled posts
 * - Stop/pause GPU workers
 * - Archive/permanently delete models
 * - Shut down fleet workers
 * - Revoke credentials
 *
 * Accessibility:
 * - Delegates to ConfirmationDialog which has focus trap, Escape handling,
 *   aria-labelledby/describedby, role="alertdialog", aria-modal="true"
 *
 * Idempotency:
 * - Action cannot fire twice while executing
 * - Unknown outcomes shown truthfully
 */

// =============================================================================
// Types
// =============================================================================

export interface ActionResult {
  success: boolean;
  message?: string;
  error?: string;
  unknownOutcome?: boolean;
}

export interface DialogState {
  open: boolean;
  title: string;
  target: string;
  consequence: string;
  riskTier: RiskTier;
  confirmLabel?: string;
  costDisclosure?: string;
  typedConfirmation?: string;
  escapeDisabled?: boolean;
}

/** Rich action descriptor for the requestConfirmation API */
export interface GovernedActionDescriptor {
  /** Unique key for idempotency tracking (e.g. "delete-talent-{id}") */
  actionKey: string;
  /** Risk tier determines confirmation UX */
  riskTier: "standard" | "elevated" | "critical";
  /** Human-readable action verb (e.g. "Delete", "Terminate") */
  verb: string;
  /** Name of the target resource */
  resourceName: string;
  /** Type of resource for context */
  resourceType: string;
  /** Clear statement of what will happen */
  consequence: string;
  /** Optional cost disclosure */
  costDisclosure?: string;
  /** For critical tier: text user must type to confirm */
  typedConfirmation?: string;
  /** Whether Escape key should be disabled */
  escapeDisabled?: boolean;
  /** Custom confirm button label (default: verb) */
  confirmLabel?: string;
  /** Custom cancel button label (default: "Cancel") */
  cancelLabel?: string;
}

// =============================================================================
// Risk Tier Mapping (new tier names → confirmation-dialog tier names)
// =============================================================================

function mapRiskTier(tier: "standard" | "elevated" | "critical"): RiskTier {
  switch (tier) {
    case "standard": return "medium";
    case "elevated": return "high";
    case "critical": return "critical";
  }
}

// =============================================================================
// Hook
// =============================================================================

export function useGovernedAction() {
  const [dialogState, setDialogState] = useState<DialogState>({
    open: false,
    title: "",
    target: "",
    consequence: "",
    riskTier: "medium",
  });
  const [pendingAction, setPendingAction] = useState<(() => Promise<boolean | null>) | null>(null);

  /** Legacy API: request an action with a simple config */
  const requestAction = useCallback((
    config: Omit<DialogState, "open">,
    action: () => Promise<boolean | null>,
  ) => {
    setDialogState({ ...config, open: true });
    setPendingAction(() => action);
  }, []);

  /**
   * Rich API: request confirmation with full action descriptor.
   * Maps GovernedActionDescriptor → DialogState and wraps the executor
   * to handle ActionResult → boolean|null conversion.
   */
  const requestConfirmation = useCallback((
    descriptor: GovernedActionDescriptor,
    executor: () => Promise<ActionResult>,
  ) => {
    setDialogState({
      open: true,
      title: `${descriptor.verb} ${descriptor.resourceType}`,
      target: descriptor.resourceName,
      consequence: descriptor.consequence,
      riskTier: mapRiskTier(descriptor.riskTier),
      confirmLabel: descriptor.confirmLabel || descriptor.verb,
      costDisclosure: descriptor.costDisclosure,
      typedConfirmation: descriptor.typedConfirmation,
      escapeDisabled: descriptor.escapeDisabled,
    });
    // Wrap the executor to convert ActionResult → boolean|null
    setPendingAction(() => async () => {
      try {
        const result = await executor();
        if (result.unknownOutcome) return null;
        return result.success;
      } catch {
        return false;
      }
    });
  }, []);

  const cancel = useCallback(() => {
    setDialogState((prev) => ({ ...prev, open: false }));
    setPendingAction(null);
  }, []);

  const executeAction = useCallback(async (): Promise<boolean | null> => {
    if (!pendingAction) return false;
    return pendingAction();
  }, [pendingAction]);

  const retry = useCallback(async (): Promise<boolean | null> => {
    return executeAction();
  }, [executeAction]);

  return {
    dialogState,
    requestAction,
    requestConfirmation,
    cancel,
    executeAction,
    retry,
  };
}

// =============================================================================
// Dialog Component (wraps ConfirmationDialog)
// =============================================================================

interface GovernedConfirmationDialogProps {
  dialogState: DialogState;
  onConfirm: () => Promise<boolean | null>;
  onCancel: () => void;
  onRetry: () => Promise<boolean | null>;
}

export function GovernedConfirmationDialog({
  dialogState,
  onConfirm,
  onCancel,
}: GovernedConfirmationDialogProps) {
  return (
    <ConfirmationDialog
      open={dialogState.open}
      riskTier={dialogState.riskTier}
      title={dialogState.title}
      target={dialogState.target}
      consequence={dialogState.consequence}
      confirmLabel={dialogState.confirmLabel}
      costDisclosure={dialogState.costDisclosure}
      typedConfirmation={dialogState.typedConfirmation}
      escapeDisabled={dialogState.escapeDisabled}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
