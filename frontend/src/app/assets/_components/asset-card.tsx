"use client";

import { Music, Package, File, Maximize2, Wand2, Trash2 } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Asset {
  id: string;
  filename: string;
  original_filename?: string;
  url: string;
  type: string;
  created_at: string;
  tags?: string[];
  public_url?: string;
  metadata?: {
    prompt?: string;
    model?: string;
    seed?: number;
    source?: string;
    width?: number;
    height?: number;
  };
}

type AssetCategory = "image" | "video" | "model" | "audio" | "other";

function getAssetCategory(asset: Asset): AssetCategory {
  const t = (asset.type || "").toLowerCase();
  const f = (asset.filename || "").toLowerCase();

  if (t.startsWith("image")) return "image";
  if (t.startsWith("video")) return "video";
  if (t.startsWith("audio")) return "audio";

  if (
    f.endsWith(".safetensors") ||
    f.endsWith(".pth") ||
    f.endsWith(".pt") ||
    f.endsWith(".bin")
  )
    return "model";
  if (
    f.endsWith(".mp3") ||
    f.endsWith(".wav") ||
    f.endsWith(".ogg") ||
    f.endsWith(".flac") ||
    f.endsWith(".m4a") ||
    f.endsWith(".aac")
  )
    return "audio";
  if (
    f.endsWith(".mp4") ||
    f.endsWith(".webm") ||
    f.endsWith(".mov") ||
    f.endsWith(".avi")
  )
    return "video";

  return "other";
}

const categoryPreview = (
  asset: Asset,
  src: string
): React.ReactNode => {
  const category = getAssetCategory(asset);

  if (category === "image") {
    return (
      <img
        src={src}
        alt={asset.filename || "Asset preview"}
        className="w-full h-full object-cover"
      />
    );
  }

  if (category === "video") {
    return (
      <video
        src={src}
        className="w-full h-full object-cover"
        controls
        preload="metadata"
        poster={src}
      >
        Your browser does not support the video tag.
      </video>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center h-full text-content-muted p-3">
      {ICON_MAP[category]}
      <span className="text-[10px] truncate max-w-full mt-2 text-center">
        {asset.filename}
      </span>
    </div>
  );
};

const ICON_MAP: Record<"model" | "audio" | "other", React.ReactNode> = {
  model: <Package className="h-10 w-10" />,
  audio: <Music className="h-10 w-10" />,
  other: <File className="h-10 w-10" />,
};

interface AssetCardProps {
  asset: Asset;
  onExpand: (url: string) => void;
  onRegenerate: (asset: Asset) => void;
  onDelete: (assetId: string) => void;
}

export function AssetCard({ asset, onExpand, onRegenerate, onDelete }: AssetCardProps) {
  const src = asset.id
    ? `${API_BASE}/api/v1/assets/${asset.id}/file`
    : asset.public_url || asset.url;
  const category = getAssetCategory(asset);
  const isMediaPreview = category === "image" || category === "video";
  const previewElement = categoryPreview(asset, src);

  return (
    <div className="group rounded-xl border border-border-subtle bg-surface-raised overflow-hidden hover:border-purple-500/30 transition-all">
      <div className="aspect-square bg-white/[0.02] flex items-center justify-center overflow-hidden relative">
        {previewElement}

        {isMediaPreview && (
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
            <button
              type="button"
              title="Expand"
              onClick={() => onExpand(src)}
              className="p-1.5 rounded-full bg-white/20 text-white hover:bg-white/30"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
            {asset.metadata?.prompt && (
              <button
                type="button"
                title="Re-generate with this prompt"
                onClick={() => onRegenerate(asset)}
                className="p-1.5 rounded-full bg-purple-600/80 text-white hover:bg-purple-600"
              >
                <Wand2 className="h-4 w-4" />
              </button>
            )}
            <button
              type="button"
              title="Delete"
              onClick={() => onDelete(asset.id)}
              className="p-1.5 rounded-full bg-red-600/80 text-white hover:bg-red-600"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
      <div className="p-2">
        <p className="text-xs text-content-secondary truncate">
          {asset.filename}
        </p>
        {asset.metadata?.prompt && (
          <p className="text-[10px] text-content-muted truncate mt-0.5">
            {asset.metadata.prompt}
          </p>
        )}
      </div>
    </div>
  );
}
