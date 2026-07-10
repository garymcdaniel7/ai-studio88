"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useEffect, useState } from "react";
import {
  Search,
  Plus,
  Upload,
  Filter,
  Star,
  MoreHorizontal,
  Loader2,
  Sparkles,
  Trash2,
} from "lucide-react";
import { getTalent, deleteTalent, updateTalent } from "@/lib/api";
import { useToast } from "@/components/toast";

const tabs = ["All Talent", "Models", "Characters", "Voices", "Influencers", "Wardrobe"];

export default function TalentPage() {
  const [selectedTab, setSelectedTab] = useState("All Talent");
  const [selectedTalent, setSelectedTalent] = useState<Record<string, unknown> | null>(null);
  const [talentData, setTalentData] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const { show } = useToast();

  useEffect(() => {
    async function load() {
      try {
        const data = await getTalent();
        setTalentData(Array.isArray(data) ? data : []);
        if (data.length > 0) setSelectedTalent(data[0]);
      } catch {
        setTalentData([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [newName, setNewName] = useState("");
  const [newBio, setNewBio] = useState("");
  const [detailTab, setDetailTab] = useState("Overview");

  async function createNewTalent() {
    if (!newName.trim()) return;
    try {
      const resp = await fetch(`${API_BASE}/talent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName, bio: newBio }),
      });
      if (resp.ok) {
        const data = await getTalent();
        setTalentData(Array.isArray(data) ? data : []);
        setShowCreate(false);
        setNewName("");
        setNewBio("");
      }
    } catch {}
  }

  const filtered = selectedTab === "All Talent" 
    ? talentData 
    : talentData.filter((t) => {
        const type = ((t.default_style as string) || (t.type as string) || "model").toLowerCase();
        const tabLower = selectedTab.toLowerCase();
        if (tabLower === "models") return type === "model" || type === "fashion" || !t.default_style;
        if (tabLower === "characters") return type === "character" || type === "story";
        if (tabLower === "voices") return type === "voice" || type === "narrator";
        if (tabLower === "influencers") return type === "influencer" || type === "social";
        if (tabLower === "wardrobe") return type === "wardrobe" || type === "fashion_set";
        return true;
      });

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
          <h1 className="text-2xl font-bold text-white">Talent</h1>
          <p className="text-sm text-gray-500">
            Manage your AI personas, models, voices, and characters.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              const input = document.createElement("input");
              input.type = "file";
              input.accept = ".json,.csv";
              input.onchange = (e: Event) => {
                const file = (e.target as HTMLInputElement).files?.[0];
                if (!file) return;
                show("Import file: " + file.name + ". JSON/CSV import coming soon.", "info");
              };
              input.click();
            }}
            className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]"
          >
            <Upload className="h-4 w-4" /> Import
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
          >
            <Plus className="h-4 w-4" /> New Talent
          </button>
        </div>
      </div>

      {/* Create Talent Modal */}
      {showCreate && (
        <div className="rounded-xl border border-purple-500/30 bg-[#12122a] p-6">
          <h3 className="text-sm font-semibold text-white mb-4">Create New Talent</h3>
          <div className="space-y-3">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Name (e.g. Melissa)"
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50"
            />
            <textarea
              value={newBio}
              onChange={(e) => setNewBio(e.target.value)}
              placeholder="Bio / description..."
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-200 placeholder:text-gray-600 outline-none resize-none"
              rows={3}
            />
            <div className="flex gap-2">
              <button
                onClick={createNewTalent}
                className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
              >
                Create
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className="rounded-lg border border-white/[0.08] px-4 py-2 text-sm text-gray-400 hover:bg-white/[0.04]"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-white/[0.06] pb-px">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setSelectedTab(tab)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              selectedTab === tab
                ? "border-b-2 border-purple-500 text-purple-400"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-6 gap-3">
        {[
          { label: "Total Talent", value: String(talentData.length), sub: "AI personas", color: "text-blue-400" },
          { label: "Models", value: String(talentData.filter((t) => t.default_style === "model" || !t.default_style).length), sub: "Fashion & commercial", color: "text-purple-400" },
          { label: "Characters", value: "0", sub: "Story characters", color: "text-amber-400" },
          { label: "Voices", value: "0", sub: "Voice profiles", color: "text-green-400" },
          { label: "Influencers", value: "0", sub: "AI influencers", color: "text-pink-400" },
          { label: "Wardrobe Sets", value: "0", sub: "Outfits & styles", color: "text-teal-400" },
        ].map((m) => (
          <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-3 text-center">
            <p className="text-xs text-gray-500">{m.label}</p>
            <p className="text-xl font-bold text-white">{m.value}</p>
            <p className={`text-xs ${m.color}`}>{m.sub}</p>
          </div>
        ))}
      </div>

      {/* Main Content: Grid + Detail Panel */}
      <div className="grid grid-cols-[1fr_380px] gap-6">
        {/* Talent Grid */}
        <div>
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-gray-400">
              Talent Library · {filtered.length} results
            </p>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1">
                <Search className="h-3.5 w-3.5 text-gray-500" />
                <input className="w-32 bg-transparent text-xs text-gray-300 placeholder:text-gray-600 outline-none" placeholder="Search..." />
              </div>
              <button className="flex items-center gap-1 rounded-lg border border-white/[0.08] px-2 py-1 text-xs text-gray-400">
                <Filter className="h-3 w-3" /> Filters
              </button>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4">
            {filtered.map((talent) => (
              <button
                key={talent.id as string}
                onClick={() => setSelectedTalent(talent)}
                className={`group relative overflow-hidden rounded-xl border transition-all ${
                  selectedTalent?.id === talent.id
                    ? "border-purple-500/50 ring-1 ring-purple-500/30"
                    : "border-white/[0.06] hover:border-white/[0.12]"
                } bg-[#12122a]`}
              >
                {/* Avatar placeholder */}
                <div className="aspect-[3/4] w-full bg-gradient-to-br from-purple-900/30 to-blue-900/30" />
                <div className="p-3">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-white">{talent.name as string}</p>
                    <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-purple-600/20 text-purple-400">
                      {(talent.default_style as string) || "Model"}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">{(talent.bio as string)?.slice(0, 40) || "AI Talent"}</p>
                  <div className="mt-1 flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                    <span className="text-[10px] text-gray-500">Active</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Detail Panel */}
        {selectedTalent && (
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            {/* Profile header */}
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-white">{selectedTalent.name as string}</h3>
                  <Star className="h-4 w-4 text-gray-600 cursor-pointer hover:text-amber-400" />
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <span className="rounded bg-purple-600/20 px-2 py-0.5 text-xs font-medium text-purple-400">
                    {(selectedTalent.default_style as string) || "Model"}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-green-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> Active
                  </span>
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => setShowEdit(true)} className="rounded-lg border border-white/[0.08] px-3 py-1.5 text-xs text-gray-300 hover:bg-white/[0.04]">Edit</button>
                <button
                  onClick={async () => {
                    if (!confirm(`Delete talent "${selectedTalent?.name}"? This cannot be undone.`)) return;
                    try {
                      await deleteTalent(selectedTalent?.id as string);
                      setTalentData((prev) => prev.filter((t) => t.id !== selectedTalent?.id));
                      setSelectedTalent(null);
                    } catch {}
                  }}
                  className="rounded-lg border border-red-500/20 px-3 py-1.5 text-xs text-red-400 hover:bg-red-400/10"
                >
                  Delete
                </button>
                <button className="rounded-lg border border-white/[0.08] p-1.5 text-gray-400 hover:bg-white/[0.04]">
                  <MoreHorizontal className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Avatar / Main Reference Image */}
            <div className="my-4 aspect-[4/5] w-full rounded-xl bg-gradient-to-br from-purple-900/40 to-blue-900/40 relative overflow-hidden group">
              {(selectedTalent.avatar_url as string) ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={selectedTalent.avatar_url as string}
                    alt={(selectedTalent.name as string) || "Talent"}
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
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
                            const resp = await fetch(`${API_BASE}/api/v1/talent/${selectedTalent.id}/media`, {
                              method: "POST",
                              body: formData,
                            });
                            if (resp.ok) {
                              const asset = await resp.json();
                              // Update talent avatar_url
                              await updateTalent(selectedTalent.id as string, { avatar_url: asset.public_url });
                              setSelectedTalent({ ...selectedTalent, avatar_url: asset.public_url });
                            }
                          } catch {}
                        }}
                      />
                    </label>
                  </div>
                </>
              ) : (
                <label className="w-full h-full flex flex-col items-center justify-center cursor-pointer hover:bg-purple-900/20 transition-colors">
                  <Upload className="h-8 w-8 text-gray-600 mb-2" />
                  <p className="text-xs text-gray-500">Upload reference photo</p>
                  <p className="text-[10px] text-gray-600 mt-0.5">This is the main identity image</p>
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
                        const resp = await fetch(`${API_BASE}/api/v1/talent/${selectedTalent.id}/media`, {
                          method: "POST",
                          body: formData,
                        });
                        if (resp.ok) {
                          const asset = await resp.json();
                          await updateTalent(selectedTalent.id as string, { avatar_url: asset.public_url });
                          setSelectedTalent({ ...selectedTalent, avatar_url: asset.public_url });
                        }
                      } catch {}
                    }}
                  />
                </label>
              )}
            </div>

            <p className="text-sm text-gray-400">
              {(selectedTalent.bio as string) || "Fashion and commercial model with a versatile look suitable for luxury, lifestyle, and editorial campaigns."}
            </p>

            {/* Tabs - dynamic based on talent type */}
            <div className="mt-4 flex gap-1 border-b border-white/[0.06]">
              {getTabsForType((selectedTalent.default_style as string) || "model").map((t) => (
                <button
                  key={t}
                  onClick={() => setDetailTab(t)}
                  className={`px-3 py-2 text-xs transition-colors ${
                    detailTab === t
                      ? "text-purple-400 border-b border-purple-500"
                      : "text-gray-500 hover:text-gray-300"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            {detailTab === "Overview" && (
              <div className="mt-4 space-y-3">
                <h4 className="text-xs font-semibold text-gray-400 uppercase">Profile</h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-gray-500">Full Name</span><p className="text-gray-200">{(selectedTalent.name as string) || "—"}</p></div>
                  <div><span className="text-gray-500">Age</span><p className="text-gray-200">{(selectedTalent.age as string) || "—"}</p></div>
                  <div><span className="text-gray-500">Height</span><p className="text-gray-200">{(selectedTalent.height as string) || "—"}</p></div>
                  <div><span className="text-gray-500">Ethnicity</span><p className="text-gray-200">{(selectedTalent.ethnicity as string) || "—"}</p></div>
                </div>

                {/* Creative DNA */}
                <div className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold text-white">Creative DNA</h4>
                    <button onClick={() => setShowEdit(true)} className="text-[10px] text-purple-400">Edit</button>
                  </div>
                  <div className="mt-2 space-y-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-purple-500" />
                      <span className="text-gray-400">Visual Style:</span>
                      <span className="text-gray-200">{(selectedTalent.visual_style as string) || "Not set"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-pink-500" />
                      <span className="text-gray-400">Best For:</span>
                      <span className="text-gray-200">{(selectedTalent.best_for as string) || "Not set"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-blue-500" />
                      <span className="text-gray-400">Persona:</span>
                      <span className="text-gray-200">{(selectedTalent.persona as string) || "Not set"}</span>
                    </div>
                  </div>
                </div>

                {/* Quick Training Photos */}
                <div className="mt-4">
                  <TalentMediaSection talentId={selectedTalent.id as string} />
                </div>
              </div>
            )}

            {detailTab === "Details" && (
              <div className="mt-4 space-y-3">
                <h4 className="text-xs font-semibold text-gray-400 uppercase">All Fields</h4>
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between border-b border-white/[0.04] pb-2"><span className="text-gray-500">Name</span><span className="text-gray-200">{(selectedTalent.name as string) || "—"}</span></div>
                  <div className="flex justify-between border-b border-white/[0.04] pb-2"><span className="text-gray-500">Bio</span><span className="text-gray-200 text-right max-w-[200px] truncate">{(selectedTalent.bio as string) || "—"}</span></div>
                  <div className="flex justify-between border-b border-white/[0.04] pb-2"><span className="text-gray-500">Age</span><span className="text-gray-200">{(selectedTalent.age as string) || "—"}</span></div>
                  <div className="flex justify-between border-b border-white/[0.04] pb-2"><span className="text-gray-500">Height</span><span className="text-gray-200">{(selectedTalent.height as string) || "—"}</span></div>
                  <div className="flex justify-between border-b border-white/[0.04] pb-2"><span className="text-gray-500">Ethnicity</span><span className="text-gray-200">{(selectedTalent.ethnicity as string) || "—"}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">Default Style</span><span className="text-gray-200">{(selectedTalent.default_style as string) || "—"}</span></div>
                </div>
              </div>
            )}

            {detailTab === "Media" && (
              <div className="mt-4 space-y-3">
                <TalentMediaSection talentId={selectedTalent.id as string} />
              </div>
            )}

            {detailTab === "Wardrobe" && (
              <div className="mt-4 space-y-3">
                <TalentLoraSection talentId={selectedTalent.id as string} />
              </div>
            )}

            {detailTab === "LoRAs" && (
              <div className="mt-4 space-y-3">
                <TalentLoraSection talentId={selectedTalent.id as string} />
              </div>
            )}

            {detailTab === "Projects" && (
              <div className="mt-4 text-center py-6">
                <p className="text-sm text-gray-400">No projects associated.</p>
              </div>
            )}

            {detailTab === "Stats" && (
              <div className="mt-4 text-center py-6">
                <p className="text-sm text-gray-400">Generation stats will appear once this talent is used in productions.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Edit Modal */}
      {showEdit && selectedTalent && (
        <TalentEditModal
          talent={selectedTalent}
          onClose={() => setShowEdit(false)}
          onSave={async (updated) => {
            try {
              await updateTalent(selectedTalent.id as string, updated);
              const data = await getTalent();
              setTalentData(Array.isArray(data) ? data : []);
              const refreshed = (Array.isArray(data) ? data : []).find((t) => t.id === selectedTalent.id);
              if (refreshed) setSelectedTalent(refreshed);
              setShowEdit(false);
              show("Talent updated successfully", "success");
            } catch (err) {
              show("Failed to update talent", "error");
            }
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper: Dynamic tabs based on talent type
// ---------------------------------------------------------------------------

function getTabsForType(type: string): string[] {
  switch (type.toLowerCase()) {
    case "model":
    case "influencer":
      return ["Overview", "Details", "Media", "LoRAs", "Projects", "Stats"];
    case "character":
      return ["Overview", "Details", "Media", "LoRAs", "Story", "Stats"];
    case "voice":
      return ["Overview", "Details", "Samples", "Projects", "Stats"];
    case "wardrobe":
      return ["Overview", "Details", "Media", "Combinations", "Stats"];
    case "background":
      return ["Overview", "Details", "Media", "Variants", "Stats"];
    default:
      return ["Overview", "Details", "Media", "LoRAs", "Projects", "Stats"];
  }
}

// ---------------------------------------------------------------------------
// Talent Media Section — Photo upload + gallery
// ---------------------------------------------------------------------------

function TalentMediaSection({ talentId }: { talentId: string }) {
  const [media, setMedia] = useState<Record<string, unknown>[]>([]);
  const [uploading, setUploading] = useState(false);

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
            <div key={item.id as string} className="aspect-square rounded-lg overflow-hidden border border-white/[0.06] bg-white/[0.02]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${API_BASE}${item.public_url as string}`}
                alt={(item.original_filename as string) || "Talent photo"}
                className="w-full h-full object-cover"
              />
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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Talent LoRA Section — Assign and manage LoRAs
// ---------------------------------------------------------------------------

function TalentLoraSection({ talentId }: { talentId: string }) {
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

function TalentEditModal({
  talent,
  onClose,
  onSave,
}: {
  talent: Record<string, unknown>;
  onClose: () => void;
  onSave: (data: Record<string, unknown>) => Promise<void>;
}) {
  const [form, setForm] = useState({
    name: (talent.name as string) || "",
    bio: (talent.bio as string) || "",
    age: (talent.age as string) || "",
    height: (talent.height as string) || "",
    ethnicity: (talent.ethnicity as string) || "",
    default_style: (talent.default_style as string) || "model",
    gender: (talent.gender as string) || "",
    hair_color: (talent.hair_color as string) || "",
    eye_color: (talent.eye_color as string) || "",
    body_type: (talent.body_type as string) || "",
    visual_style: (talent.visual_style as string) || "",
    best_for: (talent.best_for as string) || "",
    persona: (talent.persona as string) || "",
    trigger_words: (talent.trigger_words as string) || "",
    negative_prompt: (talent.negative_prompt as string) || "",
  });
  const [saving, setSaving] = useState(false);

  function update(key: string, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    const creative_dna = {
      visual_style: form.visual_style,
      best_for: form.best_for,
      persona: form.persona,
    };
    await onSave({
      name: form.name,
      bio: form.bio,
      age: form.age || null,
      height: form.height || null,
      ethnicity: form.ethnicity || null,
      default_style: form.default_style,
      gender: form.gender || null,
      hair_color: form.hair_color || null,
      eye_color: form.eye_color || null,
      body_type: form.body_type || null,
      visual_style: form.visual_style || null,
      best_for: form.best_for || null,
      persona: form.persona || null,
      trigger_words: form.trigger_words || null,
      negative_prompt: form.negative_prompt || null,
      creative_dna,
    });
    setSaving(false);
  }

  const inputClass = "w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-purple-500 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-white">Edit Talent</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">
            <span className="text-lg">&times;</span>
          </button>
        </div>

        <div className="space-y-4">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Name</label>
              <input value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="Full name" className={inputClass} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Type / Style</label>
              <select value={form.default_style} onChange={(e) => update("default_style", e.target.value)} className={inputClass}>
                <option value="model">Model</option>
                <option value="character">Character</option>
                <option value="voice">Voice</option>
                <option value="influencer">Influencer</option>
                <option value="wardrobe">Wardrobe</option>
                <option value="background">Background</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Bio / Description</label>
            <textarea value={form.bio} onChange={(e) => update("bio", e.target.value)} placeholder="Describe this talent..." className={inputClass + " resize-none"} rows={3} />
          </div>

          {/* Physical Attributes */}
          <div className="rounded-lg border border-white/[0.06] p-4">
            <p className="text-xs font-semibold text-gray-300 mb-3">Physical Attributes</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Age</label>
                <input value={form.age} onChange={(e) => update("age", e.target.value)} placeholder="28" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Height</label>
                <input value={form.height} onChange={(e) => update("height", e.target.value)} placeholder="5&apos;9&quot;" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Ethnicity</label>
                <input value={form.ethnicity} onChange={(e) => update("ethnicity", e.target.value)} placeholder="e.g. Mediterranean" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Gender</label>
                <input value={form.gender} onChange={(e) => update("gender", e.target.value)} placeholder="Female" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Hair Color</label>
                <input value={form.hair_color} onChange={(e) => update("hair_color", e.target.value)} placeholder="Dark brown" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Eye Color</label>
                <input value={form.eye_color} onChange={(e) => update("eye_color", e.target.value)} placeholder="Hazel" className={inputClass} />
              </div>
            </div>
          </div>

          {/* Creative DNA */}
          <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-4">
            <p className="text-xs font-semibold text-purple-300 mb-3">Creative DNA</p>
            <div className="space-y-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Visual Style (comma-separated)</label>
                <input value={form.visual_style} onChange={(e) => update("visual_style", e.target.value)} placeholder="Elegant, Confident, Sophisticated" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Best For (comma-separated)</label>
                <input value={form.best_for} onChange={(e) => update("best_for", e.target.value)} placeholder="Luxury, Fashion, Beauty" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Persona (comma-separated)</label>
                <input value={form.persona} onChange={(e) => update("persona", e.target.value)} placeholder="Confident, Modern, Empowered" className={inputClass} />
              </div>
            </div>
          </div>

          {/* Generation Settings */}
          <div className="rounded-lg border border-white/[0.06] p-4">
            <p className="text-xs font-semibold text-gray-300 mb-3">Generation Settings</p>
            <div className="space-y-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Trigger Words (for LoRA prompts)</label>
                <input value={form.trigger_words} onChange={(e) => update("trigger_words", e.target.value)} placeholder="ohwx, melissa_style" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Negative Prompt (always exclude)</label>
                <input value={form.negative_prompt} onChange={(e) => update("negative_prompt", e.target.value)} placeholder="blurry, low quality, deformed" className={inputClass} />
              </div>
            </div>
          </div>

          {/* Save */}
          <button
            onClick={handleSave}
            disabled={saving || !form.name.trim()}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
