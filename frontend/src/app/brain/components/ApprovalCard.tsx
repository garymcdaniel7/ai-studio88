"use client";

import { useState } from "react";
import type { ApprovalData, ApprovalStatus } from "../types";
import { authFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApprovalCardProps {
  data: ApprovalData;
  onAction: () => void;
}

/**
 * Inline approval card with approve/reject buttons.
 * Renders inside chat messages for governance actions requiring user consent.
 */
export function ApprovalCard({ data, onAction }: ApprovalCardProps) {
  const [status, setStatus] = useState<ApprovalStatus>("pending");
  const [executing, setExecuting] = useState(false);

  async function handleApprove() {
    setExecuting(true);
    try {
      const resp = await authFetch(`${API_BASE}/aios/v1/approvals/${data.approval_id}/approve`, { method: "POST" });
      if (resp.ok) {
        setStatus("approved");
        onAction();
      }
    } catch {
      // Silent failure
    }
    setExecuting(false);
  }

  async function handleReject() {
    try {
      await authFetch(`${API_BASE}/aios/v1/approvals/${data.approval_id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Rejected from Brain chat" }),
      });
      setStatus("rejected");
      onAction();
    } catch {
      // Silent failure
    }
  }

  if (status === "approved") {
    return <p className="text-xs text-green-400">✅ Approved — executing {data.tool}</p>;
  }
  if (status === "rejected") {
    return <p className="text-xs text-gray-500">❌ Rejected — {data.tool} cancelled</p>;
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-amber-300">⚡ Action requires your approval:</p>
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
        <p className="text-xs font-medium text-white">{data.tool}</p>
        <p className="text-[10px] text-gray-400 mt-0.5">{data.reason}</p>
        {data.estimated_cost_usd != null && data.estimated_cost_usd > 0 && (
          <p className="text-[10px] text-amber-400 mt-0.5">Estimated cost: ${data.estimated_cost_usd.toFixed(3)}</p>
        )}
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleApprove}
          disabled={executing}
          className="rounded-lg bg-green-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
        >
          {executing ? "Executing..." : "Approve"}
        </button>
        <button
          onClick={handleReject}
          className="rounded-lg border border-white/[0.08] px-4 py-1.5 text-xs text-gray-400 hover:text-white"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
