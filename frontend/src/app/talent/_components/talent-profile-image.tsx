"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState } from "react";
import { Upload } from "lucide-react";
import { updateTalent } from "@/lib/api";

// ---------------------------------------------------------------------------
// Talent Profile Image — Shows default photo or upload prompt
// ---------------------------------------------------------------------------

export function TalentProfileImage({ talent, onUpdate }: { talent: Record<string, unknown>; onUpdate: (t: Record<string, unknown>) => void }) {
  const [media, setMedia] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    if (!talent?.id) return;
    fetch(`${API_BASE}/api/v1/talent/${talent.id}/media`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setMedia(data);
        // Auto-set first image as avatar if none set
        if (!talent.avatar_url && data.length > 0) {
          const firstUrl = data[0].public_url;
          updateTalent(talent.id as string, { avatar_url: firstUrl });
          onUpdate({ ...talent, avatar_url: firstUrl });
        }
      })
      .catch(() => {});
  }, [talent?.id]);

  const avatarUrl = talent.avatar_url as string;
  const hasAvatar = Boolean(avatarUrl);

  return (
    <div className="my-4 aspect-[4/5] w-full rounded-xl bg-gradient-to-br from-purple-900/40 to-blue-900/40 relative overflow-hidden group">
      {hasAvatar ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={avatarUrl.startsWith("/") ? `${API_BASE}${avatarUrl}` : avatarUrl}
            alt={(talent.name as string) || "Talent"}
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2">
            <label className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-xs font-medium text-white cursor-pointer hover:bg-purple-700">
              <Upload className="h-3.5 w-3.5" /> Change Photo
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const formData = new FormData();
                  formData.append("file", file);
                  try {
                    const resp = await fetch(`${API_BASE}/api/v1/talent/${talent.id}/media`, { method: "POST", body: formData });
                    if (resp.ok) {
                      const asset = await resp.json();
                      const url = asset.public_url;
                      await updateTalent(talent.id as string, { avatar_url: url });
                      onUpdate({ ...talent, avatar_url: url });
                    }
                  } catch {}
                }}
              />
            </label>
            {media.length > 1 && (
              <p className="text-[10px] text-gray-400">Or select from {media.length} uploaded photos below</p>
            )}
          </div>
        </>
      ) : (
        <label className="w-full h-full flex flex-col items-center justify-center cursor-pointer hover:bg-purple-900/20 transition-colors">
          <Upload className="h-8 w-8 text-gray-600 mb-2" />
          <p className="text-xs text-gray-500">Upload reference photo</p>
          <p className="text-[10px] text-gray-600 mt-0.5">This becomes the default identity image</p>
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const formData = new FormData();
              formData.append("file", file);
              try {
                const resp = await fetch(`${API_BASE}/api/v1/talent/${talent.id}/media`, { method: "POST", body: formData });
                if (resp.ok) {
                  const asset = await resp.json();
                  const url = asset.public_url;
                  await updateTalent(talent.id as string, { avatar_url: url });
                  onUpdate({ ...talent, avatar_url: url });
                }
              } catch {}
            }}
          />
        </label>
      )}
    </div>
  );
}
