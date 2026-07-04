"use client";

import { useEffect, useState } from "react";
import { Film, Server, Cpu, DollarSign, Plus, Loader2 } from "lucide-react";
import { getJobs, getFleetStatus, launchWorker } from "@/lib/api";

export default function ProductionPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [fleet, setFleet] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [launchState, setLaunchState] = useState<"idle" | "launching" | "success" | "error">("idle");
  const [launchError, setLaunchError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [jobsData, fleetData] = await Promise.allSettled([getJobs(), getFleetStatus()]);
        if (jobsData.status === "fulfilled") setJobs(Array.isArray(jobsData.value) ? jobsData.value : []);
        if (fleetData.status === "fulfilled") setFleet(fleetData.value);
      } catch {} finally {
        setLoading(false);
      }
    }
    load();
    // Auto-refresh every 10 seconds when worker is launching
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  async function handleLaunch() {
    setLaunchState("launching");
    setLaunchError("");
    try {
      await launchWorker({ max_price: 1.5, min_vram_gb: 24, num_candidates: 3 });
      setLaunchState("success");
      // Refresh fleet
      const fleetData = await getFleetStatus();
      setFleet(fleetData);
    } catch (err: any) {
      setLaunchState("error");
      setLaunchError(err?.message || "Launch failed");
    }
  }

  const queuedJobs = jobs.filter((j) => j.status === "queued").length;
  const runningJobs = jobs.filter((j) => j.status === "running").length;
  const activeWorkers = fleet?.active_workers ?? 0;
  const gpuSpend = fleet?.cost_today ?? "$0.00";
  const fleetStatus = activeWorkers > 0 ? "Active" : "Idle";

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
          <p className="text-sm text-gray-500">Jobs, workers, render fleet, execution engine, and queue management.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleLaunch}
            disabled={launchState === "launching"}
            className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06] disabled:opacity-50"
          >
            <Server className="h-4 w-4" />
            {launchState === "launching" ? "Launching..." : "Launch Worker"}
          </button>
          <button className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700">
            <Plus className="h-4 w-4" /> New Job
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

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Active Workers", value: String(activeWorkers), icon: Server, color: "bg-purple-600" },
          { label: "Jobs in Queue", value: String(queuedJobs + runningJobs), icon: Cpu, color: "bg-blue-600" },
          { label: "GPU Spend Today", value: typeof gpuSpend === "number" ? `$${gpuSpend.toFixed(2)}` : gpuSpend, icon: DollarSign, color: "bg-green-600" },
          { label: "Fleet Status", value: fleetStatus, icon: Film, color: "bg-amber-600" },
        ].map((m) => (
          <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 flex items-center gap-3">
            <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${m.color}`}>
              <m.icon className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-xs text-gray-500">{m.label}</p>
              <p className="text-lg font-bold text-white">{m.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Job list */}
      {jobs.length > 0 ? (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <h3 className="text-sm font-semibold text-white mb-3">Job Queue</h3>
          <div className="space-y-2">
            {jobs.slice(0, 20).map((job, idx) => (
              <div key={job.id || idx} className="flex items-center gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3">
                <Cpu className="h-4 w-4 text-purple-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">{job.name || job.type || "Untitled Job"}</p>
                  <p className="text-xs text-gray-500">{job.model || "—"}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  job.status === "completed" ? "bg-green-500/20 text-green-400" :
                  job.status === "running" ? "bg-blue-500/20 text-blue-400" :
                  job.status === "failed" ? "bg-red-500/20 text-red-400" :
                  "bg-amber-500/20 text-amber-400"
                }`}>
                  {job.status || "queued"}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
          <Cpu className="h-12 w-12 text-gray-600 mx-auto mb-3" />
          <p className="text-sm text-gray-400">No active workers</p>
          <p className="text-xs text-gray-600 mt-1">Launch a GPU worker to start generating content.</p>
        </div>
      )}
    </div>
  );
}
