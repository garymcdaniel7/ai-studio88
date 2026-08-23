"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState } from "react";
import {
  Upload,
  Star,
  Maximize2,
  Trash2,
  Sparkles,
} from "lucide-react";
import {
  GovernedConfirmationDialog,
  useGovernedAction,
} from "@/components/governed-action";
import type { ActionResult } from "@/components/governed-action";

// ---------------------------------------------------------------------------
// Talent Media Section — Photo upload + gallery
// ---------------------------------------------------------------------------

export function TalentMediaSection({ talentId, avatarUrl, onAvatarChange }: { talentId: string; avatarUrl?: string; onAvatarChange?: (url: string) => void }) {
  const [media, setMedia] = useState<Record<string, unknown>[]>([]);
  const [uploading, setUploading] = useState(false);
  const [currentAvatar, setCurrentAvatar] = useState(avatarUrl || "");
  const [expandedImage, setExpandedImage] = useState<string | null>(null);
  const { dialogState: mediaDialogState, requestConfirmation, executeAction: mediaExecuteAction, cancel: mediaCancel, retry: mediaRetry } = useGovernedAction();

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/talent/${talentId}/media`)
      .then((r) => r.json())
      .then((data) => setMedia(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [talentId]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);

    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append("file", file);
      try {
        const resp = await fetch(`${API_BASE}/api/v1/talent/${talentId}/media`, {
          method: "POST",
          body: formData,
        });
        if (resp.ok) {
          const asset = await resp.json();
          setMedia((prev) => [asset, ...prev]);
        }
      } catch {
        // silent
      }
    }
    setUploading(false);
    e.target.value = "";
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-400 uppercase">Photos & Training Images</p>
        <label className="flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700 cursor-pointer">
          <Upload className="h-3 w-3" />
          {uploading ? "Uploading..." : "Upload Photos"}
          <input
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={handleUpload}
          />
        </label>
      </div>
      <p className="text-[10px] text-gray-600">
        Upload 10-50 consistent photos for best LoRA training results. These images define this talent&apos;s visual identity.
      </p>

      {media.length > 0 ? (
        <div className="grid grid-cols-3 gap-2">
          {media.map((item) => (
            <div key={item.id as string} className="aspect-square rounded-lg overflow-hidden border border-white/[0.06] bg-white/[0.02] relative group cursor-pointer">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${API_BASE}${item.public_url as string}`}
                alt={(item.original_filename as string) || "Talent photo"}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                <button
                  title="Set as Default"
                  onClick={async (e) => {
                    e.stopPropagation();
                    const url = item.public_url as string;
                    setCurrentAvatar(url); // Optimistic fill
                    if (onAvatarChange) onAvatarChange(url);
                    try {
                      await fetch(`${API_BASE}/api/v1/talent/${talentId}`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ avatar_url: url }),
                      });
                    } catch {}
                  }}
                  className={`p-1.5 rounded-full text-white hover:bg-purple-700 ${currentAvatar === (item.public_url as string) ? "bg-amber-500" : "bg-purple-600"}`}
                >
                  <Star className={`h-3.5 w-3.5 ${currentAvatar === (item.public_url as string) ? "fill-current" : ""}`} />
                </button>
                <button
                  title="Expand"
                  onClick={(e) => {
                    e.stopPropagation();
                    setExpandedImage(`${API_BASE}${item.public_url as string}`);
                  }}
                  className="p-1.5 rounded-full bg-white/20 text-white hover:bg-white/30"
                >
                  <Maximize2 className="h-3.5 w-3.5" />
                </button>
                <button
                  title="Delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    requestConfirmation(
                      {
                        actionKey: `delete-photo-${item.id}`,
                        riskTier: "standard",
                        verb: "Delete",
                        resourceName: (item.filename as string) || "this photo",
                        resourceType: "Training Photo",
                        consequence: "This photo will be permanently removed from the talent's training set.",
                      },
                      async (): Promise<ActionResult> => {
                        try {
                          await fetch(`${API_BASE}/api/v1/assets/${item.id}`, { method: "DELETE" });
                          setMedia((prev) => prev.filter((m) => m.id !== item.id));
                          return { success: true };
                        } catch (err: unknown) {
                          return { success: false, error: (err as Error)?.message || "Failed to delete photo." };
                        }
                      }
                    );
                  }}
                  className="p-1.5 rounded-full bg-red-600/80 text-white hover:bg-red-600"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-white/[0.1] p-6 text-center">
          <Upload className="h-8 w-8 text-gray-600 mx-auto mb-2" />
          <p className="text-xs text-gray-500">Drop photos here or click Upload</p>
          <p className="text-[10px] text-gray-600 mt-1">PNG, JPG — used for training & reference</p>
        </div>
      )}

      {expandedImage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={() => setExpandedImage(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={expandedImage} alt="Expanded" className="max-w-[90vw] max-h-[90vh] rounded-lg object-contain" />
          <button onClick={() => setExpandedImage(null)} className="absolute top-4 right-4 p-2 rounded-full bg-white/10 text-white hover:bg-white/20">✕</button>
        </div>
      )}

      {media.length >= 5 && (
        <button
          onClick={() => {
            // Navigate to training with this talent pre-selected
            window.location.href = `/training?talent_id=${talentId}`;
          }}
          className="w-full flex items-center justify-center gap-2 rounded-lg border border-purple-500/30 bg-purple-500/10 py-2 text-xs font-medium text-purple-300 hover:bg-purple-500/20"
        >
          <Sparkles className="h-3.5 w-3.5" /> Train LoRA from these {media.length} images
        </button>
      )}

      <GovernedConfirmationDialog
        dialogState={mediaDialogState}
        onConfirm={mediaExecuteAction}
        onCancel={mediaCancel}
        onRetry={mediaRetry}
      />
    </div>
  );
}
