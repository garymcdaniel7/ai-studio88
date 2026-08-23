"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Talent Relationships Section — Associate talents with each other
// ---------------------------------------------------------------------------

export function TalentRelationshipsSection({ talentId, allTalent }: { talentId: string; allTalent: Record<string, unknown>[] }) {
  const [relationships, setRelationships] = useState<Record<string, unknown>[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [selectedTalentId, setSelectedTalentId] = useState("");
  const [relType, setRelType] = useState("associated");
  const [notes, setNotes] = useState("");

  const otherTalent = allTalent.filter((t) => t.id !== talentId);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/talent/${talentId}/relationships`)
      .then((r) => r.json())
      .then((data) => setRelationships(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [talentId]);

  async function handleAdd() {
    if (!selectedTalentId) return;
    try {
      const resp = await fetch(`${API_BASE}/api/v1/talent/${talentId}/relationships`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ related_talent_id: selectedTalentId, relationship_type: relType, notes }),
      });
      if (resp.ok) {
        const data = await fetch(`${API_BASE}/api/v1/talent/${talentId}/relationships`).then((r) => r.json());
        setRelationships(Array.isArray(data) ? data : []);
        setShowAdd(false);
        setSelectedTalentId("");
        setNotes("");
      }
    } catch {}
  }

  async function handleRemove(relId: string) {
    try {
      await fetch(`${API_BASE}/api/v1/talent/relationships/${relId}`, { method: "DELETE" });
      setRelationships((prev) => prev.filter((r) => r.id !== relId));
    } catch {}
  }

  const RELATIONSHIP_TYPES = [
    { value: "associated", label: "Associated" },
    { value: "friends", label: "Friends" },
    { value: "couple", label: "Couple / Partner" },
    { value: "wears", label: "Wears (wardrobe)" },
    { value: "uses", label: "Uses (product)" },
    { value: "lives_in", label: "Lives in (background)" },
    { value: "holds", label: "Holds (prop)" },
    { value: "appears_with", label: "Appears with" },
    { value: "pairs_with", label: "Pairs with" },
    { value: "variant_of", label: "Variant of" },
  ];

  // Already-linked IDs
  const linkedIds = new Set(relationships.map((r) => {
    const rt = r.related_talent as Record<string, unknown> | undefined;
    return rt?.id as string || "";
  }));

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-400 uppercase">Relationships</p>
        <button onClick={() => setShowAdd(true)} className="flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700">
          <Plus className="h-3 w-3" /> Link Talent
        </button>
      </div>
      <p className="text-[10px] text-gray-600">
        Link this talent to others for multi-person scenes, wardrobe, backgrounds, and products.
      </p>

      {showAdd && (
        <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-3 space-y-2">
          <select value={selectedTalentId} onChange={(e) => setSelectedTalentId(e.target.value)} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white outline-none">
            <option value="">Select talent...</option>
            {otherTalent.filter((t) => !linkedIds.has(t.id as string)).map((t) => (
              <option key={t.id as string} value={t.id as string}>{t.name as string} ({(t.default_style as string) || "model"})</option>
            ))}
          </select>
          <select value={relType} onChange={(e) => setRelType(e.target.value)} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white outline-none">
            {RELATIONSHIP_TYPES.map((rt) => <option key={rt.value} value={rt.value}>{rt.label}</option>)}
          </select>
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional)" className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white placeholder:text-gray-600 outline-none" />
          <div className="flex gap-2">
            <button onClick={handleAdd} disabled={!selectedTalentId} className="rounded-lg bg-purple-600 px-4 py-1.5 text-xs text-white hover:bg-purple-700 disabled:opacity-50">Link</button>
            <button onClick={() => setShowAdd(false)} className="rounded-lg border border-white/[0.08] px-4 py-1.5 text-xs text-gray-400">Cancel</button>
          </div>
        </div>
      )}

      {relationships.length > 0 ? (
        <div className="space-y-2">
          {relationships.map((rel) => {
            const related = rel.related_talent as Record<string, unknown> | undefined;
            return (
              <div key={rel.id as string} className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-gradient-to-br from-purple-500/30 to-blue-500/30 overflow-hidden">
                    {Boolean(related?.avatar_url) && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={`${API_BASE}${related?.avatar_url as string}`} alt="" className="w-full h-full object-cover" />
                    )}
                  </div>
                  <div>
                    <p className="text-xs font-medium text-white">{(related?.name as string) || "Unknown"}</p>
                    <p className="text-[10px] text-gray-500">{(related?.default_style as string) || "Model"} &middot; <span className="text-purple-400">{(rel.relationship_type as string) || "associated"}</span></p>
                  </div>
                </div>
                <button onClick={() => handleRemove(rel.id as string)} className="p-1 text-gray-600 hover:text-red-400" title="Remove">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-white/[0.1] p-4 text-center">
          <p className="text-xs text-gray-500">No relationships yet</p>
          <p className="text-[10px] text-gray-600 mt-1">Link wardrobe, backgrounds, products, or other models to this talent.</p>
        </div>
      )}
    </div>
  );
}
