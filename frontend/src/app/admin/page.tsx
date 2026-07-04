"use client";

import { useEffect, useState } from "react";
import { Settings, Server, DollarSign, Shield, Loader2, RefreshCw, Power } from "lucide-react";
import { getServiceConnections, launchWorker, stopWorker, getFleetStatus } from "@/lib/api";

export default function AdminPage() {
  const [services, setServices] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [launchStatus, setLaunchStatus] = useState<{
    state: "idle" | "launching" | "success" | "error";
    gpu_name?: string;
    price?: number;
    error?: string;
  }>({ state: "idle" });
  const [serviceToggles, setServiceToggles] = useState<Record<string, boolean>>({
    comfyui: false,
    ollama: false,
  });
  const [serviceToggling, setServiceToggling] = useState<Record<string, boolean>>({});

  async function loadServices() {
    try {
      const data = await getServiceConnections();
      setServices(data);
    } catch {
      setServices(null);
    } finally {
      setLoading(false);
    }
  }

  async function refresh() {
    setRefreshing(true);
    await loadServices();
    setRefreshing(false);
  }

  async function toggleService(serviceName: string) {
    const newEnabled = !serviceToggles[serviceName];
    setServiceToggles((prev) => ({ ...prev, [serviceName]: newEnabled }));
    setServiceToggling((prev) => ({ ...prev, [serviceName]: true }));
    try {
      const resp = await fetch(`http://localhost:8000/api/v1/infrastructure/services/${serviceName}/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: newEnabled }),
      });
      if (!resp.ok) throw new Error("Toggle failed");
    } catch {
      // Revert on failure
      setServiceToggles((prev) => ({ ...prev, [serviceName]: !newEnabled }));
      alert(`Failed to toggle ${serviceName}. Please try again.`);
    } finally {
      setServiceToggling((prev) => ({ ...prev, [serviceName]: false }));
    }
  }

  useEffect(() => { loadServices(); }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
      </div>
    );
  }

  const summary = services?.summary || {};
  const svcList = services?.services || {};

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
          <p className="text-xs text-gray-500">Disconnected</p>
          <p className="text-2xl font-bold text-gray-500">{summary.disconnected || 0}</p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
          <p className="text-xs text-gray-500">Health</p>
          <p className={`text-2xl font-bold ${summary.health === "healthy" ? "text-green-400" : "text-amber-400"}`}>
            {summary.health || "?"}
          </p>
        </div>
      </div>

      {/* Service Connections — LIVE */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3">Service Connections</h3>
        <div className="grid grid-cols-4 gap-3">
          {Object.entries(svcList).map(([name, info]: [string, any]) => (
            <div key={name} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-white capitalize">
                  {name.replace(/_/g, " ")}
                </span>
                <span className={`h-2.5 w-2.5 rounded-full ${info.connected ? "bg-green-500" : "bg-gray-600"}`} />
              </div>
              <p className={`text-xs font-medium ${info.connected ? "text-green-400" : "text-gray-500"}`}>
                {info.connected ? "Connected" : info.mode || "Offline"}
              </p>
              <p className="text-[10px] text-gray-500 mt-1">
                {info.connected
                  ? (info.username || info.bucket || info.version || info.cached_models + " models" || "OK")
                  : (info.error || info.note || "Not configured")}
              </p>
              {info.response_ms !== undefined && (
                <p className="text-[10px] text-gray-600 mt-1">{info.response_ms.toFixed(0)}ms response</p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* GPU Services Toggle */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3">Services</h3>
        <div className="grid grid-cols-2 gap-4">
          {[
            { key: "comfyui", name: "ComfyUI", desc: "Image & video generation engine on GPU worker" },
            { key: "ollama", name: "Ollama on Worker", desc: "LLM inference service running on GPU worker" },
          ].map((svc) => (
            <div key={svc.key} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Power className={`h-5 w-5 ${serviceToggles[svc.key] ? "text-green-400" : "text-gray-500"}`} />
                <div>
                  <p className="text-sm font-medium text-white">{svc.name}</p>
                  <p className="text-xs text-gray-500">{svc.desc}</p>
                </div>
              </div>
              <button
                onClick={() => toggleService(svc.key)}
                disabled={serviceToggling[svc.key]}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  serviceToggles[svc.key] ? "bg-purple-600" : "bg-gray-700"
                } ${serviceToggling[svc.key] ? "opacity-50" : ""}`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                    serviceToggles[svc.key] ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <Server className="h-6 w-6 text-purple-400 mb-3" />
          <h3 className="text-sm font-semibold text-white">GPU Workers</h3>
          <p className="text-xs text-gray-500 mt-1">Launch, monitor, and manage GPU fleet</p>

          {/* Launch Status Card */}
          {launchStatus.state === "launching" && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-purple-500/20 bg-purple-500/5 px-3 py-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-purple-400" />
              <span className="text-xs text-purple-300">Launching worker...</span>
            </div>
          )}
          {launchStatus.state === "success" && (
            <div className="mt-3 rounded-lg border border-green-500/20 bg-green-500/5 px-3 py-2">
              <p className="text-xs font-medium text-green-400">Worker online</p>
              <p className="text-[11px] text-green-300/70 mt-0.5">
                {launchStatus.gpu_name} @ ${launchStatus.price?.toFixed(2)}/hr
              </p>
            </div>
          )}
          {launchStatus.state === "error" && (
            <div className="mt-3 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
              <p className="text-xs font-medium text-red-400">Launch failed</p>
              <p className="text-[11px] text-red-300/70 mt-0.5">{launchStatus.error}</p>
            </div>
          )}

          <button
            onClick={async () => {
              setLaunchStatus({ state: "launching" });
              try {
                const result = await launchWorker({ max_price: 1.5, min_vram_gb: 24, num_candidates: 3 });
                setLaunchStatus({
                  state: "success",
                  gpu_name: result.gpu_name || result.worker?.gpu_name || "GPU",
                  price: result.price_per_hour || result.worker?.price_per_hour || 0,
                });
                refresh();
              } catch (err: any) {
                setLaunchStatus({
                  state: "error",
                  error: err?.message || "Unknown error",
                });
              }
            }}
            disabled={launchStatus.state === "launching"}
            className="mt-3 rounded-lg bg-purple-600/20 px-3 py-1.5 text-xs text-purple-400 hover:bg-purple-600/30 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {launchStatus.state === "launching" ? "Launching..." : "Launch Worker"}
          </button>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <DollarSign className="h-6 w-6 text-green-400 mb-3" />
          <h3 className="text-sm font-semibold text-white">Cost Controls</h3>
          <p className="text-xs text-gray-500 mt-1">Budget limits, spend tracking, alerts</p>
          <button className="mt-3 rounded-lg bg-green-600/20 px-3 py-1.5 text-xs text-green-400 hover:bg-green-600/30">
            View Costs
          </button>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <Shield className="h-6 w-6 text-amber-400 mb-3" />
          <h3 className="text-sm font-semibold text-white">Provider Reputation</h3>
          <p className="text-xs text-gray-500 mt-1">Host reliability, blacklist, preferred hosts</p>
          <button className="mt-3 rounded-lg bg-amber-600/20 px-3 py-1.5 text-xs text-amber-400 hover:bg-amber-600/30">
            View Reputation
          </button>
        </div>
      </div>

      {/* Checked timestamp */}
      {services?.checked_at && (
        <p className="text-[10px] text-gray-600 text-right">
          Last checked: {new Date(services.checked_at).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
