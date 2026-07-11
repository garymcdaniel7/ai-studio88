"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Settings, Server, DollarSign, Shield, Loader2, RefreshCw, Power, Pause, Play, Square } from "lucide-react";
import { getServiceConnections, launchWorker, stopWorker, pauseWorker, resumeWorker, getVastStatus, getRunPodStatus } from "@/lib/api";
import { useToast } from "@/components/toast";

interface VastStatus {
  api_connected: boolean;
  instance_active: boolean;
  instance_paused: boolean;
  balance: number;
  instance_info: {
    id: number;
    gpu_name: string;
    price_per_hour: number;
    status: string;
  } | null;
  error?: string;
}

interface RunPodStatus {
  provider: string;
  api_connected: boolean;
  instance_active: boolean;
  instance_paused: boolean;
  balance: number;
  spend_per_hr?: number;
  instance_info: {
    id: string;
    gpu_name: string;
    price_per_hour: number;
    status: string;
    name?: string;
  } | null;
  total_pods?: number;
  active_pods?: number;
  error?: string;
}

export default function AdminPage() {
  const [services, setServices] = useState<Record<string, Record<string, unknown>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [vastStatus, setVastStatus] = useState<VastStatus | null>(null);
  const [runpodStatus, setRunpodStatus] = useState<RunPodStatus | null>(null);
  const [workerAction, setWorkerAction] = useState<"idle" | "launching" | "stopping" | "pausing" | "resuming">("idle");
  const [workerError, setWorkerError] = useState<string | null>(null);
  const [serviceToggles, setServiceToggles] = useState<Record<string, boolean>>({
    comfyui: false,
    ollama: false,
  });
  const [serviceToggling, setServiceToggling] = useState<Record<string, boolean>>({});
  const [ollamaLocal, setOllamaLocal] = useState(false);
  const [ollamaPreference, setOllamaPreference] = useState<"auto" | "local" | "remote">("auto");
  const [ollamaSource, setOllamaSource] = useState<string>("none");
  const [ollamaRemoteAvailable, setOllamaRemoteAvailable] = useState(false);
  const [outputDir, setOutputDir] = useState("~/AI-Studio/outputs");
  const [outputDirEditing, setOutputDirEditing] = useState(false);
  const { show } = useToast();

  const loadData = useCallback(async () => {
    try {
      const [svcData, vastData, runpodData, ollamaData] = await Promise.allSettled([
        getServiceConnections(),
        getVastStatus(),
        getRunPodStatus(),
        fetch(`${API_BASE}/api/v1/infrastructure/ollama/status`, { signal: AbortSignal.timeout(5000) }).then(r => r.json()),
      ]);
      if (svcData.status === "fulfilled") {
        const data = svcData.value as Record<string, Record<string, unknown>>;
        setServices(data);
        // Sync toggle state from actual service connectivity
        const svcs = (data?.services || {}) as Record<string, Record<string, unknown>>;
        if (svcs?.comfyui?.connected) {
          setServiceToggles((prev) => ({ ...prev, comfyui: true }));
        }
        if (svcs?.ollama?.connected) {
          setOllamaLocal(true);
          setServiceToggles((prev) => ({ ...prev, ollama: true }));
        }
      }
      if (vastData.status === "fulfilled") setVastStatus(vastData.value);
      if (runpodData.status === "fulfilled") setRunpodStatus(runpodData.value);
      if (ollamaData.status === "fulfilled") {
        const od = ollamaData.value as Record<string, unknown>;
        setOllamaPreference((od.preference as "auto" | "local" | "remote") || "auto");
        setOllamaSource((od.active_source as string) || "none");
        setOllamaRemoteAvailable(Boolean((od.remote as Record<string, unknown>)?.available));
        if ((od.local as Record<string, unknown>)?.online) {
          setOllamaLocal(true);
          setServiceToggles((prev) => ({ ...prev, ollama: true }));
        }
      }
      // Fetch output directory
      try {
        const outResp = await fetch(`${API_BASE}/api/v1/generate/output-dir`, { signal: AbortSignal.timeout(3000) });
        if (outResp.ok) {
          const outData = await outResp.json();
          setOutputDir(outData.path || "~/AI-Studio/outputs");
        }
      } catch {}
    } catch {
      setServices(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Check actual service availability on mount (via backend to avoid CORS)
  useEffect(() => {
    fetch(`${API_BASE}/api/v1/infrastructure/services/health`, { signal: AbortSignal.timeout(5000) })
      .then((r) => r.json())
      .then((data) => {
        if (data?.comfyui?.online) {
          setServiceToggles((prev) => ({ ...prev, comfyui: true }));
        }
        if (data?.ollama?.online) {
          setOllamaLocal(true);
          setServiceToggles((prev) => ({ ...prev, ollama: true }));
        }
      })
      .catch(() => {});
  }, []);

  async function refresh() {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  }

  async function handleWorkerToggle() {
    const isActive = vastStatus?.instance_active;
    setWorkerError(null);

    if (isActive) {
      // Confirm before stopping
      if (!confirm("Stop the GPU worker? This will terminate the instance and end billing.")) return;
      // Stop worker
      setWorkerAction("stopping");
      try {
        await stopWorker();
        await new Promise((r) => setTimeout(r, 2000));
        await loadData();
      } catch (err: unknown) {
        setWorkerError((err as Error)?.message || "Failed to stop worker");
      } finally {
        setWorkerAction("idle");
      }
    } else {
      // Launch worker
      setWorkerAction("launching");
      try {
        await launchWorker({ max_price: 1.5, min_vram_gb: 24, num_candidates: 3 });
        await new Promise((r) => setTimeout(r, 3000));
        await loadData();
      } catch (err: unknown) {
        setWorkerError((err as Error)?.message || "Failed to launch worker");
      } finally {
        setWorkerAction("idle");
      }
    }
  }

  async function handlePause() {
    if (!confirm("Pause the GPU worker? Billing will stop but instance state is preserved.")) return;
    setWorkerAction("pausing");
    setWorkerError(null);
    try {
      await pauseWorker();
      await new Promise((r) => setTimeout(r, 2000));
      await loadData();
    } catch (err: unknown) {
      setWorkerError((err as Error)?.message || "Failed to pause");
    } finally {
      setWorkerAction("idle");
    }
  }

  async function handleResume() {
    setWorkerAction("resuming");
    setWorkerError(null);
    try {
      await resumeWorker();
      await new Promise((r) => setTimeout(r, 3000));
      await loadData();
    } catch (err: unknown) {
      setWorkerError((err as Error)?.message || "Failed to resume");
    } finally {
      setWorkerAction("idle");
    }
  }

  async function toggleService(serviceName: string) {
    const gpuActive = vastStatus?.instance_active;
    const isOllamaLocal = serviceName === "ollama" && ollamaLocal;

    // Prevent toggling ComfyUI without GPU
    if (serviceName === "comfyui" && !gpuActive) {
      show("ComfyUI requires an active GPU worker. Launch a worker first.", "info");
      return;
    }
    // Prevent toggling Ollama without GPU or local
    if (serviceName === "ollama" && !gpuActive && !isOllamaLocal) {
      show("Ollama requires either a local installation (port 11434) or an active GPU worker.", "info");
      return;
    }

    const newEnabled = !serviceToggles[serviceName];
    setServiceToggles((prev) => ({ ...prev, [serviceName]: newEnabled }));
    setServiceToggling((prev) => ({ ...prev, [serviceName]: true }));
    try {
      const resp = await fetch(`${API_BASE}/api/v1/infrastructure/services/` + serviceName + "/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: newEnabled, force_local: isOllamaLocal }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || "Toggle failed");
      }
    } catch (err: unknown) {
      setServiceToggles((prev) => ({ ...prev, [serviceName]: !newEnabled }));
      show((err as Error).message || "Failed to toggle service", "error");
    } finally {
      setServiceToggling((prev) => ({ ...prev, [serviceName]: false }));
    }
  }

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [svcData, vastData, runpodData, ollamaData] = await Promise.allSettled([
          getServiceConnections(),
          getVastStatus(),
          getRunPodStatus(),
          fetch(`${API_BASE}/api/v1/infrastructure/ollama/status`, { signal: AbortSignal.timeout(5000) }).then(r => r.json()),
        ]);
        if (!active) return;
        if (svcData.status === "fulfilled") {
          const data = svcData.value as Record<string, Record<string, unknown>>;
          setServices(data);
          // Sync toggle state from actual service connectivity
          const svcs = (data?.services || {}) as Record<string, Record<string, unknown>>;
          if (svcs?.comfyui?.connected) {
            setServiceToggles((prev) => ({ ...prev, comfyui: true }));
          }
          if (svcs?.ollama?.connected) {
            setOllamaLocal(true);
            setServiceToggles((prev) => ({ ...prev, ollama: true }));
          }
        }
        if (vastData.status === "fulfilled") setVastStatus(vastData.value);
        if (runpodData.status === "fulfilled") setRunpodStatus(runpodData.value);
        if (ollamaData.status === "fulfilled") {
          const od = ollamaData.value as Record<string, unknown>;
          setOllamaPreference((od.preference as "auto" | "local" | "remote") || "auto");
          setOllamaSource((od.active_source as string) || "none");
          setOllamaRemoteAvailable(Boolean((od.remote as Record<string, unknown>)?.available));
        }
      } catch {
        if (!active) return;
        setServices(null);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  // Auto-refresh every 15s
  useEffect(() => {
    const interval = setInterval(() => { loadData(); }, 15000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
      </div>
    );
  }

  const summary = (services?.summary || {}) as Record<string, number>;
  const svcList = (services?.services || {}) as Record<string, Record<string, unknown>>;
  const gpuActive = vastStatus?.instance_active || runpodStatus?.instance_active || false;
  const gpuPaused = (vastStatus?.instance_paused || runpodStatus?.instance_paused) && !gpuActive;
  const activeProvider = vastStatus?.instance_active ? "Vast.ai" : runpodStatus?.instance_active ? "RunPod" : null;
  const totalBalance = (vastStatus?.balance || 0) + (runpodStatus?.balance || 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Admin</h1>
          <p className="text-sm text-gray-500">Provider connections, infrastructure, and platform settings.</p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
          <p className="text-xs text-gray-500">Total Services</p>
          <p className="text-2xl font-bold text-white">{summary.total_services || 0}</p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
          <p className="text-xs text-gray-500">Connected</p>
          <p className="text-2xl font-bold text-green-400">{summary.connected || 0}</p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
          <p className="text-xs text-gray-500">GPU Balance</p>
          <p className="text-2xl font-bold text-amber-400">${totalBalance.toFixed(2)}</p>
          <p className="text-[10px] text-gray-600 mt-0.5">
            {vastStatus?.api_connected && `V: $${(vastStatus.balance || 0).toFixed(2)}`}
            {vastStatus?.api_connected && runpodStatus?.api_connected && " · "}
            {runpodStatus?.api_connected && `R: $${(runpodStatus.balance || 0).toFixed(2)}`}
          </p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
          <p className="text-xs text-gray-500">GPU Status</p>
          <p className={`text-2xl font-bold ${gpuActive ? "text-green-400" : gpuPaused ? "text-amber-400" : "text-gray-500"}`}>
            {gpuActive ? "Active" : gpuPaused ? "Paused" : "Off"}
          </p>
          {activeProvider && <p className="text-[10px] text-gray-600 mt-0.5">{activeProvider}</p>}
        </div>
      </div>

      {/* GPU Worker Control — single button to launch/stop + pause */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Server className="h-6 w-6 text-purple-400" />
            <div>
              <h3 className="text-sm font-semibold text-white">GPU Worker</h3>
              <p className="text-xs text-gray-500">
                {gpuActive
                  ? `${activeProvider}: ${
                      vastStatus?.instance_active
                        ? `${vastStatus?.instance_info?.gpu_name} @ $${vastStatus?.instance_info?.price_per_hour?.toFixed(2)}/hr`
                        : `${runpodStatus?.instance_info?.gpu_name} @ $${runpodStatus?.instance_info?.price_per_hour?.toFixed(2)}/hr`
                    }`
                  : gpuPaused
                    ? "Instance paused (no billing)"
                    : "No instance running"}
              </p>
            </div>
          </div>
          {/* Vast.ai connection indicator */}
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${
              gpuActive ? "bg-green-500" : vastStatus?.api_connected ? "bg-amber-400" : "bg-gray-600"
            }`} />
            <span className={`text-xs ${
              gpuActive ? "text-green-400" : vastStatus?.api_connected ? "text-amber-400" : "text-gray-500"
            }`}>
              {gpuActive ? "GPU Active" : vastStatus?.api_connected ? "Vast.ai Connected" : "Not Connected"}
            </span>
          </div>
        </div>

        {workerError && (
          <div className="mb-3 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
            <p className="text-xs text-red-400">{workerError}</p>
          </div>
        )}

        <div className="flex items-center gap-3">
          {/* Main Launch/Stop Button */}
          <button
            onClick={handleWorkerToggle}
            disabled={workerAction !== "idle"}
            className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors disabled:opacity-50 ${
              gpuActive
                ? "bg-red-600 text-white hover:bg-red-700"
                : "bg-purple-600 text-white hover:bg-purple-700"
            }`}
          >
            {workerAction === "launching" ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Launching...</>
            ) : workerAction === "stopping" ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Stopping...</>
            ) : gpuActive ? (
              <><Square className="h-4 w-4" /> Stop Worker</>
            ) : (
              <><Play className="h-4 w-4" /> Launch Worker</>
            )}
          </button>

          {/* Pause/Resume Button */}
          {gpuActive && (
            <button
              onClick={handlePause}
              disabled={workerAction !== "idle"}
              className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm font-medium text-amber-400 hover:bg-amber-500/20 disabled:opacity-50"
            >
              {workerAction === "pausing" ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Pausing...</>
              ) : (
                <><Pause className="h-4 w-4" /> Pause (Save $)</>
              )}
            </button>
          )}
          {gpuPaused && (
            <button
              onClick={handleResume}
              disabled={workerAction !== "idle"}
              className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-2.5 text-sm font-medium text-green-400 hover:bg-green-500/20 disabled:opacity-50"
            >
              {workerAction === "resuming" ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Resuming...</>
              ) : (
                <><Play className="h-4 w-4" /> Resume Instance</>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Service Connections — LIVE */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3">Service Connections</h3>
        <div className="grid grid-cols-4 gap-3">
          {Object.entries(svcList).map(([name, info]: [string, Record<string, unknown>]) => {
            const isConnected = Boolean(info.connected);
            // Determine dot color: green=active, amber=API connected but no instance, gray=offline
            let dotColor = "bg-gray-600";
            if (name === "vast_ai" || name === "vast") {
              if (gpuActive) dotColor = "bg-green-500";
              else if (vastStatus?.api_connected) dotColor = "bg-amber-400";
            } else if (info.connected) {
              dotColor = "bg-green-500";
            }

            return (
              <div key={name} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-white capitalize">
                    {name.replace(/_/g, " ")}
                  </span>
                  <span className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
                </div>
                <p className={`text-xs font-medium ${isConnected ? "text-green-400" : (name.includes("vast") && vastStatus?.api_connected) ? "text-amber-400" : "text-gray-500"}`}>
                  {isConnected ? "Connected" : (name.includes("vast") && vastStatus?.api_connected) ? "API Ready" : String(info.mode || "Offline")}
                </p>
                <p className="text-[10px] text-gray-500 mt-1">
                  {isConnected
                    ? String(info.username || info.bucket || info.version || (info.voices_available ? `${info.voices_available} voices` : "") || (info.cached_models ? `${info.cached_models} models` : "") || info.tier || "OK")
                    : String(info.error || info.note || "Not configured")}
                </p>
                {info.response_ms !== undefined && (
                  <p className="text-[10px] text-gray-600 mt-1">{(info.response_ms as number).toFixed(0)}ms response</p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* GPU Services Toggle — Smart Logic */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3">Services</h3>
        <div className="grid grid-cols-2 gap-4">
          {/* ComfyUI Toggle */}
          <div className={`rounded-xl border p-5 flex items-center justify-between ${
            (gpuActive || serviceToggles.comfyui) ? "border-white/[0.06] bg-[#12122a]" : "border-white/[0.04] bg-[#0d0d1f]"
          }`}>
            <div className="flex items-center gap-3">
              <Power className={`h-5 w-5 ${
                serviceToggles.comfyui ? "text-green-400" : (gpuActive || serviceToggles.comfyui) ? "text-gray-500" : "text-gray-700"
              }`} />
              <div>
                <p className={`text-sm font-medium ${(gpuActive || serviceToggles.comfyui) ? "text-white" : "text-gray-600"}`}>ComfyUI</p>
                <p className="text-xs text-gray-500">
                  {serviceToggles.comfyui ? "Connected (localhost:8188)" : "Image & video generation engine"}
                </p>
                {!(gpuActive || serviceToggles.comfyui) && (
                  <p className="text-[10px] text-amber-500/70 mt-0.5">Requires active GPU worker or SSH tunnel</p>
                )}
              </div>
            </div>
            <button
              onClick={() => toggleService("comfyui")}
              disabled={serviceToggling.comfyui || !(gpuActive || serviceToggles.comfyui)}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                serviceToggles.comfyui ? "bg-purple-600" : "bg-gray-700"
              } ${serviceToggling.comfyui || !(gpuActive || serviceToggles.comfyui) ? "opacity-40 cursor-not-allowed" : ""}`}
            >
              <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                serviceToggles.comfyui ? "translate-x-5" : "translate-x-0"
              }`} />
            </button>
          </div>

          {/* Ollama Toggle — Enhanced with source + preference */}
          <div className={`rounded-xl border p-5 ${
            (gpuActive || ollamaLocal || serviceToggles.ollama) ? "border-white/[0.06] bg-[#12122a]" : "border-white/[0.04] bg-[#0d0d1f]"
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Power className={`h-5 w-5 ${
                  serviceToggles.ollama ? "text-green-400" : (gpuActive || ollamaLocal) ? "text-gray-500" : "text-gray-700"
                }`} />
                <div>
                  <p className={`text-sm font-medium ${(gpuActive || ollamaLocal || serviceToggles.ollama) ? "text-white" : "text-gray-600"}`}>Ollama</p>
                  <p className="text-xs text-gray-500">
                    {serviceToggles.ollama
                      ? `Active — ${ollamaSource === "local" ? "Local (localhost:11434)" : ollamaSource === "remote" ? "Remote (GPU Worker)" : "Connected"}`
                      : "LLM for AI Brain"}
                  </p>
                </div>
              </div>
              <button
                onClick={() => toggleService("ollama")}
                disabled={serviceToggling.ollama || !(gpuActive || ollamaLocal || serviceToggles.ollama)}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  serviceToggles.ollama ? "bg-purple-600" : "bg-gray-700"
                } ${serviceToggling.ollama || !(gpuActive || ollamaLocal || serviceToggles.ollama) ? "opacity-40 cursor-not-allowed" : ""}`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                  serviceToggles.ollama ? "translate-x-5" : "translate-x-0"
                }`} />
              </button>
            </div>

            {/* Source badges + preference */}
            <div className="mt-3 flex items-center gap-2">
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                ollamaLocal ? "bg-green-500/10 text-green-400" : "bg-gray-700/50 text-gray-500"
              }`}>
                <span className={`h-1.5 w-1.5 rounded-full ${ollamaLocal ? "bg-green-400" : "bg-gray-600"}`} />
                Local
              </span>
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                ollamaRemoteAvailable ? "bg-blue-500/10 text-blue-400" : "bg-gray-700/50 text-gray-500"
              }`}>
                <span className={`h-1.5 w-1.5 rounded-full ${ollamaRemoteAvailable ? "bg-blue-400" : "bg-gray-600"}`} />
                Remote
              </span>
              <select
                value={ollamaPreference}
                onChange={async (e) => {
                  const pref = e.target.value as "auto" | "local" | "remote";
                  setOllamaPreference(pref);
                  try {
                    await fetch(`${API_BASE}/api/v1/infrastructure/ollama/preference`, {
                      method: "PUT",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ preference: pref }),
                    });
                    show(`Ollama preference: ${pref}`, "success");
                  } catch {
                    show("Failed to update preference", "error");
                  }
                }}
                className="ml-auto rounded-md border border-white/[0.08] bg-[#0d0d1f] px-2 py-0.5 text-[10px] text-gray-300 outline-none"
              >
                <option value="auto">Auto</option>
                <option value="local">Prefer Local</option>
                <option value="remote">Prefer Remote</option>
              </select>
            </div>

            {/* Not installed helper */}
            {!ollamaLocal && !ollamaRemoteAvailable && !serviceToggles.ollama && (
              <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5">
                <p className="text-[11px] text-amber-400 font-medium">Ollama not detected</p>
                <p className="text-[10px] text-gray-500 mt-0.5">
                  Install locally for free, private AI chat.
                </p>
                <div className="flex gap-2 mt-2">
                  <a
                    href="https://ollama.com/download"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded bg-purple-600/20 px-2 py-1 text-[10px] font-medium text-purple-400 hover:bg-purple-600/30 transition-colors"
                  >
                    Download Ollama
                  </a>
                  <button
                    onClick={() => loadData()}
                    className="rounded bg-white/[0.04] px-2 py-1 text-[10px] font-medium text-gray-400 hover:bg-white/[0.08] transition-colors"
                  >
                    Check Again
                  </button>
                </div>
              </div>
            )}

            {!(gpuActive || ollamaLocal || serviceToggles.ollama) && ollamaRemoteAvailable === false && ollamaLocal === false && (
              <p className="text-[10px] text-amber-500/70 mt-2">No GPU worker or local installation detected</p>
            )}
          </div>
        </div>
      </div>

      {/* Output Directory */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-white">Output Directory</h3>
          <button
            onClick={() => setOutputDirEditing(!outputDirEditing)}
            className="text-[10px] text-purple-400 hover:text-purple-300"
          >
            {outputDirEditing ? "Done" : "Change"}
          </button>
        </div>
        <p className="text-xs text-gray-500 mb-2">Generated images auto-save here</p>
        {outputDirEditing ? (
          <div className="flex gap-2">
            <input
              type="text"
              value={outputDir}
              onChange={(e) => setOutputDir(e.target.value)}
              className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-white font-mono focus:border-purple-500 focus:outline-none"
            />
            <button
              onClick={async () => {
                try {
                  const resp = await fetch(`${API_BASE}/api/v1/generate/output-dir`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ path: outputDir }),
                  });
                  if (resp.ok) {
                    show("Output directory updated", "success");
                    setOutputDirEditing(false);
                  } else {
                    const data = await resp.json();
                    show(data.detail || "Failed", "error");
                  }
                } catch {
                  show("Failed to update", "error");
                }
              }}
              className="rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700"
            >
              Save
            </button>
          </div>
        ) : (
          <p className="text-xs text-gray-300 font-mono bg-white/[0.03] rounded-lg px-3 py-2 truncate">
            {outputDir}
          </p>
        )}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <DollarSign className="h-6 w-6 text-green-400 mb-3" />
          <h3 className="text-sm font-semibold text-white">Cost Controls</h3>
          <p className="text-xs text-gray-500 mt-1">Budget limits, spend tracking, alerts</p>
          <Link href="/analytics" className="mt-3 inline-block rounded-lg bg-green-600/20 px-3 py-1.5 text-xs text-green-400 hover:bg-green-600/30">
            View Costs
          </Link>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <Shield className="h-6 w-6 text-amber-400 mb-3" />
          <h3 className="text-sm font-semibold text-white">Provider Reputation</h3>
          <p className="text-xs text-gray-500 mt-1">Host reliability, blacklist, preferred hosts</p>
          <Link href="/admin/fleet" className="mt-3 inline-block rounded-lg bg-amber-600/20 px-3 py-1.5 text-xs text-amber-400 hover:bg-amber-600/30">
            View Reputation
          </Link>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <Settings className="h-6 w-6 text-purple-400 mb-3" />
          <h3 className="text-sm font-semibold text-white">API Keys</h3>
          <p className="text-xs text-gray-500 mt-1">Manage ElevenLabs, OpenAI, and other keys</p>
          <Link href="/admin/keys" className="mt-3 inline-block rounded-lg bg-purple-600/20 px-3 py-1.5 text-xs text-purple-400 hover:bg-purple-600/30">
            Configure
          </Link>
        </div>
      </div>

      {/* Integrations Status */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3">Integrations</h3>
        <div className="grid grid-cols-3 gap-4">
          {/* ElevenLabs */}
          <div className="rounded-xl border border-amber-500/20 bg-[#12122a] p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-white">ElevenLabs</span>
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
            </div>
            <p className="text-xs text-amber-400 font-medium">Paid Plan Required</p>
            <p className="text-[10px] text-gray-500 mt-1">
              Free tier cannot use API voices. Upgrade at elevenlabs.io to enable voice generation.
            </p>
            <a href="https://elevenlabs.io/pricing" target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-[10px] text-purple-400 hover:text-purple-300 underline">
              View pricing →
            </a>
          </div>
          {/* Social Login */}
          <div className="rounded-xl border border-amber-500/20 bg-[#12122a] p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-white">Social Login (OAuth)</span>
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
            </div>
            <p className="text-xs text-amber-400 font-medium">Setup Required</p>
            <p className="text-[10px] text-gray-500 mt-1">
              Instagram/TikTok SSO needs a Meta Developer App. Register at developers.facebook.com, create an app, and add your OAuth credentials to .env.
            </p>
            <p className="text-[10px] text-gray-600 mt-1 font-mono">
              META_APP_ID=... META_APP_SECRET=...
            </p>
          </div>
          {/* Ollama B2 Cache */}
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-white">Ollama → B2 Cache</span>
              <span className={`h-2.5 w-2.5 rounded-full ${ollamaLocal ? "bg-green-500" : "bg-gray-600"}`} />
            </div>
            <p className={`text-xs font-medium ${ollamaLocal ? "text-green-400" : "text-gray-500"}`}>
              {ollamaLocal ? "Ollama detected locally" : "Not detected"}
            </p>
            <p className="text-[10px] text-gray-500 mt-1">
              Upload llama3.2 to B2 for GPU workers. Triggered from /models page or run manually.
            </p>
            <p className="text-[10px] text-gray-600 mt-1 font-mono">
              uv run python scripts/vast/cache_ollama_model.py --model llama3.2
            </p>
          </div>
        </div>
      </div>

      {/* Quick Links */}
      <div className="flex items-center gap-3">
        <Link href="/admin/fleet" className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
          <Server className="h-4 w-4" /> Fleet Management
        </Link>
        <Link href="/admin/keys" className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
          <Shield className="h-4 w-4" /> API Keys
        </Link>
      </div>

      {/* Checked timestamp */}
      {services?.checked_at && (
        <p className="text-[10px] text-gray-600 text-right">
          Last checked: {new Date(String(services.checked_at)).toLocaleTimeString()} • Auto-refreshes every 15s
        </p>
      )}
    </div>
  );
}
