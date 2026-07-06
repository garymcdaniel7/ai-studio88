"use client";

import { useEffect, useState } from "react";
import { Server, Play, Pause, Square, RefreshCw, Loader2, DollarSign, Cpu, Settings, Zap } from "lucide-react";

interface Worker {
  id: string;
  provider: string;
  provider_instance_id: string;
  gpu_name: string;
  vram_gb: number;
  specialty: string;
  status: string;
  ssh_host: string;
  ssh_port: number;
  hourly_rate: number;
  idle_minutes: number;
  idle_action: string;
  jobs_completed: number;
}

interface FleetSettings {
  max_instances: number;
  daily_budget_usd: number;
  idle_timeout_minutes: number;
  auto_provision: boolean;
  preferred_provider: string;
  max_price_per_hour: number;
}

interface BudgetStatus {
  daily_budget: number;
  spent_today: number;
  remaining: number;
  percentage_used: number;
}

export default function FleetPage() {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [settings, setSettings] = useState<FleetSettings | null>(null);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  async function loadData() {
    try {
      const [wResp, sResp] = await Promise.allSettled([
        fetch("http://localhost:8000/api/v1/infrastructure/workers").then((r) => r.json()),
        fetch("http://localhost:8000/api/v1/infrastructure/fleet/settings").then((r) => r.json()),
      ]);
      if (wResp.status === "fulfilled") setWorkers(wResp.value.workers || []);
      if (sResp.status === "fulfilled") {
        setSettings(sResp.value.settings);
        setBudget(sResp.value.budget_status);
      }
    } catch {} finally { setLoading(false); }
  }

  useEffect(() => { loadData(); const i = setInterval(loadData, 15000); return () => clearInterval(i); }, []);

  async function workerAction(workerId: string, action: "stop" | "pause" | "resume") {
    setActionLoading(workerId);
    try {
      await fetch(`http://localhost:8000/api/v1/infrastructure/workers/${workerId}/${action}`, { method: "POST" });
      await loadData();
    } catch {} finally { setActionLoading(null); }
  }

  async function saveSettings(updated: Partial<FleetSettings>) {
    try {
      const resp = await fetch("http://localhost:8000/api/v1/infrastructure/fleet/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated),
      });
      const data = await resp.json();
      setSettings(data.settings);
      setBudget(data.budget_status);
    } catch {}
  }

  async function shutdownIdle() {
    await fetch("http://localhost:8000/api/v1/infrastructure/workers/idle/shutdown", { method: "POST" });
    await loadData();
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-purple-500" /></div>;

  const activeWorkers = workers.filter((w) => w.status === "ready" || w.status === "busy");
  const hourlyBurn = activeWorkers.reduce((s, w) => s + w.hourly_rate, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Fleet Management</h1>
          <p className="text-sm text-gray-500">Manage GPU workers across Vast.ai, RunPod, and Shadow.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={shutdownIdle} className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
            <Square className="h-4 w-4" /> Shutdown Idle
          </button>
          <button onClick={() => setShowSettings(!showSettings)} className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
            <Settings className="h-4 w-4" /> Settings
          </button>
          <button onClick={loadData} className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
          <p className="text-xs text-gray-500">Active Workers</p>
          <p className="text-2xl font-bold text-white">{activeWorkers.length}<span className="text-sm text-gray-500">/{settings?.max_instances || 3}</span></p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
          <p className="text-xs text-gray-500">Hourly Burn</p>
          <p className="text-2xl font-bold text-green-400">${hourlyBurn.toFixed(3)}<span className="text-sm text-gray-500">/hr</span></p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
          <p className="text-xs text-gray-500">Today&apos;s Spend</p>
          <p className="text-2xl font-bold text-amber-400">${(budget?.spent_today || 0).toFixed(2)}</p>
          <div className="mt-1 h-1.5 rounded-full bg-white/[0.05] overflow-hidden">
            <div className="h-full bg-amber-500 rounded-full" style={{ width: `${Math.min(100, budget?.percentage_used || 0)}%` }} />
          </div>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
          <p className="text-xs text-gray-500">Daily Budget</p>
          <p className="text-2xl font-bold text-white">${budget?.daily_budget || 0}</p>
          <p className="text-[10px] text-gray-600">${(budget?.remaining || 0).toFixed(2)} remaining</p>
        </div>
      </div>

      {/* Settings Panel */}
      {showSettings && settings && (
        <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-5 space-y-4">
          <h3 className="text-sm font-semibold text-purple-300">Fleet Settings</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-[10px] text-gray-400 mb-1">Max Instances (1-10)</label>
              <input type="number" min={1} max={10} value={settings.max_instances} onChange={(e) => saveSettings({ max_instances: parseInt(e.target.value) })} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-400 mb-1">Daily Budget (USD)</label>
              <input type="number" min={0.5} step={0.5} value={settings.daily_budget_usd} onChange={(e) => saveSettings({ daily_budget_usd: parseFloat(e.target.value) })} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-400 mb-1">Idle Timeout (min, 0=off)</label>
              <input type="number" min={0} value={settings.idle_timeout_minutes} onChange={(e) => saveSettings({ idle_timeout_minutes: parseInt(e.target.value) })} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-400 mb-1">Max Price/hr</label>
              <input type="number" min={0.05} step={0.05} value={settings.max_price_per_hour} onChange={(e) => saveSettings({ max_price_per_hour: parseFloat(e.target.value) })} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-400 mb-1">Preferred Provider</label>
              <select value={settings.preferred_provider} onChange={(e) => saveSettings({ preferred_provider: e.target.value })} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none">
                <option value="vast">Vast.ai</option>
                <option value="runpod">RunPod</option>
              </select>
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
                <input type="checkbox" checked={settings.auto_provision} onChange={(e) => saveSettings({ auto_provision: e.target.checked })} className="rounded" />
                Auto-provision when jobs queue
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Workers List */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-white">Workers ({workers.length})</h3>
        {workers.length === 0 ? (
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
            <Server className="h-12 w-12 text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-400">No GPU workers active</p>
            <p className="text-xs text-gray-600 mt-1">Generate content or enable auto-provision to launch workers.</p>
          </div>
        ) : (
          workers.map((worker) => (
            <div key={worker.id} className={`rounded-xl border p-4 ${
              worker.status === "ready" ? "border-green-500/20 bg-green-500/5" :
              worker.status === "busy" ? "border-blue-500/20 bg-blue-500/5" :
              worker.status === "provisioning" ? "border-amber-500/20 bg-amber-500/5" :
              "border-white/[0.06] bg-[#12122a]"
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                    worker.provider === "vast" ? "bg-purple-600/20" : "bg-blue-600/20"
                  }`}>
                    <Cpu className={`h-5 w-5 ${worker.provider === "vast" ? "text-purple-400" : "text-blue-400"}`} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-white">{worker.gpu_name}</p>
                      <span className="rounded px-1.5 py-0.5 text-[9px] font-medium bg-white/[0.06] text-gray-400">{worker.provider}</span>
                      <span className="rounded px-1.5 py-0.5 text-[9px] font-medium bg-purple-600/20 text-purple-400">{worker.specialty}</span>
                    </div>
                    <p className="text-xs text-gray-500">
                      {worker.vram_gb}GB VRAM · ${worker.hourly_rate.toFixed(3)}/hr · {worker.jobs_completed} jobs · Idle {worker.idle_minutes.toFixed(0)}min
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    worker.status === "ready" ? "bg-green-500/20 text-green-400" :
                    worker.status === "busy" ? "bg-blue-500/20 text-blue-400" :
                    worker.status === "provisioning" ? "bg-amber-500/20 text-amber-400" :
                    worker.status === "stopped" ? "bg-gray-500/20 text-gray-400" :
                    "bg-red-500/20 text-red-400"
                  }`}>{worker.status}</span>

                  {worker.status === "stopped" && (
                    <button onClick={() => workerAction(worker.id, "resume")} disabled={actionLoading === worker.id} className="rounded-lg bg-green-600/20 p-2 text-green-400 hover:bg-green-600/30 disabled:opacity-50">
                      {actionLoading === worker.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    </button>
                  )}
                  {(worker.status === "ready" || worker.status === "idle") && (
                    <>
                      <button onClick={() => workerAction(worker.id, "pause")} disabled={actionLoading === worker.id} className="rounded-lg bg-amber-600/20 p-2 text-amber-400 hover:bg-amber-600/30 disabled:opacity-50" title="Pause (stop billing)">
                        <Pause className="h-4 w-4" />
                      </button>
                      <button onClick={() => workerAction(worker.id, "stop")} disabled={actionLoading === worker.id} className="rounded-lg bg-red-600/20 p-2 text-red-400 hover:bg-red-600/30 disabled:opacity-50" title={`Stop (${worker.idle_action})`}>
                        <Square className="h-4 w-4" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
