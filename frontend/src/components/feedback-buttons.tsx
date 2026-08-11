"use client";

import { useState, useCallback } from "react";
import { ThumbsUp, ThumbsDown, Star, AlertCircle, RotateCcw } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * FeedbackButtons — Universal rating component for any agent output.
 *
 * Story 107: Durable feedback persistence with authoritative confirmation.
 * - Success appears ONLY after durable persistence succeeds.
 * - Failed submissions expose retry without creating duplicates.
 * - Uses idempotency_key to prevent double-submission on retry.
 *
 * Usage:
 *   <FeedbackButtons
 *     assetId="ast-abc123"
 *     jobId="job-xyz"
 *     orgId="org-123"
 *     userId="user-456"
 *     contextPackageId="ctx-1"
 *     agent="akose"
 *     outputType="recipe_generation"
 *   />
 */

interface FeedbackButtonsProps {
  /** Required: the output asset being rated */
  assetId?: string;
  /** The generation job that produced the asset */
  jobId?: string;
  /** Authenticated org (workspace) — server-derived in production */
  orgId?: string;
  /** Authenticated user — server-derived in production */
  userId?: string;
  /** Immutable context package used for generation */
  contextPackageId?: string;
  /** Talent linked to the output */
  talentId?: string;
  /** The org that owns the asset (for cross-tenant validation) */
  assetOrgId?: string;
  /** Agent that produced the output (for legacy learning integration) */
  agent?: string;
  /** Output type classification */
  outputType?: string;
  /** Additional context for learning */
  context?: Record<string, unknown>;
  /** Compact mode: just thumbs up/down */
  compact?: boolean;
}

type FeedbackState = "idle" | "sending" | "persisted" | "failed";

export function FeedbackButtons({
  assetId = "",
  jobId = "",
  orgId = "",
  userId = "",
  contextPackageId = "",
  talentId,
  assetOrgId = "",
  agent = "",
  outputType = "",
  context = {},
  compact = false,
}: FeedbackButtonsProps) {
  const [state, setState] = useState<FeedbackState>("idle");
  const [ratedValue, setRatedValue] = useState<number | null>(null);
  const [feedbackId, setFeedbackId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // Stable idempotency key per component instance + rating value
  const [idempotencyKey] = useState(() => `fb-${crypto.randomUUID()}`);

  const submitRating = useCallback(async (rating: number, ratingType: "stars" | "thumbs" = "stars") => {
    if (state === "sending") return;

    setState("sending");
    setRatedValue(rating);
    setErrorMessage(null);

    // Map rating for the durable endpoint
    const ratingValue = ratingType === "thumbs" ? (rating >= 4 ? 2 : 1) : rating;

    try {
      const resp = await fetch(`${API_BASE}/api/v1/feedback/durable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          org_id: orgId,
          user_id: userId,
          asset_id: assetId,
          job_id: jobId,
          context_package_id: contextPackageId,
          talent_id: talentId || null,
          asset_org_id: assetOrgId,
          rating_type: ratingType,
          rating_value: ratingValue,
          reason: "",
          idempotency_key: `${idempotencyKey}-${rating}`,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Network error" }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }

      const data = await resp.json();

      if (data.success) {
        setState("persisted");
        setFeedbackId(data.feedback_id);

        // Also fire legacy learning signal (non-blocking)
        if (agent && outputType) {
          fetch(`${API_BASE}/api/v1/learn/feedback`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ agent, output_type: outputType, rating, context }),
          }).catch(() => {}); // Silent — learning is best-effort
        }
      } else {
        throw new Error(data.error || "Persistence failed");
      }
    } catch (err) {
      setState("failed");
      setErrorMessage(err instanceof Error ? err.message : "Failed to save");
    }
  }, [state, orgId, userId, assetId, jobId, contextPackageId, talentId, assetOrgId, idempotencyKey, agent, outputType, context]);

  const handleRetry = useCallback(() => {
    if (ratedValue !== null) {
      submitRating(ratedValue, compact ? "thumbs" : "stars");
    }
  }, [ratedValue, compact, submitRating]);

  // Persisted — authoritative confirmation
  if (state === "persisted") {
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-gray-500">
          {(ratedValue ?? 0) >= 4 ? "Rating saved." : "Noted — rating saved."}
        </span>
        {(ratedValue ?? 0) >= 4 ? (
          <ThumbsUp className="h-3 w-3 text-green-400" />
        ) : (
          <ThumbsDown className="h-3 w-3 text-amber-400" />
        )}
      </div>
    );
  }

  // Failed — show error and retry
  if (state === "failed") {
    return (
      <div className="flex items-center gap-1.5">
        <AlertCircle className="h-3 w-3 text-red-400" />
        <span className="text-[10px] text-red-400">
          {errorMessage || "Failed"}
        </span>
        <button
          onClick={handleRetry}
          className="flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] text-gray-400 hover:text-white hover:bg-white/[0.08] transition-colors"
          title="Retry"
        >
          <RotateCcw className="h-3 w-3" />
          Retry
        </button>
      </div>
    );
  }

  // Sending — show loading state
  if (state === "sending") {
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-gray-500 animate-pulse">Saving...</span>
      </div>
    );
  }

  // Idle — show rating UI
  if (compact) {
    return (
      <div className="flex items-center gap-1">
        <button
          onClick={() => submitRating(5, "thumbs")}
          className="p-1 rounded text-gray-500 hover:text-green-400 hover:bg-green-400/10 transition-colors"
          title="Good result"
        >
          <ThumbsUp className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => submitRating(2, "thumbs")}
          className="p-1 rounded text-gray-500 hover:text-amber-400 hover:bg-amber-400/10 transition-colors"
          title="Needs improvement"
        >
          <ThumbsDown className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-gray-600">Rate this:</span>
      <div className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            onClick={() => submitRating(star, "stars")}
            className="p-0.5 text-gray-600 hover:text-yellow-400 transition-colors"
            title={`${star} star${star > 1 ? "s" : ""}`}
          >
            <Star className="h-3.5 w-3.5" fill={star <= (ratedValue || 0) ? "currentColor" : "none"} />
          </button>
        ))}
      </div>
    </div>
  );
}
