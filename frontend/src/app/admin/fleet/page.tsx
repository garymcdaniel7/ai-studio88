"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState } from "react";
import Link from "next/link";
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
  const [modelPlacements, setModelPlacements] = useState<{
    models: Array<{id: string; name: string; state: string; size_mb: number; type: string}>;
    worker_models: Array<{name: string; size_mb: number; category: string}>;
    worker_software: Array<{name: string; status: string; type: string}>;
    worker_disk: {total_gb?: number; free_gb?: number; used_pct?: number};
    worker_gpu: {name?: string; vram_total_mb?: number; vram_free_mb?: number};
    summary: Record<string, number>;
  } | null>(null);

  async function loadData() {
    try {
      const [wResp, sResp] = await Promise.allSettled([
        fetch(`${API_BASE}/api/v1/infrastructure/workers`).then((r) => r.json()),
        fetch(`${API_BASE}/api/v1/infrastructure/fleet/settings`).then((r) => r.json()),
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
      const resp = await fetch(`${API_BASE}/api/v1/infrastructure/workers/${workerId}/${action}`, { method: "POST" });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        alert(`${action} failed: ${data.detail || data.error || `HTTP ${resp.status}`}`);
      }
      await loadData();
    } catch (err) {
      alert(`Network error: ${(err as Error).message}`);
    } finally { setActionLoading(null); }
  }

  async function saveSettings(updated: Partial<FleetSettings>) {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/infrastructure/fleet/settings`, {
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
    if (!confirm("Shut down all idle workers? This will terminate billing on idle instances.")) return;
    await fetch(`${API_BASE}/api/v1/infrastructure/workers/idle/shutdown`, { method: "POST" });
    await loadData();
  }

  async function launchNewWorker() {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/infrastructure/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_price: settings?.max_price_per_hour || 0.20, min_vram_gb: 24, num_candidates: 3 }),
      });
      if (resp.ok) {
        alert("Worker launching! It will appear in the list within 1-2 minutes.");
        await loadData();
      } else {
        const data = await resp.json().catch(() => ({}));
        alert(`Launch failed: ${data.detail || data.error || "Unknown error"}`);
      }
    } catch (err) {
      alert(`Network error: ${(err as Error).message}`);
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-purple-500" /></div>;

  const activeWorkers = workers.filter((w) => w.status === "ready" || w.status === "busy");
  const hourlyBurn = activeWorkers.reduce((s, w) => s + w.hourly_rate, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Admin</h1>
          <p className="text-sm text-gray-500">GPU fleet management — workers across Vast.ai, RunPod, and Shadow.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={launchNewWorker} className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700">
            <Play className="h-4 w-4" /> Launch Worker
          </button>
          <button onClick={shutdownIdle} className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
            <Square className="h-4 w-4" /> Shutdown Idle
          </button>
          <button onClick={() => setShowSettings(!showSettings)} className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
            <Settings className="h-4 w-4" />
          </button>
          <button onClick={loadData} className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-white/[0.06] pb-px">
        <Link href="/admin" className="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-600">
          Dashboard
        </Link>
        <Link href="/admin/fleet" className="px-4 py-2 text-sm font-medium border-b-2 border-purple-500 text-purple-400">
          Fleet / GPU
        </Link>
        <Link href="/settings" className="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-600">
          Settings
        </Link>
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
              <input type="number" min={1} max={10} defaultValue={settings.max_instances} onBlur={(e) => saveSettings({ max_instances: parseInt(e.target.value) || 1 })} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-400 mb-1">Daily Budget (USD)</label>
              <input type="number" min={0.5} step={0.5} defaultValue={settings.daily_budget_usd} onBlur={(e) => saveSettings({ daily_budget_usd: parseFloat(e.target.value) || 5 })} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-400 mb-1">Idle Timeout (min, 0=off)</label>
              <input type="number" min={0} defaultValue={settings.idle_timeout_minutes} onBlur={(e) => saveSettings({ idle_timeout_minutes: parseInt(e.target.value) || 0 })} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-400 mb-1">Max Price/hr</label>
              <input type="number" min={0.05} step={0.05} defaultValue={settings.max_price_per_hour} onBlur={(e) => saveSettings({ max_price_per_hour: parseFloat(e.target.value) || 0.20 })} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none" />
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

      {/* Model Placement — what's loaded, what's in B2, disk/VRAM usage */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white">Model Placement (GPU ↔ B2)</h3>
          <button
            onClick={async () => {
              try {
                const resp = await fetch(`${API_BASE}/aios/v1/models/placements`);
                if (resp.ok) setModelPlacements(await resp.json());
              } catch {}
            }}
            className="text-[10px] text-purple-400 hover:text-purple-300 flex items-center gap-1"
          >
            <RefreshCw className="h-3 w-3" /> Refresh
          </button>
        </div>
        {modelPlacements ? (
          <div className="space-y-4">
            {/* Summary stats */}
            <div className="grid grid-cols-5 gap-2 text-center">
              <div className="rounded-lg bg-green-500/10 px-2 py-1">
                <p className="text-xs text-green-400 font-bold">{modelPlacements.summary?.loaded || 0}</p>
                <p className="text-[9px] text-gray-500">Loaded</p>
              </div>
              <div className="rounded-lg bg-blue-500/10 px-2 py-1">
                <p className="text-xs text-blue-400 font-bold">{modelPlacements.summary?.b2_only || 0}</p>
                <p className="text-[9px] text-gray-500">B2 Only</p>
              </div>
              <div className="rounded-lg bg-gray-500/10 px-2 py-1">
                <p className="text-xs text-gray-400 font-bold">{modelPlacements.summary?.archived || 0}</p>
                <p className="text-[9px] text-gray-500">Archived</p>
              </div>
              <div className="rounded-lg bg-amber-500/10 px-2 py-1">
                <p className="text-xs text-amber-400 font-bold">{modelPlacements.summary?.on_worker_disk || 0}</p>
                <p className="text-[9px] text-gray-500">On GPU Disk</p>
              </div>
              <div className="rounded-lg bg-purple-500/10 px-2 py-1">
                <p className="text-xs text-purple-400 font-bold">{modelPlacements.summary?.total_registered || 0}</p>
                <p className="text-[9px] text-gray-500">Registered</p>
              </div>
            </div>

            {/* Disk & VRAM usage */}
            {(modelPlacements.worker_disk?.total_gb || modelPlacements.worker_gpu?.vram_total_mb) && (
              <div className="grid grid-cols-2 gap-3">
                {modelPlacements.worker_disk?.total_gb ? (
                  <div className="rounded-lg border border-white/[0.04] bg-white/[0.02] p-3">
                    <p className="text-[10px] text-gray-500">GPU Disk</p>
                    <p className="text-sm font-bold text-white">{(modelPlacements.summary?.worker_disk_used_gb || 0).toFixed(1)}GB / {modelPlacements.worker_disk.total_gb.toFixed(0)}GB</p>
                    <div className="mt-1 h-1.5 rounded-full bg-white/[0.05]">
                      <div className="h-full bg-amber-500 rounded-full" style={{ width: `${modelPlacements.worker_disk.used_pct || 0}%` }} />
                    </div>
                  </div>
                ) : null}
                {modelPlacements.worker_gpu?.vram_total_mb ? (
                  <div className="rounded-lg border border-white/[0.04] bg-white/[0.02] p-3">
                    <p className="text-[10px] text-gray-500">VRAM ({modelPlacements.worker_gpu.name || "GPU"})</p>
                    <p className="text-sm font-bold text-white">{((modelPlacements.worker_gpu.vram_total_mb - (modelPlacements.summary?.gpu_vram_free_mb || 0)) / 1024).toFixed(1)}GB / {(modelPlacements.worker_gpu.vram_total_mb / 1024).toFixed(0)}GB</p>
                    <div className="mt-1 h-1.5 rounded-full bg-white/[0.05]">
                      <div className="h-full bg-purple-500 rounded-full" style={{ width: `${((modelPlacements.worker_gpu.vram_total_mb - (modelPlacements.summary?.gpu_vram_free_mb || 0)) / modelPlacements.worker_gpu.vram_total_mb * 100)}%` }} />
                    </div>
                  </div>
                ) : null}
              </div>
            )}

            {/* Worker Software */}
            {modelPlacements.worker_software.length > 0 && (
              <div>
                <p className="text-[10px] text-gray-500 uppercase mb-2">GPU Software</p>
                <div className="flex flex-wrap gap-2">
                  {modelPlacements.worker_software.map((s) => (
                    <span key={s.name} className="inline-flex items-center gap-1 rounded-full bg-white/[0.04] px-2.5 py-1 text-[10px] text-gray-300">
                      <span className={`h-1.5 w-1.5 rounded-full ${s.status === "running" ? "bg-green-400" : "bg-gray-500"}`} />
                      {s.name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Worker Models (actual files on disk) */}
            {modelPlacements.worker_models.length > 0 && (
              <div>
                <p className="text-[10px] text-gray-500 uppercase mb-2">Files on GPU Disk ({modelPlacements.worker_models.length})</p>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {modelPlacements.worker_models.map((m, i) => (
                    <div key={i} className="flex items-center justify-between rounded px-2 py-1 bg-white/[0.02]">
                      <span className="text-[10px] text-gray-300 truncate max-w-[200px]">{m.name}</span>
                      <span className="text-[10px] text-gray-500">{m.size_mb > 1024 ? `${(m.size_mb/1024).toFixed(1)}GB` : `${m.size_mb.toFixed(0)}MB`}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Registered Models */}
            <div>
              <p className="text-[10px] text-gray-500 uppercase mb-2">Registered Models ({modelPlacements.models.length})</p>
              <div className="space-y-1 max-h-60 overflow-y-auto">
                {modelPlacements.models.map((m) => (
                  <div key={m.id} className="flex items-center justify-between rounded-lg border border-white/[0.04] bg-white/[0.02] px-3 py-2">
                    <div>
                      <p className="text-xs font-medium text-white">{m.name}</p>
                      <p className="text-[10px] text-gray-500">{m.type} · {m.size_mb > 1024 ? `${(m.size_mb/1024).toFixed(1)}GB` : m.size_mb > 0 ? `${m.size_mb.toFixed(0)}MB` : "?"}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`rounded px-2 py-0.5 text-[9px] font-medium ${
                        m.state === "loaded" ? "bg-green-500/20 text-green-400" :
                        m.state === "b2_only" ? "bg-blue-500/20 text-blue-400" :
                        "bg-gray-500/20 text-gray-400"
                      }`}>{m.state === "b2_only" ? "B2" : m.state}</span>
                      {m.state === "loaded" && (
                        <button
                          onClick={async () => {
                            await fetch(`${API_BASE}/aios/v1/models/unload`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({model: m.name}) });
                            const resp = await fetch(`${API_BASE}/aios/v1/models/placements`); if (resp.ok) setModelPlacements(await resp.json());
                          }}
                          className="text-[9px] text-amber-400 hover:text-amber-300"
                        >
                          Unload
                        </button>
                      )}
                      {m.state === "b2_only" && (
                        <button
                          onClick={async () => {
                            await fetch(`${API_BASE}/aios/v1/models/ensure-loaded`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({model: m.name}) });
                            const resp = await fetch(`${API_BASE}/aios/v1/models/placements`); if (resp.ok) setModelPlacements(await resp.json());
                          }}
                          className="text-[9px] text-green-400 hover:text-green-300"
                        >
                          Load
                        </button>
                      )}
                      {m.state !== "archived" && (
                        <button
                          onClick={async () => {
                            await fetch(`${API_BASE}/aios/v1/models/archive`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({model_id: m.id}) });
                            const resp = await fetch(`${API_BASE}/aios/v1/models/placements`); if (resp.ok) setModelPlacements(await resp.json());
                          }}
                          className="text-[9px] text-gray-500 hover:text-gray-300"
                        >
                          Archive
                        </button>
                      )}
                      {m.state === "archived" && (
                        <button
                          onClick={async () => {
                            await fetch(`${API_BASE}/aios/v1/models/restore`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({model_id: m.id}) });
                            const resp = await fetch(`${API_BASE}/aios/v1/models/placements`); if (resp.ok) setModelPlacements(await resp.json());
                          }}
                          className="text-[9px] text-purple-400 hover:text-purple-300"
                        >
                          Restore
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <p className="text-xs text-gray-500">Click Refresh to load model placements from GPU worker</p>
        )}
      </div>
    </div>
  );
}
