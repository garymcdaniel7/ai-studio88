"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Talent LoRA Section — Assign and manage LoRAs
// ---------------------------------------------------------------------------

export function TalentLoraSection({ talentId }: { talentId: string }) {
  const [loras, setLoras] = useState<{ identity_loras: Record<string, unknown>[]; style_loras: Record<string, unknown>[] }>({ identity_loras: [], style_loras: [] });
  const [models, setModels] = useState<Record<string, unknown>[]>([]);
  const [showAssign, setShowAssign] = useState(false);
  const [assignModelId, setAssignModelId] = useState("");
  const [assignName, setAssignName] = useState("");
  const [assignStrength, setAssignStrength] = useState("0.7");
  const [assignAlwaysOn, setAssignAlwaysOn] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/talent/${talentId}/loras`)
      .then((r) => r.json())
      .then((data) => setLoras(data))
      .catch(() => {});

    // Fetch available LoRA models for assignment
    fetch(`${API_BASE}/api/v1/models?type=lora`)
      .then((r) => r.json())
      .then((data) => setModels(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [talentId]);

  async function handleAssign() {
    if (!assignModelId) return;
    try {
      const resp = await fetch(`${API_BASE}/api/v1/talent/${talentId}/loras`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_id: assignModelId,
          name: assignName || models.find((m) => m.id === assignModelId)?.name || "LoRA",
          type: "style",
          strength: parseFloat(assignStrength),
          always_on: assignAlwaysOn,
        }),
      });
      if (resp.ok) {
        // Refresh
        const data = await fetch(`${API_BASE}/api/v1/talent/${talentId}/loras`).then((r) => r.json());
        setLoras(data);
        setShowAssign(false);
        setAssignModelId("");
        setAssignName("");
        setAssignAlwaysOn(false);
      }
    } catch {}
  }

  async function handleRemove(loraId: string) {
    try {
      await fetch(`${API_BASE}/api/v1/talent/${talentId}/loras/${loraId}`, { method: "DELETE" });
      setLoras((prev) => ({
        ...prev,
        style_loras: prev.style_loras.filter((l) => l.id !== loraId),
      }));
    } catch {}
  }

  const allLoras = [...loras.identity_loras, ...loras.style_loras];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-400 uppercase">LoRA Models</p>
        <button
          onClick={() => setShowAssign(true)}
          className="flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700"
        >
          <Plus className="h-3 w-3" /> Assign LoRA
        </button>
      </div>
      <p className="text-[10px] text-gray-600">
        Identity LoRAs preserve this talent&apos;s look. Style LoRAs (like &quot;golden hour&quot;) are applied to all generations.
      </p>

      {showAssign && (
        <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-3 space-y-2">
          <select
            value={assignModelId}
            onChange={(e) => setAssignModelId(e.target.value)}
            className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white outline-none"
          >
            <option value="">Select a LoRA model...</option>
            {models.map((m) => (
              <option key={m.id as string} value={m.id as string}>{m.name as string}</option>
            ))}
          </select>
          <input
            value={assignName}
            onChange={(e) => setAssignName(e.target.value)}
            placeholder="Display name (optional)"
            className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white placeholder:text-gray-600 outline-none"
          />
          <div className="flex items-center gap-3">
            <input
              type="number"
              step="0.05"
              min="0"
              max="1"
              value={assignStrength}
              onChange={(e) => setAssignStrength(e.target.value)}
              className="w-20 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-white outline-none"
            />
            <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={assignAlwaysOn}
                onChange={(e) => setAssignAlwaysOn(e.target.checked)}
                className="rounded border-gray-600"
              />
              Always-on (auto-apply to all generations)
            </label>
          </div>
          <div className="flex gap-2">
            <button onClick={handleAssign} className="rounded-lg bg-purple-600 px-4 py-1.5 text-xs text-white hover:bg-purple-700">Assign</button>
            <button onClick={() => setShowAssign(false)} className="rounded-lg border border-white/[0.08] px-4 py-1.5 text-xs text-gray-400">Cancel</button>
          </div>
        </div>
      )}

      {allLoras.length > 0 ? (
        <div className="space-y-2">
          {allLoras.map((lora) => (
            <div key={(lora.id as string)} className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-xs font-medium text-white">{(lora.name as string) || "Unnamed LoRA"}</p>
                  {Boolean(lora.always_on) && (
                    <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-medium text-amber-300">ALWAYS ON</span>
                  )}
                  <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[9px] text-blue-300">
                    {(lora.lora_type as string) || "style"}
                  </span>
                </div>
                <p className="text-[10px] text-gray-500 mt-0.5">Strength: {String(lora.strength || 0.7)}</p>
              </div>
              <button
                onClick={() => handleRemove(lora.id as string)}
                className="p-1 text-gray-600 hover:text-red-400"
                title="Remove"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-white/[0.1] p-4 text-center">
          <p className="text-xs text-gray-500">No LoRAs assigned</p>
          <p className="text-[10px] text-gray-600 mt-1">Train an identity LoRA from photos or assign style LoRAs</p>
        </div>
      )}
    </div>
  );
}
