"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState } from "react";
import { Loader2, Image as ImageIcon } from "lucide-react";
import { authFetch } from "@/lib/api";

// ---------------------------------------------------------------------------
// Talent Generations Section — Shows images generated for/with this talent
// ---------------------------------------------------------------------------

export function TalentGenerationsSection({ talentId, talentName }: { talentId: string; talentName: string }) {
  const [generations, setGenerations] = useState<{id: string; filename: string; public_url?: string; metadata?: Record<string, unknown>; created_at?: string}[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch assets associated with this talent
    authFetch(`${API_BASE}/api/v1/assets`)
      .then((r) => r.json())
      .then((data) => {
        const items = Array.isArray(data) ? data : data.assets || [];
        // Filter to assets linked to this talent
        const talentAssets = items.filter((a: Record<string, unknown>) =>
          a.talent_id === talentId ||
          ((a.metadata as Record<string, unknown>)?.talent_ids as string[])?.includes(talentId)
        );
        setGenerations(talentAssets);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [talentId]);

  if (loading) {
    return <div className="py-8 text-center"><Loader2 className="h-5 w-5 animate-spin text-purple-500 mx-auto" /></div>;
  }

  if (generations.length === 0) {
    return (
      <div className="py-8 text-center">
        <ImageIcon className="h-8 w-8 text-gray-600 mx-auto mb-2" />
        <p className="text-sm text-gray-400">No generations for {talentName} yet</p>
        <p className="text-xs text-gray-600 mt-1">Select this talent on the Create page and generate to see results here.</p>
        <a
          href={`/create?talent=${talentId}`}
          className="mt-3 inline-block rounded-lg bg-purple-600/10 px-3 py-1.5 text-xs text-purple-400 hover:bg-purple-600/20"
        >
          Generate with {talentName}
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500">{generations.length} generation{generations.length !== 1 ? "s" : ""}</p>
        <a href={`/create?talent=${talentId}`} className="text-xs text-purple-400 hover:text-purple-300">
          Generate more
        </a>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {generations.map((gen) => (
          <div key={gen.id} className="aspect-square rounded-lg overflow-hidden border border-white/[0.06] bg-white/[0.02] group relative">
            {gen.public_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={gen.public_url.startsWith("http") ? gen.public_url : `${API_BASE}/api/v1/assets/${gen.id}/file`}
                alt={gen.filename}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <ImageIcon className="h-6 w-6 text-gray-600" />
              </div>
            )}
            {gen.metadata?.prompt ? (
              <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <p className="text-[9px] text-gray-300 truncate">{String(gen.metadata.prompt)}</p>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
