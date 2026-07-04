"use client";

import { useEffect, useState } from "react";
import { Cpu, Download, HardDrive, Loader2, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { getAvailableModels } from "@/lib/api";

interface Model {
  id: string;
  name: string;
  provider?: string;
  type?: string;
  size?: string;
  b2_cached?: boolean;
  b2_path?: string;
  status?: string;
}

export default function ModelsPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAvailableModels()
      .then((data) => {
        setModels(Array.isArray(data) ? data : []);
      })
      .catch((err) => {
        setError(err.message || "Failed to load models");
      })
      .finally(() => setLoading(false));
  }, []);

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
      <div>
        <h1 className="text-2xl font-bold text-white">Model Manager</h1>
        <p className="text-sm text-gray-500">
          View available AI models, B2 cache status, and download commands.
        </p>
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

      {/* Models Grid */}
      {models.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {models.map((model) => (
            <div
              key={model.id || model.name}
              className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-600/20">
                    <Cpu className="h-5 w-5 text-purple-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-white">{model.name}</p>
                    <p className="text-xs text-gray-500">{model.provider || model.type || "Unknown provider"}</p>
                  </div>
                </div>
              </div>

              {/* B2 Cache Status */}
              <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 mb-3">
                <HardDrive className="h-4 w-4 text-gray-400" />
                <span className="text-xs text-gray-400">B2 Cache:</span>
                {model.b2_cached ? (
                  <span className="flex items-center gap-1 text-xs text-green-400">
                    <CheckCircle className="h-3 w-3" /> Cached
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-gray-500">
                    <XCircle className="h-3 w-3" /> Not cached
                  </span>
                )}
                {model.size && <span className="ml-auto text-xs text-gray-500">{model.size}</span>}
              </div>

              {/* Download button / info */}
              {!model.b2_cached && (
                <div className="rounded-lg border border-dashed border-white/[0.08] bg-white/[0.01] p-3">
                  <p className="text-xs text-gray-400 mb-2">Download to B2 cache:</p>
                  <code className="block text-[11px] text-purple-300 bg-black/30 rounded px-2 py-1.5 overflow-x-auto">
                    b2 upload-file studio-models ./models/{model.id || model.name} models/{model.id || model.name}
                  </code>
                </div>
              )}
              {model.b2_cached && model.b2_path && (
                <p className="text-[11px] text-gray-500 truncate">
                  Path: {model.b2_path}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        !error && (
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
            <Cpu className="h-12 w-12 text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-400">No models available</p>
            <p className="text-xs text-gray-600 mt-1">
              Connect your backend to see registered models.
            </p>
          </div>
        )
      )}

      {/* Info */}
      <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
        <h3 className="text-sm font-semibold text-white mb-2">About Model Caching</h3>
        <p className="text-xs text-gray-400 leading-relaxed">
          Models cached in B2 are pre-downloaded to your cloud storage for fast loading onto GPU workers.
          Use the CLI commands above to push local model files to your B2 bucket. Cached models load 3-5x
          faster when launching new worker instances.
        </p>
      </div>
    </div>
  );
}
