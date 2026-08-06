"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useState, useEffect, useRef } from "react";
import { Image as ImageIcon, Upload, Download, Loader2, Maximize2, Trash2, Wand2 } from "lucide-react";
import { useToast } from "@/components/toast";
import {
  GovernedConfirmationDialog,
  useGovernedAction,
} from "@/components/governed-action";
import type { ActionResult } from "@/components/governed-action";

interface Asset {
  id: string;
  filename: string;
  original_filename?: string;
  url: string;
  type: string;
  created_at: string;
  tags?: string[];
  public_url?: string;
  metadata?: { prompt?: string; model?: string; seed?: number; source?: string; width?: number; height?: number };
}

export default function AssetsPage() {
  const { show } = useToast();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState("All");
  const [expandedAsset, setExpandedAsset] = useState<string | null>(null);
  const { dialogState, requestConfirmation, executeAction, cancel, retry } = useGovernedAction();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchAssets = async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/assets`);
      if (resp.ok) {
        const data = await resp.json();
        setAssets(Array.isArray(data) ? data : data.items || data.assets || []);
      }
    } catch {
      // backend not available
    }
  };

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/v1/assets`);
        if (!active) return;
        if (resp.ok) {
          const data = await resp.json();
          setAssets(Array.isArray(data) ? data : data.items || data.assets || []);
        }
      } catch {
        // backend not available
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploading(true);

    try {
      const formData = new FormData();
      Array.from(e.target.files).forEach((file) => {
        formData.append("file", file);
      });

      const resp = await fetch(`${API_BASE}/api/v1/assets`, {
        method: "POST",
        body: formData,
      });

      if (resp.ok) {
        await fetchAssets();
      } else {
        const err = await resp.json().catch(() => ({}));
        show(err.detail || "Upload failed", "error");
      }
    } catch {
      show("Cannot reach backend. Is the API server running?", "error");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const filters = ["All", "Images", "Videos", "Objects", "Backgrounds", "Wardrobe", "Products", "Brand"];

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
          <h1 className="text-2xl font-bold text-content-primary">Assets</h1>
          <p className="text-sm text-content-muted">Manage images, videos, objects, backgrounds, and brand assets.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              // Export assets — download all visible assets
              const filtered = activeFilter === "All" ? assets : assets.filter((a) => {
                const type = (a.type || "").toLowerCase();
                if (activeFilter.toLowerCase() === "images") return type.startsWith("image");
                if (activeFilter.toLowerCase() === "videos") return type.startsWith("video");
                return true;
              });
              if (filtered.length === 0) return;
              // Download each asset file
              filtered.forEach((asset, i) => {
                setTimeout(() => {
                  const url = asset.id ? `${API_BASE}/api/v1/assets/${asset.id}/file` : (asset.public_url || asset.url);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = asset.filename || asset.original_filename || `asset_${i}.png`;
                  a.click();
                }, i * 500); // Stagger downloads to avoid browser blocking
              });
            }}
            className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-secondary hover:bg-surface-active"
          >
            <Download className="h-4 w-4" /> Export {activeFilter === "All" ? "All" : activeFilter}
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            <Upload className="h-4 w-4" /> {uploading ? "Uploading..." : "Upload Asset"}
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,video/*"
          multiple
          className="hidden"
          onChange={handleUpload}
        />
      </div>

      <div className="flex gap-3">
        {filters.map((t) => (
          <button
            key={t}
            onClick={() => setActiveFilter(t)}
            className={`rounded-lg border px-3 py-1.5 text-xs hover:text-content-primary hover:bg-surface-active ${
              activeFilter === t
                ? "bg-interactive-muted text-status-info border-status-info/30"
                : "border-border-subtle bg-surface-hover text-content-tertiary"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {(() => {
        const filteredAssets = activeFilter === "All"
          ? assets
          : assets.filter((a) => {
              const type = (a.type || "").toLowerCase();
              const tags = Array.isArray(a.tags) ? a.tags.join(",").toLowerCase() : "";
              const filter = activeFilter.toLowerCase();
              if (filter === "images") return type.startsWith("image");
              if (filter === "videos") return type.startsWith("video");
              if (filter === "backgrounds") return tags.includes("background") || type.includes("background");
              if (filter === "wardrobe") return tags.includes("wardrobe") || tags.includes("outfit");
              if (filter === "products") return tags.includes("product");
              if (filter === "objects") return tags.includes("object");
              if (filter === "brand") return tags.includes("brand");
              return true;
            });

        return filteredAssets.length === 0 ? (
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-8 text-center">
            <ImageIcon className="h-12 w-12 text-content-muted mx-auto mb-3" />
            <p className="text-sm text-content-tertiary">
              {activeFilter === "All" ? "Upload assets to get started" : `No ${activeFilter.toLowerCase()} found`}
            </p>
            <p className="text-xs text-content-muted mt-1">Every asset gets Object DNA — the AI understands what it is and how to use it.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {filteredAssets.map((asset) => (
              <div
                key={asset.id}
                className="group rounded-xl border border-border-subtle bg-surface-raised overflow-hidden hover:border-purple-500/30 transition-all"
              >
                <div className="aspect-square bg-white/[0.02] flex items-center justify-center overflow-hidden relative">
                  {asset.type?.startsWith("image") ? (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={asset.id ? `${API_BASE}/api/v1/assets/${asset.id}/file` : (asset.public_url || asset.url)}
                        alt={asset.filename || "Asset preview"}
                        className="w-full h-full object-cover"
                      />
                      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                        <button
                          title="Expand"
                          onClick={() => setExpandedAsset(`${API_BASE}/api/v1/assets/${asset.id}/file`)}
                          className="p-1.5 rounded-full bg-white/20 text-white hover:bg-white/30"
                        >
                          <Maximize2 className="h-4 w-4" />
                        </button>
                        {asset.metadata?.prompt && (
                          <button
                            title="Re-generate with this prompt"
                            onClick={() => {
                              const params = new URLSearchParams({ prompt: asset.metadata!.prompt! });
                              if (asset.metadata?.model) params.set("model", String(asset.metadata.model));
                              if (asset.metadata?.seed) params.set("seed", String(asset.metadata.seed));
                              if (asset.metadata?.width) params.set("width", String(asset.metadata.width));
                              if (asset.metadata?.height) params.set("height", String(asset.metadata.height));
                              window.location.href = `/create?${params.toString()}`;
                            }}
                            className="p-1.5 rounded-full bg-purple-600/80 text-white hover:bg-purple-600"
                          >
                            <Wand2 className="h-4 w-4" />
                          </button>
                        )}
                        <button
                          title="Delete"
                          onClick={() => {
                            requestConfirmation(
                              {
                                actionKey: `delete-asset-${asset.id}`,
                                riskTier: "standard",
                                verb: "Delete",
                                resourceName: asset.original_filename || asset.filename || "this asset",
                                resourceType: "Asset",
                                consequence: "This asset will be permanently removed from your library.",
                              },
                              async (): Promise<ActionResult> => {
                                try {
                                  await fetch(`${API_BASE}/api/v1/assets/${asset.id}`, { method: "DELETE" });
                                  setAssets((prev) => prev.filter((a) => a.id !== asset.id));
                                  return { success: true };
                                } catch (err: unknown) {
                                  return { success: false, error: (err as Error)?.message || "Failed to delete asset." };
                                }
                              }
                            );
                          }}
                          className="p-1.5 rounded-full bg-red-600/80 text-white hover:bg-red-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </>
                  ) : (
                    <ImageIcon className="h-8 w-8 text-gray-600" />
                  )}
                </div>
                <div className="p-2">
                  <p className="text-xs text-content-secondary truncate">{asset.filename}</p>
                  {asset.metadata?.prompt && (
                    <p className="text-[10px] text-content-muted truncate mt-0.5">{asset.metadata.prompt}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        );
      })()}

      {expandedAsset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={() => setExpandedAsset(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={expandedAsset} alt="Expanded" className="max-w-[90vw] max-h-[90vh] rounded-lg object-contain" />
          <button onClick={() => setExpandedAsset(null)} className="absolute top-4 right-4 p-2 rounded-full bg-white/10 text-white hover:bg-white/20">✕</button>
        </div>
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
