"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useState } from "react";
import { Film, Server, Cpu, DollarSign, Loader2, Trash2, RefreshCw, Clock, CheckCircle, XCircle } from "lucide-react";
import { getJobs, getFleetStatus, authFetch } from "@/lib/api";
import {
  GovernedConfirmationDialog,
  useGovernedAction,
} from "@/components/governed-action";
import type { ActionResult } from "@/components/governed-action";
import Link from "next/link";
import { usePageState } from "@/lib/page-state";
import { PageStateRenderer } from "@/components/page-state";

interface ProductionData {
  jobs: Record<string, unknown>[];
  fleet: Record<string, unknown> | null;
  costHourly: Record<string, number> | null;
}

export default function ProductionPage() {
  const { dialogState, requestConfirmation, executeAction, cancel, retry } = useGovernedAction();
  const [showCostTooltip, setShowCostTooltip] = useState(false);
  const [clearing, setClearing] = useState(false);

  const { state, data, error, freshness, isOffline, retryAttempt, refresh, retry: retryFetch } = usePageState<ProductionData>({
    fetcher: async () => {
      const [jobsData, fleetData, costData] = await Promise.allSettled([
        getJobs(),
        getFleetStatus(),
        authFetch(`${API_BASE}/api/v1/infrastructure/cost/hourly`).then((r) => r.json()),
      ]);
      return {
        jobs: jobsData.status === "fulfilled" && Array.isArray(jobsData.value) ? jobsData.value : [],
        fleet: fleetData.status === "fulfilled" ? fleetData.value : null,
        costHourly: costData.status === "fulfilled" ? ((costData.value as Record<string, unknown>)?.hourly as Record<string, number>) || null : null,
      };
    },
    refreshInterval: 10_000,
    isEmpty: (d) => d.jobs.length === 0,
  });

  const jobs = data?.jobs || [];
  const fleet = data?.fleet || null;
  const costHourly = data?.costHourly || null;

  async function clearCompletedJobs() {
    const count = jobs.filter((j) => j.status === "completed" || j.status === "failed").length;
    requestConfirmation(
      {
        actionKey: "clear-completed-jobs",
        riskTier: "elevated",
        verb: "Clear",
        resourceName: `${count} completed/failed jobs`,
        resourceType: "Completed Jobs",
        consequence: `${count} completed and failed job records will be permanently removed. This cannot be undone.`,
      },
      async (): Promise<ActionResult> => {
        setClearing(true);
        try {
          const toDelete = jobs.filter((j) => j.status === "completed" || j.status === "failed");
          for (const job of toDelete) {
            await authFetch(`${API_BASE}/api/v1/jobs/${job.id}`, { method: "DELETE" });
          }
          refresh();
          return { success: true };
        } catch (err: unknown) {
          return { success: false, error: (err as Error)?.message || "Failed to clear jobs." };
        } finally {
          setClearing(false);
        }
      }
    );
  }

  const queuedJobs = jobs.filter((j) => j.status === "queued");
  const runningJobs = jobs.filter((j) => j.status === "running");
  const completedJobs = jobs.filter((j) => j.status === "completed");
  const failedJobs = jobs.filter((j) => j.status === "failed");
  const activeWorkers = (fleet?.active_workers as number) ?? 0;
  const fleetStatus = activeWorkers > 0 ? "Active" : "Idle";

  // Calculate GPU spend from hourly data
  const totalSpendToday = costHourly ? Object.values(costHourly).reduce((s, v) => s + v, 0) : 0;

  return (
    <PageStateRenderer
      state={state}
      error={error}
      freshness={freshness}
      retryAttempt={retryAttempt}
      isOffline={isOffline}
      hasData={jobs.length > 0}
      resource="jobs"
      onRetry={retryFetch}
      onRefresh={refresh}
      emptyState={
        <div className="text-center py-16">
          <Cpu className="h-12 w-12 text-content-muted mx-auto mb-3" />
          <p className="text-sm text-content-tertiary">No jobs in the queue</p>
          <p className="text-xs text-content-muted mt-1">Generate content from the Create page to see jobs here.</p>
        </div>
      }
    >
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-content-primary">Jobs</h1>
          <p className="text-sm text-content-muted">Generation queue, active workers, and job history.</p>
        </div>
        <div className="flex gap-2">
          {(completedJobs.length > 0 || failedJobs.length > 0) && (
            <button
              onClick={clearCompletedJobs}
              disabled={clearing}
              className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-secondary hover:bg-surface-active disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              {clearing ? "Clearing..." : `Clear ${completedJobs.length + failedJobs.length} Done`}
            </button>
          )}
          <button
            onClick={() => refresh()}
            className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-secondary hover:bg-surface-active"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
          <Link
            href="/admin/fleet"
            className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-secondary hover:bg-surface-active"
          >
            <Server className="h-4 w-4" /> Manage Fleet
          </Link>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-border-subtle bg-surface-raised p-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-600">
            <Server className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs text-content-muted">Active Workers</p>
            <p className="text-lg font-bold text-content-primary">{activeWorkers}</p>
          </div>
        </div>

        <div className="rounded-xl border border-border-subtle bg-surface-raised p-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600">
            <Cpu className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs text-content-muted">Jobs in Queue</p>
            <p className="text-lg font-bold text-content-primary">{queuedJobs.length + runningJobs.length}</p>
            {runningJobs.length > 0 && (
              <p className="text-[10px] text-blue-400">{runningJobs.length} running now</p>
            )}
          </div>
        </div>

        {/* GPU Spend with hover tooltip */}
        <div
          className="rounded-xl border border-border-subtle bg-surface-raised p-4 flex items-center gap-3 relative cursor-pointer"
          onMouseEnter={() => setShowCostTooltip(true)}
          onMouseLeave={() => setShowCostTooltip(false)}
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-600">
            <DollarSign className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs text-content-muted">GPU Spend Today</p>
            <p className="text-lg font-bold text-content-primary">${totalSpendToday.toFixed(2)}</p>
          </div>

          {/* Hourly tooltip */}
          {showCostTooltip && costHourly && (
            <div className="absolute bottom-full left-0 mb-2 w-72 rounded-xl border border-border-default bg-surface-overlay p-4 shadow-2xl z-50">
              <p className="text-xs font-semibold text-content-primary mb-2">Hourly Breakdown (UTC)</p>
              <div className="grid grid-cols-6 gap-1">
                {Object.entries(costHourly).map(([hour, cost]) => (
                  <div key={hour} className="text-center">
                    <div
                      className="mx-auto w-3 rounded-sm bg-green-500/40"
                      style={{ height: `${Math.max(4, (cost / Math.max(0.01, totalSpendToday)) * 40)}px` }}
                    />
                    <p className="text-[8px] text-content-muted mt-0.5">{hour.slice(0, 2)}</p>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-content-muted mt-2">Total: ${totalSpendToday.toFixed(4)}</p>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-border-subtle bg-surface-raised p-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-600">
            <Film className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs text-content-muted">Fleet Status</p>
            <p className="text-lg font-bold text-content-primary">{fleetStatus}</p>
          </div>
        </div>
      </div>

      {/* Active Jobs — Highlighted */}
      {runningJobs.length > 0 && (
        <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-5">
          <div className="flex items-center gap-2 mb-3">
            <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
            <h3 className="text-sm font-semibold text-blue-300">Active Jobs ({runningJobs.length})</h3>
          </div>
          <div className="space-y-2">
            {runningJobs.map((job, idx) => (
              <div key={(job.id as string) || idx} className="flex items-center gap-3 rounded-lg border border-blue-500/10 bg-blue-500/5 px-4 py-3">
                <Loader2 className="h-4 w-4 text-blue-400 animate-spin shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-content-primary truncate">{(job.name as string) || (job.type as string) || "Generation"}</p>
                  <p className="text-xs text-content-muted">{(job.model as string) || "—"} • Started {job.started_at ? new Date(job.started_at as string).toLocaleTimeString() : "just now"}</p>
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400">Running</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Job Queue */}
      <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-content-primary">Job Queue ({jobs.length} total)</h3>
          <div className="flex items-center gap-3 text-[10px] text-content-muted">
            <span className="flex items-center gap-1"><Clock className="h-3 w-3 text-status-warning" />{queuedJobs.length} queued</span>
            <span className="flex items-center gap-1"><CheckCircle className="h-3 w-3 text-status-success" />{completedJobs.length} done</span>
            <span className="flex items-center gap-1"><XCircle className="h-3 w-3 text-status-error" />{failedJobs.length} failed</span>
          </div>
        </div>

        {jobs.length > 0 ? (
          <div className="space-y-2">
            {jobs.slice(0, 30).map((job, idx) => (
              <div key={(job.id as string) || idx} className="flex items-center gap-3 rounded-lg border border-border-subtle bg-white/[0.02] px-4 py-3">
                {job.status === "running" ? (
                  <Loader2 className="h-4 w-4 text-blue-400 animate-spin shrink-0" />
                ) : job.status === "completed" ? (
                  <CheckCircle className="h-4 w-4 text-status-success shrink-0" />
                ) : job.status === "failed" ? (
                  <XCircle className="h-4 w-4 text-status-error shrink-0" />
                ) : (
                  <Clock className="h-4 w-4 text-status-warning shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-content-primary truncate">{(job.name as string) || (job.type as string) || "Untitled Job"}</p>
                  <p className="text-xs text-content-muted">{(job.model as string) || "—"}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  job.status === "completed" ? "bg-status-success-muted text-status-success" :
                  job.status === "running" ? "bg-blue-500/20 text-blue-400" :
                  job.status === "failed" ? "bg-status-error-muted text-status-error" :
                  "bg-status-warning-muted text-status-warning"
                }`}>
                  {(job.status as string) || "queued"}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <Cpu className="h-12 w-12 text-content-muted mx-auto mb-3" />
            <p className="text-sm text-content-tertiary">No jobs in the queue</p>
            <p className="text-xs text-content-muted mt-1">Generate content from the Create page to see jobs here.</p>
          </div>
        )}
      </div>

      {/* Governed Confirmation Dialog */}
      <GovernedConfirmationDialog
        dialogState={dialogState}
        onConfirm={executeAction}
        onCancel={cancel}
        onRetry={retry}
      />
    </div>
    </PageStateRenderer>
  );
}
