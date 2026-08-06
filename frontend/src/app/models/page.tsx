"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState, useRef } from "react";
import {
  Cpu,
  HardDrive,
  Loader2,
  CheckCircle,
  XCircle,
  AlertCircle,
  Upload,
  X,
  Trash2,
  FolderOpen,
  Server,
} from "lucide-react";
import {
  getRegisteredModels,
  getAvailableModels,
  uploadModel,
  deleteModel,
  hardDeleteModel,
  getModelInventory,
  ModelUploadResponse,
  ModelInventory,
} from "@/lib/api";
import { useToast } from "@/components/toast";
import {
  GovernedConfirmationDialog,
  useGovernedAction,
} from "@/components/governed-action";
import type { ActionResult } from "@/components/governed-action";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Model {
  id: string;
  name: string;
  provider?: string;
  type?: string;
  family?: string;
  size?: string;
  b2_cached?: boolean;
  b2_path?: string;
  storage_path?: string;
  comfyui_path?: string;
  status?: string;
  required_vram_gb?: number;
  metadata?: Record<string, unknown>;
}

const MODEL_TYPES = [
  { value: "checkpoint", label: "Checkpoint" },
  { value: "lora", label: "LoRA" },
  { value: "vae", label: "VAE" },
  { value: "controlnet", label: "ControlNet" },
  { value: "ipadapter", label: "IP-Adapter" },
  { value: "upscaler", label: "Upscaler" },
  { value: "embedding", label: "Embedding" },
];

const MODEL_FAMILIES = [
  { value: "flux", label: "Flux" },
  { value: "sdxl", label: "SDXL" },
  { value: "sd15", label: "SD 1.5" },
  { value: "wan", label: "WAN" },
  { value: "ltx", label: "LTX" },
  { value: "hunyuan", label: "HunyuanVideo" },
  { value: "other", label: "Other" },
];

const ACCEPTED_EXTENSIONS = ".safetensors,.ckpt,.pt,.pth,.gguf,.bin";

