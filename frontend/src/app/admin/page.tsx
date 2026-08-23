"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import { getServiceConnections, launchWorker, stopWorker, pauseWorker, resumeWorker, getVastStatus, getRunPodStatus, authFetch } from "@/lib/api";
import { useToast } from "@/components/toast";
import { PageLoading, PageOffline } from "@/components/page-state";
import {
  GovernedConfirmationDialog,
  useGovernedAction,
} from "@/components/governed-action";
import type { ActionResult } from "@/components/governed-action";
import { AdminTabs } from "./_components/admin-tabs";
import { SummaryCards } from "./_components/summary-cards";
import { GpuWorkerControl } from "./_components/gpu-worker-control";
import { ServiceConnectionsGrid } from "./_components/service-connections-grid";
import { ServiceToggles } from "./_components/service-toggles";
import { OutputDirectoryCard } from "./_components/output-directory-card";
import { WorkerServicesGrid } from "./_components/worker-services-grid";
import { QuickActions } from "./_components/quick-actions";
import { IntegrationsSection } from "./_components/integrations-section";
import type {
  GpuWorkerAction,
  OllamaPreference,
  RunPodStatus,
  VastStatus,
} from "./_components/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdminPage() {
  const [services, setServices] = useState<Record<string, Record<string, unknown>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [vastStatus, setVastStatus] = useState<VastStatus | null>(null);
  const [runpodStatus, setRunpodStatus] = useState<RunPodStatus | null>(null);
  const [workerAction, setWorkerAction] = useState<GpuWorkerAction>("idle");
  const [workerError, setWorkerError] = useState<string | null>(null);
  const [bootProgress, setBootProgress] = useState<string>("");
  const { dialogState, requestConfirmation, executeAction, cancel, retry } = useGovernedAction();
  const [serviceToggles, setServiceToggles] = useState<Record<string, boolean>>({
    comfyui: false,
    ollama: false,
  });
  const [serviceToggling, setServiceToggling] = useState<Record<string, boolean>>({});
  const [ollamaLocal, setOllamaLocal] = useState(false);
  const [ollamaPreference, setOllamaPreference] = useState<OllamaPreference>("auto");
  const [ollamaSource, setOllamaSource] = useState<string>("none");
  const [ollamaRemoteAvailable, setOllamaRemoteAvailable] = useState(false);
  const [outputDir, setOutputDir] = useState("~/AI-Studio/outputs");
  const [outputDirEditing, setOutputDirEditing] = useState(false);
  const [isOffline, setIsOffline] = useState(typeof navigator !== "undefined" ? !navigator.onLine : false);
  const { show } = useToast();

  // Offline detection
  useEffect(() => {
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  const loadData = useCallback(async () => {
    try {
      const [svcData, vastData, runpodData, ollamaData] = await Promise.allSettled([
        getServiceConnections(),
        getVastStatus(),
        getRunPodStatus(),
        authFetch(`${API_BASE}/api/v1/infrastructure/ollama/status`, { signal: AbortSignal.timeout(5000) }).then(r => r.json()),
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
        setOllamaPreference((od.preference as OllamaPreference) || "auto");
        setOllamaSource((od.active_source as string) || "none");
        setOllamaRemoteAvailable(Boolean((od.remote as Record<string, unknown>)?.available));
        if ((od.local as Record<string, unknown>)?.online) {
          setOllamaLocal(true);
          setServiceToggles((prev) => ({ ...prev, ollama: true }));
        }
      }
      // Fetch output directory
      try {
        const outResp = await authFetch(`${API_BASE}/api/v1/generate/output-dir`, { signal: AbortSignal.timeout(3000) });
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
    authFetch(`${API_BASE}/api/v1/infrastructure/services/health`, { signal: AbortSignal.timeout(5000) })
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
      // Confirm before stopping via governed dialog
      requestConfirmation(
        {
          actionKey: "stop-worker",
          riskTier: "elevated",
          verb: "Stop",
          resourceName: "GPU Worker Instance",
          resourceType: "GPU Worker",
          consequence: "This will terminate the GPU instance and end billing immediately. Any running jobs will be interrupted.",
          costDisclosure: vastStatus?.instance_info?.price_per_hour
            ? `Current rate: $${(vastStatus.instance_info.price_per_hour as number).toFixed(2)}/hr`
            : undefined,
        },
        async (): Promise<ActionResult> => {
          setWorkerAction("stopping");
          try {
            await stopWorker();
            await new Promise((r) => setTimeout(r, 2000));
            await loadData();
            return { success: true };
          } catch (err: unknown) {
            setWorkerError((err as Error)?.message || "Failed to stop worker");
            return { success: false, error: (err as Error)?.message || "Failed to stop worker" };
          } finally {
            setWorkerAction("idle");
          }
        }
      );
      return;
    } else {
      // Launch worker (async — backend returns immediately, we poll for progress)
      setWorkerAction("launching");
      setWorkerError(null);
      setBootProgress("Finding best GPU...");
      try {
        await launchWorker({ max_price: 1.5, min_vram_gb: 24, num_candidates: 3 });
        // Now poll /worker/progress until ready or error
        let attempts = 0;
        const maxAttempts = 120; // 10 minutes max (5s intervals)
        while (attempts < maxAttempts) {
          await new Promise((r) => setTimeout(r, 5000));
          attempts++;
          try {
            const resp = await authFetch(`${API_BASE}/api/v1/infrastructure/worker/progress`);
            const progress = await resp.json();
            const status = progress.status;
            // Update the progress message for the UI
            if (progress.progress_message) {
              setBootProgress(progress.progress_message);
            }
            if (status === "ready") {
              setBootProgress("");
              show("GPU worker is ready!", "success");
              break;
            }
            if (status === "error") {
              setBootProgress("");
              setWorkerError(progress.progress_message || "Worker boot failed");
              break;
            }
            if (status === "no_session") {
              setBootProgress("");
              break;
            }
            // Still booting — continue polling
          } catch {
            // Network error polling — ignore, retry
          }
        }
        await loadData();
      } catch (err: unknown) {
        setBootProgress("");
        setWorkerError((err as Error)?.message || "Failed to launch worker");
      } finally {
        setWorkerAction("idle");
        setBootProgress("");
      }
    }
  }

  async function handlePause() {
    requestConfirmation(
      {
        actionKey: "pause-worker",
        riskTier: "standard",
        verb: "Pause",
        resourceName: "GPU Worker Instance",
        resourceType: "GPU Worker",
        consequence: "Billing will stop but the instance state is preserved. You can resume later without re-provisioning.",
      },
      async (): Promise<ActionResult> => {
        setWorkerAction("pausing");
        setWorkerError(null);
        try {
          await pauseWorker();
          await new Promise((r) => setTimeout(r, 2000));
          await loadData();
          return { success: true };
        } catch (err: unknown) {
          setWorkerError((err as Error)?.message || "Failed to pause");
          return { success: false, error: (err as Error)?.message || "Failed to pause" };
        } finally {
          setWorkerAction("idle");
        }
      }
    );
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
      const resp = await authFetch(`${API_BASE}/api/v1/infrastructure/services/` + serviceName + "/toggle", {
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

  async function handleOllamaPreferenceChange(pref: OllamaPreference) {
    setOllamaPreference(pref);
    try {
      await authFetch(`${API_BASE}/api/v1/infrastructure/ollama/preference`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preference: pref }),
      });
      show(`Ollama preference: ${pref}`, "success");
    } catch {
      show("Failed to update preference", "error");
    }
  }

  async function handleSaveOutputDir() {
    try {
      const resp = await authFetch(`${API_BASE}/api/v1/generate/output-dir`, {
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
  }

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [svcData, vastData, runpodData, ollamaData] = await Promise.allSettled([
          getServiceConnections(),
          getVastStatus(),
          getRunPodStatus(),
          authFetch(`${API_BASE}/api/v1/infrastructure/ollama/status`, { signal: AbortSignal.timeout(5000) }).then(r => r.json()),
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
          setOllamaPreference((od.preference as OllamaPreference) || "auto");
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

  const summary = (services?.summary || {}) as Record<string, number>;
  const svcList = (services?.services || {}) as Record<string, Record<string, unknown>>;
  const gpuActive = vastStatus?.instance_active || runpodStatus?.instance_active || false;
  const gpuPaused = Boolean((vastStatus?.instance_paused || runpodStatus?.instance_paused) && !gpuActive);
  const activeProvider = vastStatus?.instance_active ? "Vast.ai" : runpodStatus?.instance_active ? "RunPod" : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-content-primary">Admin</h1>
          <p className="text-sm text-content-muted">Provider connections, infrastructure, and platform settings.</p>
        </div>
        {!loading && (
        <button
          onClick={refresh}
          className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-secondary hover:bg-surface-active"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </button>
        )}
      </div>

      {/* Tab Navigation */}
      <AdminTabs active="dashboard" />

      {isOffline && <PageOffline hasData={services !== null} />}

      {loading ? (
        <PageLoading resource="services" />
      ) : (
      <>
      {/* Summary */}
      <SummaryCards
        summary={summary}
        vastStatus={vastStatus}
        runpodStatus={runpodStatus}
        gpuActive={gpuActive}
        gpuPaused={gpuPaused}
        activeProvider={activeProvider}
      />

      {/* GPU Worker Control — single button to launch/stop + pause */}
      <GpuWorkerControl
        vastStatus={vastStatus}
        runpodStatus={runpodStatus}
        gpuActive={gpuActive}
        gpuPaused={gpuPaused}
        activeProvider={activeProvider}
        workerAction={workerAction}
        bootProgress={bootProgress}
        workerError={workerError}
        onToggleWorker={handleWorkerToggle}
        onPause={handlePause}
        onResume={handleResume}
      />

      {/* Service Connections — LIVE */}
      <ServiceConnectionsGrid
        services={svcList}
        gpuActive={gpuActive}
        vastApiConnected={Boolean(vastStatus?.api_connected)}
      />

      {/* Services Toggle — Smart Logic */}
      <ServiceToggles
        gpuActive={gpuActive}
        ollamaLocal={ollamaLocal}
        ollamaSource={ollamaSource}
        ollamaRemoteAvailable={ollamaRemoteAvailable}
        ollamaPreference={ollamaPreference}
        serviceToggles={serviceToggles}
        serviceToggling={serviceToggling}
        onToggleService={(name) => { toggleService(name); }}
        onOllamaPreferenceChange={handleOllamaPreferenceChange}
        onCheckAgain={() => loadData()}
      />

      {/* Output Directory */}
      <OutputDirectoryCard
        outputDir={outputDir}
        editing={outputDirEditing}
        onEditingChange={setOutputDirEditing}
        onDirChange={setOutputDir}
        onSave={handleSaveOutputDir}
      />

      {/* Worker Services Status */}
      <WorkerServicesGrid gpuActive={gpuActive} />

      {/* Quick Actions */}
      <QuickActions />

      {/* Integrations Status */}
      <IntegrationsSection ollamaLocal={ollamaLocal} />

      {/* Checked timestamp */}
      {services?.checked_at && (
        <p className="text-[10px] text-gray-600 text-right">
          Last checked: {new Date(String(services.checked_at)).toLocaleTimeString()} • Auto-refreshes every 15s
        </p>
      )}
      </>
      )}

      {/* Governed Confirmation Dialog */}
      <GovernedConfirmationDialog
        dialogState={dialogState}
        onConfirm={executeAction}
        onCancel={cancel}
        onRetry={retry}
      />
    </div>
  );
}
