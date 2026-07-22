"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  Users,
  Maximize2,
  Image as ImageIcon,
} from "lucide-react";
import { getTalent, createTalent, deleteTalent, updateTalent } from "@/lib/api";
import { useToast } from "@/components/toast";

const tabs = ["All Talent", "Models", "Characters", "Voices", "Influencers", "Wardrobe", "Products", "Backgrounds"];

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
        const items = Array.isArray(data) ? data : [];
        // Sort favorites to top
        const favs = JSON.parse(localStorage.getItem("talent_favorites") || "[]") as string[];
        items.sort((a, b) => {
          const aFav = favs.includes(a.id as string) ? 0 : 1;
          const bFav = favs.includes(b.id as string) ? 0 : 1;
          return aFav - bFav;
        });
        setTalentData(items);
        if (items.length > 0) setSelectedTalent(items[0]);
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
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [newName, setNewName] = useState("");
  const [newBio, setNewBio] = useState("");
  const [detailTab, setDetailTab] = useState("Overview");

  async function createNewTalent() {
    if (!newName.trim()) return;
    try {
      await createTalent({ name: newName, bio: newBio });
      const data = await getTalent();
      setTalentData(Array.isArray(data) ? data : []);
      setShowCreate(false);
      setNewName("");
      setNewBio("");
      show("Talent created!", "success");
    } catch {
      show("Failed to create talent", "error");
    }
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
        if (tabLower === "products") return type === "product";
        if (tabLower === "backgrounds") return type === "background";
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
          { label: "Models", value: String(talentData.filter((t) => !t.default_style || t.default_style === "model" || t.default_style === "fashion").length), sub: "Fashion & commercial", color: "text-purple-400" },
          { label: "Characters", value: String(talentData.filter((t) => t.default_style === "character" || t.default_style === "story").length), sub: "Story characters", color: "text-amber-400" },
          { label: "Voices", value: String(talentData.filter((t) => t.default_style === "voice" || t.default_style === "narrator").length), sub: "Voice profiles", color: "text-green-400" },
          { label: "Influencers", value: String(talentData.filter((t) => t.default_style === "influencer" || t.default_style === "social").length), sub: "AI influencers", color: "text-pink-400" },
          { label: "Wardrobe Sets", value: String(talentData.filter((t) => t.default_style === "wardrobe" || t.default_style === "fashion_set").length), sub: "Outfits & styles", color: "text-teal-400" },
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
              <button aria-label="Filter talent" className="flex items-center gap-1 rounded-lg border border-white/[0.08] px-2 py-1 text-xs text-gray-400">
                <Filter className="h-3 w-3" /> Filters
              </button>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4">
            {filtered.length === 0 && !loading && (
              <div className="col-span-4 rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
                <Users className="h-10 w-10 text-gray-600 mx-auto mb-3" />
                <p className="text-sm text-gray-400">
                  {selectedTab === "All Talent" ? "No talent yet" : `No ${selectedTab.toLowerCase()} found`}
                </p>
                <p className="text-xs text-gray-600 mt-1">Create your first AI persona to start generating content.</p>
                <button
                  onClick={() => setShowCreate(true)}
                  className="mt-3 inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
                >
                  <Plus className="h-4 w-4" /> Create Talent
                </button>
              </div>
            )}
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
                {/* Avatar / Default Photo */}
                <div className="aspect-[3/4] w-full bg-gradient-to-br from-purple-900/30 to-blue-900/30 overflow-hidden">
                  {(talent.avatar_url as string) ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={(talent.avatar_url as string).startsWith("/") ? `${API_BASE}${talent.avatar_url}` : (talent.avatar_url as string)}
                      alt={(talent.name as string) || ""}
                      className="w-full h-full object-cover"
                    />
                  ) : null}
                </div>
                <div className="p-3">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-white">{talent.name as string}</p>
                    <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-purple-600/20 text-purple-400">
                      {(talent.default_style as string) || "Model"}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">{(talent.bio as string)?.slice(0, 40) || "AI Talent"}</p>
                  <div className="mt-1 flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                      <span className="text-[10px] text-gray-500">Active</span>
                    </div>
                    <a
                      href={`/training?talent_id=${talent.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="text-[10px] text-purple-400 hover:text-purple-300 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      Train LoRA →
                    </a>
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
                  <button
                    onClick={() => {
                      const id = selectedTalent.id as string;
                      const favs = JSON.parse(localStorage.getItem("talent_favorites") || "[]") as string[];
                      const updated = favs.includes(id) ? favs.filter((f) => f !== id) : [id, ...favs];
                      localStorage.setItem("talent_favorites", JSON.stringify(updated));
                      // Force re-render by updating talent data order
                      setTalentData((prev) => {
                        const sorted = [...prev].sort((a, b) => {
                          const aFav = updated.includes(a.id as string) ? 0 : 1;
                          const bFav = updated.includes(b.id as string) ? 0 : 1;
                          return aFav - bFav;
                        });
                        return sorted;
                      });
                    }}
                    className="p-0.5"
                    title={JSON.parse(localStorage.getItem("talent_favorites") || "[]").includes(selectedTalent.id as string) ? "Remove from favorites" : "Add to favorites"}
                  >
                    <Star className={`h-4 w-4 cursor-pointer transition-colors ${JSON.parse(localStorage.getItem("talent_favorites") || "[]").includes(selectedTalent.id as string) ? "text-amber-400 fill-amber-400" : "text-gray-600 hover:text-amber-400"}`} />
                  </button>
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
                <div className="relative">
                  <button
                    aria-label="More options"
                    onClick={() => setShowMoreMenu(!showMoreMenu)}
                    className="rounded-lg border border-white/[0.08] p-1.5 text-gray-400 hover:bg-white/[0.04]"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                  {showMoreMenu && (
                    <div className="absolute right-0 top-full z-20 mt-1 w-44 rounded-xl border border-white/[0.1] bg-[#12122a] p-1.5 shadow-2xl">
                      <button
                        onClick={() => { setShowEdit(true); setShowMoreMenu(false); }}
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-300 hover:bg-white/[0.05]"
                      >
                        Edit Profile
                      </button>
                      <button
                        onClick={() => {
                          // Duplicate talent
                          const copy = { ...selectedTalent, name: `${selectedTalent?.name} (copy)` } as Record<string, unknown>;
                          delete copy.id;
                          createTalent(copy).then(() => getTalent().then((d) => setTalentData(Array.isArray(d) ? d : [])));
                          setShowMoreMenu(false);
                        }}
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-300 hover:bg-white/[0.05]"
                      >
                        Duplicate
                      </button>
                      <button
                        onClick={() => {
                          // Copy Creative DNA to clipboard
                          const dna = { visual_style: selectedTalent?.visual_style, best_for: selectedTalent?.best_for, persona: selectedTalent?.persona, trigger_words: selectedTalent?.trigger_words };
                          navigator.clipboard.writeText(JSON.stringify(dna, null, 2));
                          show("Creative DNA copied to clipboard", "success");
                          setShowMoreMenu(false);
                        }}
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-300 hover:bg-white/[0.05]"
                      >
                        Copy DNA
                      </button>
                      <button
                        onClick={() => {
                          window.location.href = `/training?talent_id=${selectedTalent?.id}`;
                          setShowMoreMenu(false);
                        }}
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-300 hover:bg-white/[0.05]"
                      >
                        Train LoRA
                      </button>
                      <button
                        onClick={() => {
                          // Export as JSON
                          const blob = new Blob([JSON.stringify(selectedTalent, null, 2)], { type: "application/json" });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement("a");
                          a.href = url; a.download = `${(selectedTalent?.name as string || "talent").toLowerCase().replace(/\s+/g, "_")}.json`;
                          a.click(); URL.revokeObjectURL(url);
                          setShowMoreMenu(false);
                        }}
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-300 hover:bg-white/[0.05]"
                      >
                        Export JSON
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Avatar / Main Reference Image */}
            <TalentProfileImage talent={selectedTalent} onUpdate={(updated) => setSelectedTalent(updated)} />

            <p className="text-sm text-gray-400">
              {(selectedTalent.bio as string) || "Fashion and commercial model with a versatile look suitable for luxury, lifestyle, and editorial campaigns."}
            </p>

            {/* Tabs - dynamic based on talent type */}
            <div className="mt-4 flex gap-1 border-b border-white/[0.06] overflow-x-auto scrollbar-hide">
              {getTabsForType((selectedTalent.default_style as string) || "model").map((t) => (
                <button
                  key={t}
                  onClick={() => setDetailTab(t)}
                  className={`px-3 py-2 text-xs transition-colors whitespace-nowrap shrink-0 ${
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
                  <TalentMediaSection talentId={selectedTalent.id as string} avatarUrl={selectedTalent.avatar_url as string} onAvatarChange={(url) => setSelectedTalent((prev) => prev ? { ...prev, avatar_url: url } : prev)} />
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

            {detailTab === "Wardrobe" && (
              <div className="mt-4 space-y-3">
                <TalentMediaSection talentId={selectedTalent.id as string} />
              </div>
            )}

            {detailTab === "LoRAs" && (
              <div className="mt-4 space-y-3">
                <TalentLoraSection talentId={selectedTalent.id as string} />
              </div>
            )}

            {(detailTab === "Voices" || detailTab === "Samples") && (
              <div className="mt-4 space-y-3">
                <TalentVoiceSection talentId={selectedTalent.id as string} talentName={selectedTalent.name as string} />
              </div>
            )}

            {detailTab === "Projects" && (
              <div className="mt-4 text-center py-6">
                <p className="text-sm text-gray-400">No projects associated.</p>
              </div>
            )}

            {detailTab === "Relationships" && (
              <div className="mt-4 space-y-3">
                <TalentRelationshipsSection talentId={selectedTalent.id as string} allTalent={talentData} />
              </div>
            )}

            {detailTab === "Generations" && (
              <div className="mt-4">
                <TalentGenerationsSection talentId={selectedTalent.id as string} talentName={selectedTalent.name as string} />
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
      return ["Overview", "Details", "Generations", "Voices", "LoRAs", "Relationships", "Stats"];
    case "character":
      return ["Overview", "Details", "Generations", "Voices", "LoRAs", "Story", "Stats"];
    case "voice":
      return ["Overview", "Details", "Voices", "Projects", "Stats"];
    case "wardrobe":
      return ["Overview", "Details", "Media", "Combinations", "Stats"];
    case "background":
      return ["Overview", "Details", "Media", "Variants", "Stats"];
    default:
      return ["Overview", "Details", "Generations", "Voices", "Media", "LoRAs", "Projects", "Stats"];
  }
}

// ---------------------------------------------------------------------------
// Talent Media Section — Photo upload + gallery
// ---------------------------------------------------------------------------

function TalentMediaSection({ talentId, avatarUrl, onAvatarChange }: { talentId: string; avatarUrl?: string; onAvatarChange?: (url: string) => void }) {
  const [media, setMedia] = useState<Record<string, unknown>[]>([]);
  const [uploading, setUploading] = useState(false);
  const [currentAvatar, setCurrentAvatar] = useState(avatarUrl || "");
  const [expandedImage, setExpandedImage] = useState<string | null>(null);

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
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (!confirm("Delete this photo?")) return;
                    try {
                      await fetch(`${API_BASE}/api/v1/assets/${item.id}`, { method: "DELETE" });
                      setMedia((prev) => prev.filter((m) => m.id !== item.id));
                    } catch {}
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
    // Wardrobe fields
    garment_type: (talent.garment_type as string) || "",
    fabric: (talent.fabric as string) || "",
    color: (talent.color as string) || "",
    brand: (talent.brand as string) || "",
    size_range: (talent.size_range as string) || "",
    season: (talent.season as string) || "",
    category: (talent.category as string) || "",
    // Product fields
    product_name: (talent.product_name as string) || "",
    dimensions: (talent.dimensions as string) || "",
    sku: (talent.sku as string) || "",
    // Background/Set fields
    location_type: (talent.location_type as string) || "",
    lighting: (talent.lighting as string) || "",
    time_of_day: (talent.time_of_day as string) || "",
    mood: (talent.mood as string) || "",
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
    const payload: Record<string, unknown> = {
      name: form.name,
      bio: form.bio,
      default_style: form.default_style,
      visual_style: form.visual_style || null,
      best_for: form.best_for || null,
      persona: form.persona || null,
      trigger_words: form.trigger_words || null,
      negative_prompt: form.negative_prompt || null,
      creative_dna,
    };
    const type = form.default_style;
    if (type === "model" || type === "influencer" || type === "character" || type === "voice") {
      payload.age = form.age || null;
      payload.height = form.height || null;
      payload.ethnicity = form.ethnicity || null;
      payload.gender = form.gender || null;
      payload.hair_color = form.hair_color || null;
      payload.eye_color = form.eye_color || null;
      payload.body_type = form.body_type || null;
    } else if (type === "wardrobe") {
      payload.garment_type = form.garment_type || null;
      payload.fabric = form.fabric || null;
      payload.color = form.color || null;
      payload.brand = form.brand || null;
      payload.size_range = form.size_range || null;
      payload.season = form.season || null;
      payload.category = form.category || null;
    } else if (type === "product") {
      payload.product_name = form.product_name || null;
      payload.brand = form.brand || null;
      payload.category = form.category || null;
      payload.dimensions = form.dimensions || null;
      payload.sku = form.sku || null;
      payload.color = form.color || null;
    } else if (type === "background") {
      payload.location_type = form.location_type || null;
      payload.lighting = form.lighting || null;
      payload.time_of_day = form.time_of_day || null;
      payload.mood = form.mood || null;
    }
    await onSave(payload);
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
                <option value="model">Model / Person</option>
                <option value="character">Character</option>
                <option value="voice">Voice</option>
                <option value="influencer">Influencer</option>
                <option value="wardrobe">Wardrobe / Clothing</option>
                <option value="product">Product</option>
                <option value="background">Background / Set</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Bio / Description</label>
            <textarea value={form.bio} onChange={(e) => update("bio", e.target.value)} placeholder="Describe this talent..." className={inputClass + " resize-none"} rows={3} />
          </div>

          {/* Physical Attributes — only for person types */}
          {(form.default_style === "model" || form.default_style === "influencer" || form.default_style === "character" || form.default_style === "voice") && (
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
          )}

          {/* Wardrobe Details */}
          {form.default_style === "wardrobe" && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
            <p className="text-xs font-semibold text-amber-300 mb-3">Wardrobe Details</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Garment Type</label>
                <select value={form.garment_type} onChange={(e) => update("garment_type", e.target.value)} className={inputClass}>
                  <option value="">Select...</option>
                  <option value="dress">Dress</option>
                  <option value="top">Top / Blouse</option>
                  <option value="bottom">Bottom / Pants</option>
                  <option value="outerwear">Outerwear / Jacket</option>
                  <option value="shoes">Shoes</option>
                  <option value="accessory">Accessory</option>
                  <option value="jewelry">Jewelry</option>
                  <option value="bag">Bag / Purse</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Color</label>
                <input value={form.color} onChange={(e) => update("color", e.target.value)} placeholder="Black, gold" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Fabric</label>
                <input value={form.fabric} onChange={(e) => update("fabric", e.target.value)} placeholder="Silk" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Brand</label>
                <input value={form.brand} onChange={(e) => update("brand", e.target.value)} placeholder="Brand name" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Season</label>
                <select value={form.season} onChange={(e) => update("season", e.target.value)} className={inputClass}>
                  <option value="">Any</option>
                  <option value="spring">Spring</option>
                  <option value="summer">Summer</option>
                  <option value="fall">Fall</option>
                  <option value="winter">Winter</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Size Range</label>
                <input value={form.size_range} onChange={(e) => update("size_range", e.target.value)} placeholder="XS-XL" className={inputClass} />
              </div>
            </div>
          </div>
          )}

          {/* Product Details */}
          {form.default_style === "product" && (
          <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4">
            <p className="text-xs font-semibold text-cyan-300 mb-3">Product Details</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Product Name</label>
                <input value={form.product_name} onChange={(e) => update("product_name", e.target.value)} placeholder="Product name" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Brand</label>
                <input value={form.brand} onChange={(e) => update("brand", e.target.value)} placeholder="Brand" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Category</label>
                <input value={form.category} onChange={(e) => update("category", e.target.value)} placeholder="Beauty, Tech, etc." className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Color</label>
                <input value={form.color} onChange={(e) => update("color", e.target.value)} placeholder="Rose gold" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Dimensions</label>
                <input value={form.dimensions} onChange={(e) => update("dimensions", e.target.value)} placeholder="8oz, 10x5cm" className={inputClass} />
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">SKU</label>
                <input value={form.sku} onChange={(e) => update("sku", e.target.value)} placeholder="SKU-12345" className={inputClass} />
              </div>
            </div>
          </div>
          )}

          {/* Background / Set Details */}
          {form.default_style === "background" && (
          <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-4">
            <p className="text-xs font-semibold text-green-300 mb-3">Background / Set Details</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Location Type</label>
                <select value={form.location_type} onChange={(e) => update("location_type", e.target.value)} className={inputClass}>
                  <option value="">Select...</option>
                  <option value="studio">Studio</option>
                  <option value="outdoor">Outdoor</option>
                  <option value="urban">Urban</option>
                  <option value="interior">Interior</option>
                  <option value="beach">Beach</option>
                  <option value="abstract">Abstract</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Lighting</label>
                <select value={form.lighting} onChange={(e) => update("lighting", e.target.value)} className={inputClass}>
                  <option value="">Select...</option>
                  <option value="natural">Natural</option>
                  <option value="golden_hour">Golden Hour</option>
                  <option value="studio">Studio</option>
                  <option value="neon">Neon</option>
                  <option value="dramatic">Dramatic</option>
                  <option value="soft">Soft</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Time of Day</label>
                <select value={form.time_of_day} onChange={(e) => update("time_of_day", e.target.value)} className={inputClass}>
                  <option value="">Any</option>
                  <option value="morning">Morning</option>
                  <option value="golden_hour">Golden Hour</option>
                  <option value="sunset">Sunset</option>
                  <option value="night">Night</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-gray-400 mb-1">Mood</label>
                <input value={form.mood} onChange={(e) => update("mood", e.target.value)} placeholder="Warm, luxurious" className={inputClass} />
              </div>
            </div>
          </div>
          )}

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


// ---------------------------------------------------------------------------
// Talent Profile Image — Shows default photo or upload prompt
// ---------------------------------------------------------------------------

function TalentProfileImage({ talent, onUpdate }: { talent: Record<string, unknown>; onUpdate: (t: Record<string, unknown>) => void }) {
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

// ---------------------------------------------------------------------------
// Talent Voice Section — ElevenLabs voice browser + assignment
// ---------------------------------------------------------------------------

function TalentVoiceSection({ talentId, talentName }: { talentId: string; talentName: string }) {
  const [voices, setVoices] = useState<Record<string, unknown>[]>([]);
  const [assignedVoices, setAssignedVoices] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState<string | null>(null);
  const [showCreateVoice, setShowCreateVoice] = useState(false);
  const [voiceDesc, setVoiceDesc] = useState("");
  const [voiceName, setVoiceName] = useState("");
  const [creating, setCreating] = useState(false);
  const [voiceMode, setVoiceMode] = useState<"generate" | "clone">("generate");
  const [cloneSample, setCloneSample] = useState<File | null>(null);
  const [previewAudio, setPreviewAudio] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/v1/voices/elevenlabs`).then((r) => r.json()),
      fetch(`${API_BASE}/api/v1/voice-profiles?talent_id=${talentId}`).then((r) => r.json()),
    ])
      .then(([elevenData, profileData]) => {
        setVoices(elevenData?.voices || []);
        setAssignedVoices(Array.isArray(profileData) ? profileData : []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [talentId]);

  async function assignVoice(voice: Record<string, unknown>) {
    setAssigning(voice.voice_id as string);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/voice-profiles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `${talentName} - ${voice.name}`,
          talent_id: talentId,
          provider: "elevenlabs",
          provider_voice_id: voice.voice_id,
          voice_type: "character",
          language: "en",
          gender: (voice.labels as Record<string, string>)?.gender || "",
          accent: (voice.labels as Record<string, string>)?.accent || "",
          metadata: { elevenlabs_voice: voice },
        }),
      });
      if (resp.ok) {
        const profile = await resp.json();
        setAssignedVoices((prev) => [...prev, profile]);
      }
    } catch {}
    setAssigning(null);
  }

  async function removeVoice(profileId: string) {
    try {
      await fetch(`${API_BASE}/api/v1/voice-profiles/${profileId}`, { method: "DELETE" });
      setAssignedVoices((prev) => prev.filter((v) => v.id !== profileId));
    } catch {}
  }

  if (loading) {
    return <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-purple-500" /></div>;
  }

  const assignedIds = new Set(assignedVoices.map((v) => v.provider_voice_id));

  return (
    <div className="space-y-4">
      {/* Create Voice Button */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-400 uppercase">Voice Management</p>
        <button
          onClick={() => setShowCreateVoice(true)}
          className="flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
        >
          <Sparkles className="h-3 w-3" /> Create Voice (MOSS)
        </button>
      </div>

      {/* Create Voice Modal — Generate or Clone */}
      {showCreateVoice && (
        <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-green-300">Create Voice for {talentName}</p>
            <button onClick={() => setShowCreateVoice(false)} className="text-xs text-gray-500 hover:text-white">&times;</button>
          </div>

          {/* Mode toggle: Generate vs Clone */}
          <div className="flex gap-2">
            <button
              onClick={() => setVoiceMode("generate")}
              className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium border transition-colors ${voiceMode === "generate" ? "bg-green-600/20 border-green-500/40 text-green-300" : "border-white/[0.08] text-gray-400 hover:text-white"}`}
            >
              Generate from Description
            </button>
            <button
              onClick={() => setVoiceMode("clone")}
              className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium border transition-colors ${voiceMode === "clone" ? "bg-purple-600/20 border-purple-500/40 text-purple-300" : "border-white/[0.08] text-gray-400 hover:text-white"}`}
            >
              Clone from Audio Sample
            </button>
          </div>

          {voiceMode === "generate" && (
            <div className="space-y-2">
              <input value={voiceName} onChange={(e) => setVoiceName(e.target.value)} placeholder={`${talentName}'s Voice`} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white placeholder:text-gray-600 outline-none" />
              <input value={voiceDesc} onChange={(e) => setVoiceDesc(e.target.value)} placeholder="Warm female voice, mid-30s, confident, slight accent..." className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white placeholder:text-gray-600 outline-none" />
            </div>
          )}

          {voiceMode === "clone" && (
            <div className="space-y-2">
              <input value={voiceName} onChange={(e) => setVoiceName(e.target.value)} placeholder={`${talentName}'s Voice (cloned)`} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-white placeholder:text-gray-600 outline-none" />
              <label className="block">
                <span className="text-[10px] text-gray-400">Upload audio sample (6+ seconds)</span>
                <input
                  type="file"
                  accept="audio/*"
                  className="mt-1 w-full text-xs text-gray-400 file:mr-2 file:rounded-lg file:border-0 file:bg-purple-600 file:px-3 file:py-1.5 file:text-xs file:text-white file:cursor-pointer"
                  onChange={(e) => setCloneSample(e.target.files?.[0] || null)}
                />
              </label>
              {cloneSample && <p className="text-[10px] text-green-400">Selected: {cloneSample.name}</p>}
            </div>
          )}

          {/* Preview Audio Player */}
          {previewAudio && (
            <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="text-[10px] text-gray-400 mb-1">Preview:</p>
              <audio controls className="w-full h-8" src={previewAudio} />
              <button
                onClick={async () => {
                  // Save to B2
                  try {
                    const resp = await fetch(`${API_BASE}/api/v1/voices/moss/generate-speech`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ text: "Hello, this is a sample of my voice.", talent_id: talentId, save: true }),
                    });
                    if (resp.ok) {
                      const data = await resp.json();
                      if (data.saved) {
                        setAssignedVoices((prev) => [...prev, ...(data.profile ? [data.profile] : [])]);
                      }
                    }
                  } catch {}
                }}
                className="mt-2 w-full rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
              >
                Save to Library
              </button>
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={async () => {
                setCreating(true);
                setPreviewAudio(null);
                try {
                  if (voiceMode === "generate") {
                    if (!voiceDesc.trim()) { setCreating(false); return; }
                    const resp = await fetch(`${API_BASE}/api/v1/voices/moss/create-voice`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ description: voiceDesc, name: voiceName || `${talentName}'s Voice`, talent_id: talentId }),
                    });
                    if (resp.ok) {
                      const data = await resp.json();
                      // If we got a sample URL, set preview
                      if (data.sample_url) {
                        setPreviewAudio(data.sample_url);
                      }
                      setAssignedVoices((prev) => [...prev, data.profile || data]);
                      setVoiceDesc("");
                      setVoiceName("");
                    }
                  } else {
                    // Clone mode — upload sample and generate speech
                    if (!cloneSample) { setCreating(false); return; }
                    // Upload sample file first
                    const formData = new FormData();
                    formData.append("file", cloneSample);
                    const uploadResp = await fetch(`${API_BASE}/api/v1/talent/${talentId}/media`, { method: "POST", body: formData });
                    if (uploadResp.ok) {
                      const asset = await uploadResp.json();
                      const sampleUrl = asset.public_url;
                      // Now generate speech with this sample as voice reference
                      const genResp = await fetch(`${API_BASE}/api/v1/voices/moss/generate-speech`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ text: "Hello, this is a sample of my cloned voice.", voice_sample_url: sampleUrl, talent_id: talentId, consent_acknowledged: true }),
                      });
                      if (genResp.ok) {
                        const genData = await genResp.json();
                        if (genData.audio_base64) {
                          setPreviewAudio(`data:audio/wav;base64,${genData.audio_base64}`);
                        }
                        // Create voice profile
                        const profileResp = await fetch(`${API_BASE}/api/v1/voice-profiles`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ name: voiceName || `${talentName}'s Voice (cloned)`, talent_id: talentId, provider: "moss-tts", voice_type: "cloned", metadata: { sample_url: sampleUrl, clone_source: cloneSample.name } }),
                        });
                        if (profileResp.ok) {
                          const profile = await profileResp.json();
                          setAssignedVoices((prev) => [...prev, profile]);
                        }
                      }
                    }
                    setCloneSample(null);
                    setVoiceName("");
                  }
                } catch {}
                setCreating(false);
              }}
              disabled={creating || (voiceMode === "generate" ? !voiceDesc.trim() : !cloneSample)}
              className="rounded-lg bg-green-600 px-4 py-2 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
            >
              {creating ? "Processing..." : voiceMode === "generate" ? "Generate Voice" : "Clone Voice"}
            </button>
            <button onClick={() => { setShowCreateVoice(false); setPreviewAudio(null); }} className="rounded-lg border border-white/[0.08] px-4 py-2 text-xs text-gray-400 hover:text-white">Cancel</button>
          </div>
        </div>
      )}

      {/* Assigned voices */}
      {assignedVoices.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase mb-2">Assigned Voices</p>
          <div className="space-y-2">
            {assignedVoices.map((v) => (
              <div key={v.id as string} className="rounded-lg border border-green-500/20 bg-green-500/5 px-3 py-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-white">{v.name as string}</p>
                    <p className="text-[10px] text-gray-400">
                      {v.provider as string} &middot; {v.language as string || "en"} &middot; {v.gender as string || "—"}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <VoiceDemoButton voiceProfile={v} talentName={talentName} />
                    <button
                      onClick={() => removeVoice(v.id as string)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Browse ElevenLabs voices */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase mb-2">
          ElevenLabs Voices ({voices.length} available)
        </p>
        <div className="max-h-[300px] overflow-y-auto space-y-1.5 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2">
          {voices.map((v) => {
            const voiceId = v.voice_id as string;
            const isAssigned = assignedIds.has(voiceId);
            const labels = (v.labels || {}) as Record<string, string>;
            return (
              <div
                key={voiceId}
                className={`flex items-center justify-between rounded-lg px-3 py-2 ${
                  isAssigned ? "bg-green-500/10 border border-green-500/20" : "hover:bg-white/[0.04]"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-white truncate">{v.name as string}</p>
                  <p className="text-[10px] text-gray-500">
                    {labels.accent || ""} {labels.gender || ""} {labels.age || ""} &middot; {labels.use_case || labels.description || ""}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {(v.preview_url as string) && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        const audio = new Audio(v.preview_url as string);
                        audio.play().catch(() => {});
                      }}
                      className="p-1 rounded text-gray-500 hover:text-purple-400 hover:bg-purple-400/10"
                      title="Play demo"
                    >
                      <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                    </button>
                  )}
                  {isAssigned ? (
                    <span className="text-[10px] text-green-400 font-medium">Assigned</span>
                  ) : (
                    <button
                      onClick={() => assignVoice(v)}
                      disabled={assigning === voiceId}
                      className="rounded-lg bg-purple-600 px-3 py-1 text-[10px] font-medium text-white hover:bg-purple-700 disabled:opacity-50"
                    >
                      {assigning === voiceId ? "..." : "Assign"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {voices.length === 0 && (
            <p className="text-xs text-gray-500 text-center py-4">
              No ElevenLabs voices found. Check your API key in Admin settings.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Talent Relationships Section — Associate talents with each other
// ---------------------------------------------------------------------------

function TalentRelationshipsSection({ talentId, allTalent }: { talentId: string; allTalent: Record<string, unknown>[] }) {
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


// ---------------------------------------------------------------------------
// Voice Demo Button — Plays a sample phrase using the assigned voice
// ---------------------------------------------------------------------------

function VoiceDemoButton({ voiceProfile, talentName }: { voiceProfile: Record<string, unknown>; talentName: string }) {
  const [playing, setPlaying] = useState(false);

  // Gender-aware sample phrases
  const FEMALE_PHRASES = [
    `Hi, I'm ${talentName}. This is how I sound.`,
    `Welcome to my world. I'm ${talentName}, and I'm excited to create with you.`,
    `Hey there! ${talentName} here. Let's make something beautiful today.`,
    `This is ${talentName} speaking. Ready when you are.`,
  ];
  const MALE_PHRASES = [
    `What's up, I'm ${talentName}. This is my voice.`,
    `Hey, ${talentName} here. Let's get to work.`,
    `This is ${talentName}. Ready to create something great.`,
    `${talentName} speaking. Let's make it happen.`,
  ];
  const NEUTRAL_PHRASES = [
    `Hello, I'm ${talentName}. This is a sample of my voice.`,
    `Hi there, ${talentName} here. This is how I sound.`,
    `This is ${talentName}. Nice to meet you.`,
  ];

  function getSamplePhrase(): string {
    const gender = String(voiceProfile.gender || "").toLowerCase();
    let phrases = NEUTRAL_PHRASES;
    if (gender.includes("female") || gender.includes("woman")) phrases = FEMALE_PHRASES;
    else if (gender.includes("male") || gender.includes("man")) phrases = MALE_PHRASES;
    return phrases[Math.floor(Math.random() * phrases.length)];
  }

  async function handlePlay() {
    if (playing) return;
    setPlaying(true);

    try {
      const provider = voiceProfile.provider as string;
      const phrase = getSamplePhrase();

      // Check if there's a saved sample URL in metadata
      const meta = (voiceProfile.metadata || {}) as Record<string, unknown>;
      const sampleUrl = meta.sample_url as string || meta.b2_url as string;

      if (sampleUrl) {
        // Play the saved sample directly
        const audio = new Audio(sampleUrl);
        audio.onended = () => setPlaying(false);
        audio.onerror = () => setPlaying(false);
        await audio.play();
        return;
      }

      // For ElevenLabs: use the preview URL if available
      const elevenVoice = meta.elevenlabs_voice as Record<string, unknown> | undefined;
      if (elevenVoice?.preview_url) {
        const audio = new Audio(elevenVoice.preview_url as string);
        audio.onended = () => setPlaying(false);
        audio.onerror = () => setPlaying(false);
        await audio.play();
        return;
      }

      // Generate a fresh sample via MOSS/provider
      const endpoint = provider === "elevenlabs"
        ? `${API_BASE}/api/v1/audio/tts/preview`
        : `${API_BASE}/api/v1/voices/moss/generate-speech`;

      const body = provider === "elevenlabs"
        ? { text: phrase, voice_id: voiceProfile.provider_voice_id, provider: "elevenlabs" }
        : { text: phrase, talent_id: voiceProfile.talent_id };

      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (resp.ok) {
        const data = await resp.json();
        const audioBase64 = data.audio_base64;
        if (audioBase64) {
          const audio = new Audio(`data:audio/wav;base64,${audioBase64}`);
          audio.onended = () => setPlaying(false);
          audio.onerror = () => setPlaying(false);
          await audio.play();
          return;
        }
      }
      setPlaying(false);
    } catch {
      setPlaying(false);
    }
  }

  return (
    <button
      onClick={handlePlay}
      disabled={playing}
      className="p-1.5 rounded-lg text-gray-400 hover:text-green-400 hover:bg-green-400/10 transition-colors disabled:opacity-50"
      title="Play voice demo"
    >
      {playing ? (
        <svg className="h-3.5 w-3.5 animate-pulse" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
      ) : (
        <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Talent Generations Section — Shows images generated for/with this talent
// ---------------------------------------------------------------------------

function TalentGenerationsSection({ talentId, talentName }: { talentId: string; talentName: string }) {
  const [generations, setGenerations] = useState<{id: string; filename: string; public_url?: string; metadata?: Record<string, unknown>; created_at?: string}[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch assets associated with this talent
    fetch(`${API_BASE}/api/v1/assets`)
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