import { usePageState } from "@/lib/page-state";
import { PageStateRenderer } from "@/components/page-state";

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function ModelsPage() {
  const [filter, setFilter] = useState<string>("all");
  const { show } = useToast();
  const { dialogState, requestConfirmation, executeAction, cancel, retry } = useGovernedAction();

  // Upload state (inline, no modal)
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [modelType, setModelType] = useState("checkpoint");
  const [family, setFamily] = useState("flux");
  const [name, setName] = useState("");
  const [triggerWords, setTriggerWords] = useState("");
  const [baseModel, setBaseModel] = useState("");
  const [strength, setStrength] = useState("0.7");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [inventory, setInventory] = useState<ModelInventory | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Unified page state for model loading
  const { state, data: models, error, freshness, isFetching, isOffline, retryAttempt, refresh, retry: retryFetch } = usePageState<Model[]>({
    fetcher: async () => {
      const registered = await getRegisteredModels();
      if (Array.isArray(registered) && registered.length > 0) {
        const deduped = Array.from(
          new Map(
            registered.map((m) => [
              ((m as Record<string, unknown>).id as string) ||
                ((m as Record<string, unknown>).name as string),
              m,
            ])
          ).values()
        );
        return deduped as unknown as Model[];
      } else {
        const available = await getAvailableModels();
        return Array.isArray(available) ? (available as unknown as Model[]) : [];
      }
    },
    refreshInterval: 30_000,
    hasActiveFilter: filter !== "all",
  });

  // Load inventory separately (non-critical)
  useEffect(() => {
    getModelInventory().then(setInventory).catch(() => {});
  }, []);

  const allModels = models || [];
  const filteredModels =
    filter === "all" ? allModels : allModels.filter((m) => m.type === filter);

  // --- Upload handlers ---
  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) {
      setFile(dropped);
      if (!name) setName(dropped.name.replace(/\.[^.]+$/, "").replace(/[_-]/g, " "));
      setShowForm(true);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      if (!name) setName(selected.name.replace(/\.[^.]+$/, "").replace(/[_-]/g, " "));
      setShowForm(true);
    }
  }

  function resetUpload() {
    setFile(null);
    setName("");
    setTriggerWords("");
    setBaseModel("");
    setStrength("0.7");
    setModelType("checkpoint");
    setFamily("flux");
    setProgress(0);
    setUploadError(null);
    setShowForm(false);
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setProgress(0);

    try {
      await uploadModel(
        file,
        {
          name: name || undefined,
          model_type: modelType,
          family,
          trigger_words: triggerWords || undefined,
          base_model: baseModel || undefined,
          recommended_strength: modelType === "lora" ? parseFloat(strength) : undefined,
        },
        (pct) => setProgress(pct),
      );
      show(`"${name || file.name}" uploaded successfully!`, "success");
      resetUpload();
      refresh();
    } catch (err) {
      setUploadError((err as Error).message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  // --- Model actions ---
  async function handleDelete(model: Model) {
    requestConfirmation(
      {
        actionKey: `archive-model-${model.id}`,
        riskTier: "standard",
        verb: "Archive",
        resourceName: model.name,
        resourceType: "Model",
        consequence: `"${model.name}" will be archived. It stays in B2 storage for re-download later.`,
      },
      async (): Promise<ActionResult> => {
        try {
          await deleteModel(model.id);
          refresh();
          show(`"${model.name}" archived.`, "success");
          return { success: true };
        } catch {
          show(`Failed to archive "${model.name}".`, "error");
          return { success: false, error: `Failed to archive "${model.name}".` };
        }
      }
    );
  }

  async function handleRestore(model: Model) {
    try {
      await fetch(`${API_BASE}/api/v1/models/${model.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "available" }),
      });
      refresh();
      show(`"${model.name}" restored.`, "success");
    } catch {
      show(`Failed to restore.`, "error");
    }
  }

  async function handleHardDelete(model: Model) {
    requestConfirmation(
      {
        actionKey: `delete-model-${model.id}`,
        riskTier: "critical",
        verb: "Delete Permanently",
        resourceName: model.name,
        resourceType: "Model",
        consequence: `"${model.name}" will be PERMANENTLY removed from B2 storage AND the registry. This cannot be undone.`,
        typedConfirmation: model.name,
        confirmLabel: "Delete Forever",
      },
      async (): Promise<ActionResult> => {
        try {
          await hardDeleteModel(model.id);
          refresh();
          show(`"${model.name}" permanently deleted.`, "success");
          return { success: true };
        } catch {
          show(`Failed to delete "${model.name}".`, "error");
          return { success: false, error: `Failed to delete "${model.name}".` };
        }
      }
    );
  }

  async function handleDeployToWorker(model: Model) {
    const comfyPath = model.comfyui_path || (model.metadata?.comfyui_path as string) || "";
    if (!comfyPath) {
      show("No ComfyUI path configured for this model.", "error");
      return;
    }
    show(`Deploying "${model.name}" to GPU worker...`, "info");
    try {
      const resp = await fetch(`${API_BASE}/api/v1/models/${model.id}/upload-to-gpu`, {
        method: "POST",
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error((body as Record<string, string>).detail || `HTTP ${resp.status}`);
      }
      refresh();
      show(`"${model.name}" deployed to worker!`, "success");
    } catch (err) {
      show(`Deploy failed: ${(err as Error).message}`, "error");
    }
  }

  async function handleFreeGpu(model: Model) {
    show(`Freeing GPU space for "${model.name}"...`, "info");
    try {
      await fetch(`${API_BASE}/api/v1/models/${model.id}/free-gpu`, { method: "POST" });
      refresh();
      show(`"${model.name}" removed from GPU. Still in B2.`, "success");
    } catch {
      show("Failed to free GPU space.", "error");
    }
  }

  return (
    <div className="space-y-6">
      {/* Header — always renders immediately */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-content-primary">Model Manager</h1>
          <p className="text-sm text-content-muted">
            Upload, manage, and deploy AI models to GPU workers.
          </p>
        </div>
      </div>

      <PageStateRenderer
        state={state}
        error={error}
        freshness={freshness}
        retryAttempt={retryAttempt}
        isOffline={isOffline}
        hasData={allModels.length > 0}
        resource="models"
        onRetry={retryFetch}
        onRefresh={refresh}
        onClearFilters={() => setFilter("all")}
      >
      {/* ============================================================== */}
      {/* DRAG & DROP UPLOAD ZONE — Always visible at top */}
      {/* ============================================================== */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => !showForm && inputRef.current?.click()}
        className={`rounded-2xl border-2 border-dashed transition-all duration-200 ${
          dragging
            ? "border-purple-500 bg-purple-500/10 scale-[1.01]"
            : showForm
              ? "border-border-default bg-surface-raised"
              : "border-border-strong bg-surface-raised hover:border-purple-500/50 hover:bg-purple-500/5 cursor-pointer"
        } ${showForm ? "p-6" : "p-8"}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          onChange={handleFileSelect}
          className="hidden"
        />

        {!showForm ? (
          /* Collapsed state — just the drop target */
          <div className="text-center">
            <Upload className="h-10 w-10 text-purple-400/60 mx-auto mb-3" />
            <p className="text-sm font-medium text-content-secondary">
              Drop a model file here to upload
            </p>
            <p className="text-xs text-content-muted mt-1">
              .safetensors, .ckpt, .pt, .pth, .gguf, .bin — up to 20 GB
            </p>
            <p className="text-[10px] text-content-muted mt-2">
              Checkpoints, LoRAs, VAEs, ControlNets, Upscalers, Embeddings
            </p>
          </div>
        ) : (
          /* Expanded state — file selected, show form */
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <CheckCircle className="h-5 w-5 text-green-400" />
                <div>
                  <p className="text-sm font-medium text-content-primary">{file?.name}</p>
                  <p className="text-xs text-content-tertiary">
                    {file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB` : ""}
                  </p>
                </div>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); resetUpload(); }}
                className="p-1.5 rounded-lg text-content-tertiary hover:text-content-primary hover:bg-surface-hover"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Form fields */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-xs font-medium text-content-tertiary mb-1">Model Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  placeholder="e.g. SDXL Turbo FP16"
                  className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-white placeholder:text-content-muted focus:border-purple-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-content-tertiary mb-1">Type</label>
                <select
                  value={modelType}
                  onChange={(e) => setModelType(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
                >
                  {MODEL_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-content-tertiary mb-1">Family</label>
                <select
                  value={family}
                  onChange={(e) => setFamily(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
                >
                  {MODEL_FAMILIES.map((f) => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* LoRA-specific fields */}
            {modelType === "lora" && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4 rounded-lg border border-blue-500/20 bg-blue-500/5 p-4">
                <div>
                  <label className="block text-xs font-medium text-blue-300 mb-1">Trigger Words</label>
                  <input
                    type="text"
                    value={triggerWords}
                    onChange={(e) => setTriggerWords(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    placeholder="e.g. ohwx, style_xyz"
                    className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-white placeholder:text-content-muted focus:border-purple-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-blue-300 mb-1">Base Model</label>
                  <input
                    type="text"
                    value={baseModel}
                    onChange={(e) => setBaseModel(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    placeholder="e.g. flux1-dev"
                    className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-white placeholder:text-content-muted focus:border-purple-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-blue-300 mb-1">Strength (0–1)</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={strength}
                    onChange={(e) => setStrength(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    className="w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
                  />
                </div>
              </div>
            )}

            {/* Error */}
            {uploadError && (
              <div className="flex items-center gap-2 rounded-lg border border-status-error/30 bg-status-error-muted px-3 py-2 mb-4">
                <AlertCircle className="h-4 w-4 text-status-error shrink-0" />
                <p className="text-xs text-red-300">{uploadError}</p>
              </div>
            )}

            {/* Progress */}
            {uploading && (
              <div className="mb-4">
                <div className="flex items-center justify-between text-xs text-content-tertiary mb-1">
                  <span>Uploading to B2...</span>
                  <span>{progress}%</span>
                </div>
                <div className="h-2 rounded-full bg-white/[0.05] overflow-hidden">
                  <div
                    className="h-full bg-purple-600 rounded-full transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Upload Button */}
            <button
              onClick={(e) => { e.stopPropagation(); handleUpload(); }}
              disabled={!file || uploading}
              className="flex items-center gap-2 rounded-lg bg-purple-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {uploading ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Uploading...</>
              ) : (
                <><Upload className="h-4 w-4" /> Upload & Register</>
              )}
            </button>
          </div>
        )}
      </div>

      {/* ============================================================== */}
      {/* WORKER INVENTORY PANEL */}
      {/* ============================================================== */}
      {inventory && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-4">
            <div className="flex items-center gap-2 mb-1">
              <Server className="h-4 w-4 text-status-success" />
              <span className="text-xs font-medium text-content-tertiary">On GPU</span>
            </div>
            <p className="text-xl font-bold text-content-primary">{inventory.on_gpu.count}</p>
            <p className="text-[10px] text-content-muted">Ready to generate</p>
          </div>
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-4">
            <div className="flex items-center gap-2 mb-1">
              <HardDrive className="h-4 w-4 text-blue-400" />
              <span className="text-xs font-medium text-content-tertiary">B2 Only</span>
            </div>
            <p className="text-xl font-bold text-content-primary">{inventory.b2_only.count}</p>
            <p className="text-[10px] text-content-muted">Need deploy to use</p>
          </div>
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-4">
            <div className="flex items-center gap-2 mb-1">
              <Cpu className="h-4 w-4 text-status-info" />
              <span className="text-xs font-medium text-content-tertiary">Total Active</span>
            </div>
            <p className="text-xl font-bold text-content-primary">{inventory.total_active}</p>
            <p className="text-[10px] text-content-muted">{inventory.total_size_gb} GB stored</p>
          </div>
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-4">
            <div className="flex items-center gap-2 mb-1">
              <Trash2 className="h-4 w-4 text-status-warning" />
              <span className="text-xs font-medium text-content-tertiary">Archived</span>
            </div>
            <p className="text-xl font-bold text-content-primary">{inventory.archived.count}</p>
            <p className="text-[10px] text-content-muted">Can restore anytime</p>
          </div>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-5 py-3">
          <AlertCircle className="h-5 w-5 text-amber-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-300">Could not load models</p>
            <p className="text-xs text-amber-400/60 mt-0.5">{error?.message}</p>
          </div>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 flex-wrap">
        {[{ value: "all", label: "All" }, ...MODEL_TYPES].map((t) => (
          <button
            key={t.value}
            onClick={() => setFilter(t.value)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              filter === t.value
                ? "bg-interactive-default text-white"
                : "bg-surface-hover text-content-tertiary hover:text-content-primary hover:bg-surface-active"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Models Grid */}
      {filteredModels.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredModels.map((model) => (
            <ModelCard
              key={model.id || model.name}
              model={model}
              onDelete={() => handleDelete(model)}
              onHardDelete={() => handleHardDelete(model)}
              onRestore={() => handleRestore(model)}
              onDeploy={() => handleDeployToWorker(model)}
              onFreeGpu={() => handleFreeGpu(model)}
            />
          ))}
        </div>
      ) : (
        !error && (
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-8 text-center">
            <Cpu className="h-12 w-12 text-content-muted mx-auto mb-3" />
            <p className="text-sm text-content-tertiary">No models found</p>
            <p className="text-xs text-content-muted mt-1">
              Drop a file in the upload zone above to get started.
            </p>
          </div>
        )
      )}
      </PageStateRenderer>

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

// ---------------------------------------------------------------------------
// Model Card (with Deploy to Worker button)
// ---------------------------------------------------------------------------

function ModelCard({
  model,
  onDelete,
  onHardDelete,
  onRestore,
  onDeploy,
  onFreeGpu,
}: {
  model: Model;
  onDelete: () => void;
  onHardDelete: () => void;
  onRestore: () => void;
  onDeploy: () => void;
  onFreeGpu: () => void;
}) {
  const typeColors: Record<string, string> = {
    checkpoint: "bg-purple-600/20 text-purple-400",
    lora: "bg-blue-600/20 text-blue-400",
    vae: "bg-green-600/20 text-green-400",
    controlnet: "bg-orange-600/20 text-orange-400",
    ipadapter: "bg-pink-600/20 text-pink-400",
    upscaler: "bg-cyan-600/20 text-cyan-400",
    embedding: "bg-yellow-600/20 text-yellow-400",
  };

  const badgeClass = typeColors[model.type || ""] || "bg-gray-600/20 text-gray-400";
  const comfyuiPath = model.comfyui_path || (model.metadata?.comfyui_path as string) || "";
  const sizeMb = (model.metadata as Record<string, unknown>)?.size_mb as number | undefined;
  const isArchived = model.status === "archived";
  const isB2Only = model.status === "available_b2_only";

  return (
    <div className={`rounded-xl border p-5 group ${isArchived ? "border-white/[0.03] bg-[#0d0d1a] opacity-50" : "border-border-subtle bg-surface-raised"}`}>
      {/* Archived banner */}
      {isArchived && (
        <div className="flex items-center justify-between mb-2 -mt-1">
          <span className="text-[10px] font-medium text-amber-400/70 bg-amber-500/10 px-2 py-0.5 rounded">Archived</span>
          <button onClick={onRestore} className="text-[10px] text-purple-400 hover:text-purple-300 font-medium">
            Restore
          </button>
        </div>
      )}

      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${isArchived ? "bg-gray-700/20" : "bg-purple-600/20"}`}>
            <Cpu className={`h-5 w-5 ${isArchived ? "text-gray-600" : "text-purple-400"}`} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-content-primary truncate">{model.name}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${badgeClass}`}>
                {model.type || "unknown"}
              </span>
              {model.family && <span className="text-[10px] text-content-muted">{model.family}</span>}
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-0.5 shrink-0">
          {!isArchived && comfyuiPath && (
            <>
              {isB2Only ? (
                <button
                  onClick={onDeploy}
                  className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-gray-500 hover:text-green-400 hover:bg-green-400/10 transition-all"
                  title="Deploy to GPU worker from B2"
                >
                  <Server className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  onClick={onFreeGpu}
                  className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-gray-500 hover:text-amber-400 hover:bg-amber-400/10 transition-all"
                  title="Free GPU space (keep in B2)"
                >
                  <HardDrive className="h-3.5 w-3.5" />
                </button>
              )}
            </>
          )}
          <button
            onClick={onDelete}
            className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-gray-500 hover:text-amber-400 hover:bg-amber-400/10 transition-all"
            title="Archive (keep in B2)"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={onHardDelete}
            className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-gray-500 hover:text-red-600 hover:bg-red-600/10 transition-all"
            title="Permanently delete (removes from B2)"
          >
            <XCircle className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Deploy to Worker button — prominent for B2-only models */}
      {isB2Only && !isArchived && (
        <button
          onClick={onDeploy}
          className="w-full flex items-center justify-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-2 text-xs font-medium text-green-400 hover:bg-green-500/20 mb-3 transition-colors"
        >
          <Server className="h-3.5 w-3.5" /> Deploy to Worker
        </button>
      )}

      {/* Storage / Cache Status */}
      <div className="flex items-center gap-2 rounded-lg border border-border-subtle bg-white/[0.02] px-3 py-2 mb-3">
        <HardDrive className="h-4 w-4 text-content-tertiary" />
        <span className="text-xs text-content-tertiary">B2:</span>
        {model.storage_path || model.b2_cached ? (
          <span className="flex items-center gap-1 text-xs text-status-success">
            <CheckCircle className="h-3 w-3" /> Cached
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-content-muted">
            <XCircle className="h-3 w-3" /> Not cached
          </span>
        )}
        {sizeMb && (
          <span className="ml-auto text-xs text-content-muted">
            {Number(sizeMb) > 1024
              ? `${(Number(sizeMb) / 1024).toFixed(1)} GB`
              : `${Number(sizeMb).toFixed(0)} MB`}
          </span>
        )}
      </div>

      {/* ComfyUI Path */}
      {comfyuiPath && (
        <div className="flex items-center gap-2 rounded-lg border border-border-subtle bg-white/[0.02] px-3 py-2 mb-3">
          <FolderOpen className="h-4 w-4 text-content-tertiary" />
          <span className="text-[10px] text-content-muted truncate font-mono">{comfyuiPath}</span>
        </div>
      )}

      {/* Base Model + Trigger Words (for LoRAs) */}
      {model.type === "lora" && (
        <div className="space-y-1.5 mb-3">
          {Boolean((model.metadata as Record<string, unknown>)?.base_model) && (
            <div className="flex items-center gap-2 text-[11px]">
              <span className="text-content-muted">Base:</span>
              <span className="text-content-secondary font-medium">{String((model.metadata as Record<string, unknown>).base_model)}</span>
            </div>
          )}
          {Boolean((model.metadata as Record<string, unknown>)?.trigger_words) && (
            <div className="flex items-center gap-2 text-[11px]">
              <span className="text-content-muted">Trigger:</span>
              <span className="text-purple-300 font-mono">{Array.isArray((model.metadata as Record<string, unknown>).trigger_words) ? ((model.metadata as Record<string, unknown>).trigger_words as string[]).join(", ") : String((model.metadata as Record<string, unknown>).trigger_words)}</span>
            </div>
          )}
        </div>
      )}

      {/* VRAM */}
      {model.required_vram_gb && (
        <p className="text-[11px] text-content-muted">VRAM: ~{model.required_vram_gb} GB</p>
      )}
    </div>
  );
}
