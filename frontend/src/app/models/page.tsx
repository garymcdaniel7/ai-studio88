"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useEffect, useState, useCallback, useRef } from "react";
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
} from "lucide-react";
import {
  getRegisteredModels,
  getAvailableModels,
  uploadModel,
  deleteModel,
  hardDeleteModel,
  ModelUploadResponse,
} from "@/lib/api";

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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ModelsPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [filter, setFilter] = useState<string>("all");

  // Load models on mount
  const loadModels = useCallback(async () => {
    try {
      const registered = await getRegisteredModels();
      if (Array.isArray(registered) && registered.length > 0) {
        // Deduplicate by name (some models appear twice in DB)
        const seen = new Set<string>();
        const deduped = registered.filter((m) => {
          const name = (m as Record<string, unknown>).name as string;
          if (seen.has(name)) return false;
          seen.add(name);
          return true;
        });
        setModels(deduped as unknown as Model[]);
      } else {
        const available = await getAvailableModels();
        setModels(Array.isArray(available) ? available as unknown as Model[] : []);
      }
      setError(null);
    } catch (err) {
      setError((err as Error).message || "Failed to load models");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const registered = await getRegisteredModels();
        if (cancelled) return;
        if (Array.isArray(registered) && registered.length > 0) {
          const deduped = Array.from(
            new Map(registered.map((m) => [((m as Record<string, unknown>).id as string) || ((m as Record<string, unknown>).name as string), m])).values()
          );
          setModels(deduped as unknown as Model[]);
        } else {
          const available = await getAvailableModels();
          if (cancelled) return;
          setModels(Array.isArray(available) ? available as unknown as Model[] : []);
        }
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError((err as Error).message || "Failed to load models");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const filteredModels =
    filter === "all" ? models : models.filter((m) => m.type === filter);

  async function handleDelete(model: Model) {
    if (!confirm(`Archive model "${model.name}"? It will be greyed out but stays in B2 for re-download.`)) return;
    try {
      await deleteModel(model.id);
      // Mark as archived locally (don't remove from view)
      setModels((prev) => prev.map((m) => m.id === model.id ? { ...m, status: "archived" } : m));
    } catch {
      // silent
    }
  }

  async function handleRestore(model: Model) {
    try {
      await fetch(`${API_BASE}/api/v1/models/${model.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "available" }),
      });
      setModels((prev) => prev.map((m) => m.id === model.id ? { ...m, status: "available" } : m));
    } catch {
      // silent
    }
  }

  async function handleHardDelete(model: Model) {
    if (!confirm(`PERMANENTLY delete "${model.name}"?\n\nThis removes the model from B2 storage AND the registry. This cannot be undone.`)) return;
    if (!confirm(`Are you absolutely sure? "${model.name}" will be gone forever.`)) return;
    try {
      await hardDeleteModel(model.id);
      setModels((prev) => prev.filter((m) => m.id !== model.id));
    } catch {
      // silent
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Model Manager</h1>
          <p className="text-sm text-gray-500">
            Upload, manage, and deploy AI models to GPU workers.
          </p>
        </div>
        <button
          onClick={() => setShowUpload(true)}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700"
        >
          <Upload className="h-4 w-4" /> Upload Model
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-5 py-3">
          <AlertCircle className="h-5 w-5 text-amber-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-300">Could not load models</p>
            <p className="text-xs text-amber-400/60 mt-0.5">{error}</p>
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
                ? "bg-purple-600 text-white"
                : "bg-white/[0.04] text-gray-400 hover:text-white hover:bg-white/[0.08]"
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
            />
          ))}
        </div>
      ) : (
        !error && (
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
            <Cpu className="h-12 w-12 text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-400">No models found</p>
            <p className="text-xs text-gray-600 mt-1">
              Upload a model to get started.
            </p>
            <button
              onClick={() => setShowUpload(true)}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
            >
              <Upload className="h-4 w-4" /> Upload Your First Model
            </button>
          </div>
        )
      )}

      {/* Upload Modal */}
      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onSuccess={() => {
            setShowUpload(false);
            setLoading(true);
            loadModels();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Model Card
// ---------------------------------------------------------------------------

function ModelCard({ model, onDelete, onHardDelete, onRestore }: { model: Model; onDelete: () => void; onHardDelete: () => void; onRestore?: () => void }) {
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
  const sizeMb = (model.metadata as Record<string, unknown>)?.size_mb as number | undefined;

  const isArchived = model.status === "archived";

  return (
    <div className={`rounded-xl border p-5 group ${isArchived ? "border-white/[0.03] bg-[#0d0d1a] opacity-50" : "border-white/[0.06] bg-[#12122a]"}`}>
      {isArchived && (
        <div className="flex items-center justify-between mb-2 -mt-1">
          <span className="text-[10px] font-medium text-amber-400/70 bg-amber-500/10 px-2 py-0.5 rounded">Archived</span>
          {onRestore && (
            <button
              onClick={onRestore}
              className="text-[10px] text-purple-400 hover:text-purple-300 font-medium"
            >
              Restore
            </button>
          )}
        </div>
      )}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${isArchived ? "bg-gray-700/20" : "bg-purple-600/20"}`}>
            <Cpu className={`h-5 w-5 ${isArchived ? "text-gray-600" : "text-purple-400"}`} />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">{model.name}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${badgeClass}`}>
                {model.type || "unknown"}
              </span>
              {model.family && (
                <span className="text-[10px] text-gray-500">{model.family}</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-0.5">
          {/* GPU Management */}
          {(model.status === "available" || !model.status) && model.comfyui_path && (
            <button
              onClick={async () => {
                try {
                  await fetch(`${API_BASE}/api/v1/models/${model.id}/free-gpu`, { method: "POST" });
                } catch {}
              }}
              className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-gray-500 hover:text-amber-400 hover:bg-amber-400/10 transition-all"
              title="Free GPU space (keep in B2)"
            >
              <HardDrive className="h-3.5 w-3.5" />
            </button>
          )}
          {model.status === "available_b2_only" && model.comfyui_path && (
            <button
              onClick={async () => {
                try {
                  await fetch(`${API_BASE}/api/v1/models/${model.id}/upload-to-gpu`, { method: "POST" });
                } catch {}
              }}
              className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-gray-500 hover:text-green-400 hover:bg-green-400/10 transition-all"
              title="Re-upload to GPU from B2"
            >
              <Upload className="h-3.5 w-3.5" />
            </button>
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

      {/* Storage / Cache Status */}
      <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 mb-3">
        <HardDrive className="h-4 w-4 text-gray-400" />
        <span className="text-xs text-gray-400">B2:</span>
        {model.storage_path || model.b2_cached ? (
          <span className="flex items-center gap-1 text-xs text-green-400">
            <CheckCircle className="h-3 w-3" /> Cached
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-gray-500">
            <XCircle className="h-3 w-3" /> Not cached
          </span>
        )}
        {sizeMb && (
          <span className="ml-auto text-xs text-gray-500">
            {Number(sizeMb) > 1024
              ? `${(Number(sizeMb) / 1024).toFixed(1)} GB`
              : `${Number(sizeMb).toFixed(0)} MB`}
          </span>
        )}
      </div>

      {/* ComfyUI Path */}
      {model.comfyui_path && (
        <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 mb-3">
          <FolderOpen className="h-4 w-4 text-gray-400" />
          <span className="text-[10px] text-gray-500 truncate font-mono">{model.comfyui_path}</span>
        </div>
      )}

      {/* VRAM requirement */}
      {model.required_vram_gb && (
        <p className="text-[11px] text-gray-500">
          VRAM: ~{model.required_vram_gb} GB
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Upload Modal
// ---------------------------------------------------------------------------

function UploadModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
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
  const [result, setResult] = useState<ModelUploadResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) {
      setFile(dropped);
      if (!name) setName(dropped.name.replace(/\.[^.]+$/, "").replace(/[_-]/g, " "));
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      if (!name) setName(selected.name.replace(/\.[^.]+$/, "").replace(/[_-]/g, " "));
    }
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setProgress(0);

    try {
      const resp = await uploadModel(
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
      setResult(resp);
      setTimeout(onSuccess, 1500);
    } catch (err) {
      setUploadError((err as Error).message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-white">Upload Model</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {result ? (
          // Success State
          <div className="text-center py-6">
            <CheckCircle className="h-12 w-12 text-green-400 mx-auto mb-3" />
            <p className="text-sm font-medium text-white mb-1">Upload Complete</p>
            <p className="text-xs text-gray-400">
              {result.size_mb.toFixed(1)} MB uploaded to B2
            </p>
            <p className="text-xs text-gray-500 mt-2 font-mono">{result.comfyui_path}</p>
          </div>
        ) : (
          <>
            {/* Drop Zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => inputRef.current?.click()}
              className={`rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors mb-5 ${
                dragging
                  ? "border-purple-500 bg-purple-500/10"
                  : file
                    ? "border-green-500/50 bg-green-500/5"
                    : "border-white/[0.1] hover:border-purple-500/50 hover:bg-purple-500/5"
              }`}
            >
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPTED_EXTENSIONS}
                onChange={handleFileSelect}
                className="hidden"
              />
              {file ? (
                <div>
                  <CheckCircle className="h-8 w-8 text-green-400 mx-auto mb-2" />
                  <p className="text-sm font-medium text-white">{file.name}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {(file.size / (1024 * 1024)).toFixed(1)} MB
                  </p>
                </div>
              ) : (
                <div>
                  <Upload className="h-8 w-8 text-gray-500 mx-auto mb-2" />
                  <p className="text-sm text-gray-300">
                    Drop a model file here or click to browse
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    .safetensors, .ckpt, .pt, .pth, .gguf, .bin
                  </p>
                </div>
              )}
            </div>

            {/* Form Fields */}
            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Model Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. SDXL Turbo FP16"
                  className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-purple-500 focus:outline-none"
                />
              </div>

              {/* Type & Family */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">Type</label>
                  <select
                    value={modelType}
                    onChange={(e) => setModelType(e.target.value)}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
                  >
                    {MODEL_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">Family</label>
                  <select
                    value={family}
                    onChange={(e) => setFamily(e.target.value)}
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
                  >
                    {MODEL_FAMILIES.map((f) => (
                      <option key={f.value} value={f.value}>{f.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* LoRA-specific fields */}
              {modelType === "lora" && (
                <div className="space-y-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-4">
                  <p className="text-xs font-semibold text-blue-300">LoRA Settings</p>
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">
                      Trigger Words (comma-separated)
                    </label>
                    <input
                      type="text"
                      value={triggerWords}
                      onChange={(e) => setTriggerWords(e.target.value)}
                      placeholder="e.g. ohwx, style_xyz"
                      className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-purple-500 focus:outline-none"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-400 mb-1">
                        Base Model
                      </label>
                      <input
                        type="text"
                        value={baseModel}
                        onChange={(e) => setBaseModel(e.target.value)}
                        placeholder="e.g. flux1-dev"
                        className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-purple-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-400 mb-1">
                        Strength (0.0–1.0)
                      </label>
                      <input
                        type="number"
                        step="0.05"
                        min="0"
                        max="1"
                        value={strength}
                        onChange={(e) => setStrength(e.target.value)}
                        className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Upload Error */}
              {uploadError && (
                <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
                  <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />
                  <p className="text-xs text-red-300">{uploadError}</p>
                </div>
              )}

              {/* Progress Bar */}
              {uploading && (
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs text-gray-400">
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

              {/* Submit */}
              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {uploading ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Uploading...</>
                ) : (
                  <><Upload className="h-4 w-4" /> Upload & Register</>
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
