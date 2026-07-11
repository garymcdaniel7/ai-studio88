"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useEffect, useState } from "react";
import { Film, Server, Cpu, DollarSign, Loader2, Trash2, RefreshCw, Clock, CheckCircle, XCircle } from "lucide-react";
import { getJobs, getFleetStatus, launchWorker } from "@/lib/api";

export default function ProductionPage() {
  const [jobs, setJobs] = useState<Record<string, unknown>[]>([]);
  const [fleet, setFleet] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [launchState, setLaunchState] = useState<"idle" | "launching" | "success" | "error">("idle");
  const [launchError, setLaunchError] = useState("");
  const [costHourly, setCostHourly] = useState<Record<string, number> | null>(null);
  const [showCostTooltip, setShowCostTooltip] = useState(false);
  const [clearing, setClearing] = useState(false);

  async function loadData() {
    try {
      const [jobsData, fleetData, costData] = await Promise.allSettled([
        getJobs(),
        getFleetStatus(),
        fetch(`${API_BASE}/api/v1/infrastructure/cost/hourly`).then((r) => r.json()),
      ]);
      if (jobsData.status === "fulfilled") setJobs(Array.isArray(jobsData.value) ? jobsData.value : []);
      if (fleetData.status === "fulfilled") setFleet(fleetData.value);
      if (costData.status === "fulfilled") {
        const data = costData.value as Record<string, unknown>;
        setCostHourly((data?.hourly as Record<string, number>) || null);
      }
    } catch {} finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [jobsData, fleetData, costData] = await Promise.allSettled([
          getJobs(),
          getFleetStatus(),
          fetch(`${API_BASE}/api/v1/infrastructure/cost/hourly`).then((r) => r.json()),
        ]);
        if (!active) return;
        if (jobsData.status === "fulfilled") setJobs(Array.isArray(jobsData.value) ? jobsData.value : []);
        if (fleetData.status === "fulfilled") setFleet(fleetData.value);
        if (costData.status === "fulfilled") {
          const data = costData.value as Record<string, unknown>;
          setCostHourly((data?.hourly as Record<string, number>) || null);
        }
      } catch {} finally {
        if (active) setLoading(false);
      }
    })();
    const interval = setInterval(loadData, 10000);
    return () => { active = false; clearInterval(interval); };
  }, []);

  async function handleLaunch() {
    setLaunchState("launching");
    setLaunchError("");
    try {
      await launchWorker({ max_price: 1.5, min_vram_gb: 24, num_candidates: 3 });
      setLaunchState("success");
      await loadData();
    } catch (err: unknown) {
      setLaunchState("error");
      setLaunchError((err as Error)?.message || "Launch failed");
    }
  }

  async function clearCompletedJobs() {
    const count = jobs.filter((j) => j.status === "completed" || j.status === "failed").length;
    if (!confirm(`Clear ${count} completed/failed jobs? This cannot be undone.`)) return;
    setClearing(true);
    try {
      const toDelete = jobs.filter((j) => j.status === "completed" || j.status === "failed");
      for (const job of toDelete) {
        await fetch(`${API_BASE}/api/v1/jobs/${job.id}`, { method: "DELETE" });
      }
      setJobs((prev) => prev.filter((j) => j.status !== "completed" && j.status !== "failed"));
    } catch {} finally {
      setClearing(false);
    }
  }

  const queuedJobs = jobs.filter((j) => j.status === "queued");
  const runningJobs = jobs.filter((j) => j.status === "running");
  const completedJobs = jobs.filter((j) => j.status === "completed");
  const failedJobs = jobs.filter((j) => j.status === "failed");
  const activeWorkers = (fleet?.active_workers as number) ?? 0;
  const fleetStatus = activeWorkers > 0 ? "Active" : "Idle";

  // Calculate GPU spend from hourly data
  const totalSpendToday = costHourly ? Object.values(costHourly).reduce((s, v) => s + v, 0) : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Production</h1>
          <p className="text-sm text-gray-500">Jobs, workers, render fleet, and queue management.</p>
        </div>
        <div className="flex gap-2">
          {(completedJobs.length > 0 || failedJobs.length > 0) && (
            <button
              onClick={clearCompletedJobs}
              disabled={clearing}
              className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06] disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              {clearing ? "Clearing..." : `Clear ${completedJobs.length + failedJobs.length} Done`}
            </button>
          )}
          <button
            onClick={() => loadData()}
            className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
          <button
            onClick={() => {
              if (!confirm("Launch a GPU worker on Vast.ai (~$0.50-1.50/hr). Continue?")) return;
              handleLaunch();
            }}
            disabled={launchState === "launching"}
            className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            <Server className="h-4 w-4" />
            {launchState === "launching" ? "Launching..." : "Launch Worker"}
          </button>
        </div>
      </div>

      {/* Launch feedback */}
      {launchState === "success" && (
        <div className="rounded-lg border border-green-500/20 bg-green-500/5 px-4 py-2 text-xs text-green-400">
          Worker launched successfully.
        </div>
      )}
      {launchState === "error" && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2 text-xs text-red-400">
          {launchError}
        </div>
      )}

      {/* Metrics */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-600">
            <Server className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs text-gray-500">Active Workers</p>
            <p className="text-lg font-bold text-white">{activeWorkers}</p>
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600">
            <Cpu className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs text-gray-500">Jobs in Queue</p>
            <p className="text-lg font-bold text-white">{queuedJobs.length + runningJobs.length}</p>
            {runningJobs.length > 0 && (
              <p className="text-[10px] text-blue-400">{runningJobs.length} running now</p>
            )}
          </div>
        </div>

        {/* GPU Spend with hover tooltip */}
        <div
          className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 flex items-center gap-3 relative cursor-pointer"
          onMouseEnter={() => setShowCostTooltip(true)}
          onMouseLeave={() => setShowCostTooltip(false)}
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-600">
            <DollarSign className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs text-gray-500">GPU Spend Today</p>
            <p className="text-lg font-bold text-white">${totalSpendToday.toFixed(2)}</p>
          </div>

          {/* Hourly tooltip */}
          {showCostTooltip && costHourly && (
            <div className="absolute bottom-full left-0 mb-2 w-72 rounded-xl border border-white/[0.08] bg-[#0f0f24] p-4 shadow-2xl z-50">
              <p className="text-xs font-semibold text-white mb-2">Hourly Breakdown (UTC)</p>
              <div className="grid grid-cols-6 gap-1">
                {Object.entries(costHourly).map(([hour, cost]) => (
                  <div key={hour} className="text-center">
                    <div
                      className="mx-auto w-3 rounded-sm bg-green-500/40"
                      style={{ height: `${Math.max(4, (cost / Math.max(0.01, totalSpendToday)) * 40)}px` }}
                    />
                    <p className="text-[8px] text-gray-600 mt-0.5">{hour.slice(0, 2)}</p>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-gray-500 mt-2">Total: ${totalSpendToday.toFixed(4)}</p>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-600">
            <Film className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs text-gray-500">Fleet Status</p>
            <p className="text-lg font-bold text-white">{fleetStatus}</p>
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
                  <p className="text-sm text-white truncate">{(job.name as string) || (job.type as string) || "Generation"}</p>
                  <p className="text-xs text-gray-500">{(job.model as string) || "—"} • Started {job.started_at ? new Date(job.started_at as string).toLocaleTimeString() : "just now"}</p>
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400">Running</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Job Queue */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-white">Job Queue ({jobs.length} total)</h3>
          <div className="flex items-center gap-3 text-[10px] text-gray-500">
            <span className="flex items-center gap-1"><Clock className="h-3 w-3 text-amber-400" />{queuedJobs.length} queued</span>
            <span className="flex items-center gap-1"><CheckCircle className="h-3 w-3 text-green-400" />{completedJobs.length} done</span>
            <span className="flex items-center gap-1"><XCircle className="h-3 w-3 text-red-400" />{failedJobs.length} failed</span>
          </div>
        </div>

        {jobs.length > 0 ? (
          <div className="space-y-2">
            {jobs.slice(0, 30).map((job, idx) => (
              <div key={(job.id as string) || idx} className="flex items-center gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3">
                {job.status === "running" ? (
                  <Loader2 className="h-4 w-4 text-blue-400 animate-spin shrink-0" />
                ) : job.status === "completed" ? (
                  <CheckCircle className="h-4 w-4 text-green-400 shrink-0" />
                ) : job.status === "failed" ? (
                  <XCircle className="h-4 w-4 text-red-400 shrink-0" />
                ) : (
                  <Clock className="h-4 w-4 text-amber-400 shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">{(job.name as string) || (job.type as string) || "Untitled Job"}</p>
                  <p className="text-xs text-gray-500">{(job.model as string) || "—"}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  job.status === "completed" ? "bg-green-500/20 text-green-400" :
                  job.status === "running" ? "bg-blue-500/20 text-blue-400" :
                  job.status === "failed" ? "bg-red-500/20 text-red-400" :
                  "bg-amber-500/20 text-amber-400"
                }`}>
                  {(job.status as string) || "queued"}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <Cpu className="h-12 w-12 text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-400">No jobs in the queue</p>
            <p className="text-xs text-gray-600 mt-1">Generate content from the Create page to see jobs here.</p>
          </div>
        )}
      </div>
    </div>
  );
}
