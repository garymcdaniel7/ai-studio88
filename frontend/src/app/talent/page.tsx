"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useEffect, useState } from "react";
import {
  GovernedConfirmationDialog,
  useGovernedAction,
} from "@/components/governed-action";
import type { ActionResult } from "@/components/governed-action";
import {
  Search,
  Plus,
  Upload,
  Filter,
  Star,
  MoreHorizontal,
  Users,
} from "lucide-react";
import { getTalent, createTalent, deleteTalent, updateTalent } from "@/lib/api";
import { useToast } from "@/components/toast";

const tabs = ["All Talent", "Models", "Characters", "Voices", "Influencers", "Wardrobe", "Products", "Backgrounds"];

import { usePageState } from "@/lib/page-state";
import { PageStateRenderer } from "@/components/page-state";
import { TalentMediaSection } from "./_components/talent-media-section";
import { TalentLoraSection } from "./_components/talent-lora-section";
import { TalentProfileImage } from "./_components/talent-profile-image";
import { TalentVoiceSection } from "./_components/talent-voice-section";
import { TalentRelationshipsSection } from "./_components/talent-relationships-section";
import { TalentGenerationsSection } from "./_components/talent-generations-section";

export default function TalentPage() {
  const [selectedTab, setSelectedTab] = useState("All Talent");
  const [selectedTalent, setSelectedTalent] = useState<Record<string, unknown> | null>(null);
  const { show } = useToast();
  const { dialogState, requestConfirmation, executeAction, cancel, retry } = useGovernedAction();

  // Unified page state: loading, error, stale, offline, retry — all handled
  const { state, data: talentData, error, freshness, isFetching, isOffline, retryAttempt, refresh, retry: retryFetch } = usePageState<Record<string, unknown>[]>({
    fetcher: async () => {
      const data = await getTalent();
      const items = Array.isArray(data) ? data : [];
      // Sort favorites to top
      const favs = JSON.parse(localStorage.getItem("talent_favorites") || "[]") as string[];
      items.sort((a, b) => {
        const aFav = favs.includes(a.id as string) ? 0 : 1;
        const bFav = favs.includes(b.id as string) ? 0 : 1;
        return aFav - bFav;
      });
      return items;
    },
    refreshInterval: 60_000, // Auto-refresh every 60s
    hasActiveFilter: selectedTab !== "All Talent",
  });

  // Select first talent when data loads
  useEffect(() => {
    if (talentData && talentData.length > 0 && !selectedTalent) {
      setSelectedTalent(talentData[0]);
    }
  }, [talentData, selectedTalent]);

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
      refresh(); // Re-fetch via unified page state
      setShowCreate(false);
      setNewName("");
      setNewBio("");
      show("Talent created!", "success");
    } catch {
      show("Failed to create talent", "error");
    }
  }

  const allTalent = talentData || [];
  const filtered = selectedTab === "All Talent" 
    ? allTalent 
    : allTalent.filter((t) => {
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

  return (
    <PageStateRenderer
      state={state}
      error={error}
      freshness={freshness}
      retryAttempt={retryAttempt}
      isOffline={isOffline}
      hasData={allTalent.length > 0}
      resource="talent"
      onRetry={retryFetch}
      onRefresh={refresh}
      onClearFilters={() => setSelectedTab("All Talent")}
      emptyState={
        <div className="flex flex-col items-center justify-center py-16">
          <Users className="h-10 w-10 text-content-muted mb-3" />
          <p className="text-sm text-content-tertiary">No talent yet</p>
          <p className="text-xs text-content-muted mt-1">Create your first AI persona to start generating content.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
          >
            <Plus className="h-4 w-4" /> Create Talent
          </button>
        </div>
      }
    >
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-content-primary">Talent</h1>
          <p className="text-sm text-content-muted">
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
            className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-content-secondary hover:bg-surface-active"
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
        <div className="rounded-xl border border-status-info/30 bg-surface-raised p-6">
          <h3 className="text-sm font-semibold text-content-primary mb-4">Create New Talent</h3>
          <div className="space-y-3">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Name (e.g. Melissa)"
              className="w-full rounded-lg border border-border-default bg-surface-hover px-4 py-2 text-sm text-content-secondary placeholder:text-content-muted outline-none focus:border-purple-500/50"
            />
            <textarea
              value={newBio}
              onChange={(e) => setNewBio(e.target.value)}
              placeholder="Bio / description..."
              className="w-full rounded-lg border border-border-default bg-surface-hover px-4 py-2 text-sm text-content-secondary placeholder:text-content-muted outline-none resize-none"
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
                className="rounded-lg border border-border-default px-4 py-2 text-sm text-content-tertiary hover:bg-surface-hover"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border-subtle pb-px">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setSelectedTab(tab)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              selectedTab === tab
                ? "border-b-2 border-purple-500 text-status-info"
                : "text-content-muted hover:text-content-secondary"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-6 gap-3">
        {[
          { label: "Total Talent", value: String(allTalent.length), sub: "AI personas", color: "text-blue-400" },
          { label: "Models", value: String(allTalent.filter((t) => !t.default_style || t.default_style === "model" || t.default_style === "fashion").length), sub: "Fashion & commercial", color: "text-purple-400" },
          { label: "Characters", value: String(allTalent.filter((t) => t.default_style === "character" || t.default_style === "story").length), sub: "Story characters", color: "text-amber-400" },
          { label: "Voices", value: String(allTalent.filter((t) => t.default_style === "voice" || t.default_style === "narrator").length), sub: "Voice profiles", color: "text-green-400" },
          { label: "Influencers", value: String(allTalent.filter((t) => t.default_style === "influencer" || t.default_style === "social").length), sub: "AI influencers", color: "text-pink-400" },
          { label: "Wardrobe Sets", value: String(allTalent.filter((t) => t.default_style === "wardrobe" || t.default_style === "fashion_set").length), sub: "Outfits & styles", color: "text-teal-400" },
        ].map((m) => (
          <div key={m.label} className="rounded-xl border border-border-subtle bg-surface-raised p-3 text-center">
            <p className="text-xs text-content-muted">{m.label}</p>
            <p className="text-xl font-bold text-content-primary">{m.value}</p>
            <p className={`text-xs ${m.color}`}>{m.sub}</p>
          </div>
        ))}
      </div>

      {/* Main Content: Grid + Detail Panel */}
      <div className="grid grid-cols-[1fr_380px] gap-6">
        {/* Talent Grid */}
        <div>
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-content-tertiary">
              Talent Library · {filtered.length} results
            </p>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 rounded-lg border border-border-default bg-surface-hover px-2 py-1">
                <Search className="h-3.5 w-3.5 text-content-muted" />
                <input className="w-32 bg-transparent text-xs text-content-secondary placeholder:text-content-muted outline-none" placeholder="Search..." />
              </div>
              <button aria-label="Filter talent" className="flex items-center gap-1 rounded-lg border border-border-default px-2 py-1 text-xs text-content-tertiary">
                <Filter className="h-3 w-3" /> Filters
              </button>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4">
            {filtered.length === 0 && !isFetching && (
              <div className="col-span-4 rounded-xl border border-border-subtle bg-surface-raised p-8 text-center">
                <Users className="h-10 w-10 text-content-muted mx-auto mb-3" />
                <p className="text-sm text-content-tertiary">
                  {selectedTab === "All Talent" ? "No talent yet" : `No ${selectedTab.toLowerCase()} found`}
                </p>
                <p className="text-xs text-content-muted mt-1">Create your first AI persona to start generating content.</p>
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
                    : "border-border-subtle hover:border-white/[0.12]"
                } bg-surface-raised`}
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
                    <p className="text-sm font-medium text-content-primary">{talent.name as string}</p>
                    <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-interactive-muted text-status-info">
                      {(talent.default_style as string) || "Model"}
                    </span>
                  </div>
                  <p className="text-xs text-content-muted">{(talent.bio as string)?.slice(0, 40) || "AI Talent"}</p>
                  <div className="mt-1 flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                      <span className="text-[10px] text-content-muted">Active</span>
                    </div>
                    <a
                      href={`/training?talent_id=${talent.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="text-[10px] text-status-info hover:text-purple-300 opacity-0 group-hover:opacity-100 transition-opacity"
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
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
            {/* Profile header */}
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-content-primary">{selectedTalent.name as string}</h3>
                  <button
                    onClick={() => {
                      const id = selectedTalent.id as string;
                      const favs = JSON.parse(localStorage.getItem("talent_favorites") || "[]") as string[];
                      const updated = favs.includes(id) ? favs.filter((f) => f !== id) : [id, ...favs];
                      localStorage.setItem("talent_favorites", JSON.stringify(updated));
                      // Force re-render by refreshing data
                      refresh();
                    }}
                    className="p-0.5"
                    title={JSON.parse(localStorage.getItem("talent_favorites") || "[]").includes(selectedTalent.id as string) ? "Remove from favorites" : "Add to favorites"}
                  >
                    <Star className={`h-4 w-4 cursor-pointer transition-colors ${JSON.parse(localStorage.getItem("talent_favorites") || "[]").includes(selectedTalent.id as string) ? "text-amber-400 fill-amber-400" : "text-gray-600 hover:text-amber-400"}`} />
                  </button>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <span className="rounded bg-interactive-muted px-2 py-0.5 text-xs font-medium text-status-info">
                    {(selectedTalent.default_style as string) || "Model"}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-status-success">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> Active
                  </span>
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => setShowEdit(true)} className="rounded-lg border border-border-default px-3 py-1.5 text-xs text-content-secondary hover:bg-surface-hover">Edit</button>
                <button
                  onClick={() => {
                    const talentName = (selectedTalent?.name as string) || "this talent";
                    const talentId = selectedTalent?.id as string;
                    requestConfirmation(
                      {
                        actionKey: `delete-talent-${talentId}`,
                        riskTier: "elevated",
                        verb: "Delete",
                        resourceName: talentName,
                        resourceType: "AI Talent",
                        consequence: `"${talentName}" and all associated training data will be permanently removed. This cannot be undone.`,
                      },
                      async (): Promise<ActionResult> => {
                        try {
                          await deleteTalent(talentId);
                          refresh();
                          setSelectedTalent(null);
                          return { success: true };
                        } catch (err: unknown) {
                          return { success: false, error: (err as Error)?.message || "Failed to delete talent." };
                        }
                      }
                    );
                  }}
                  className="rounded-lg border border-status-error/30 px-3 py-1.5 text-xs text-status-error hover:bg-red-400/10"
                >
                  Delete
                </button>
                <div className="relative">
                  <button
                    aria-label="More options"
                    onClick={() => setShowMoreMenu(!showMoreMenu)}
                    className="rounded-lg border border-border-default p-1.5 text-content-tertiary hover:bg-surface-hover"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                  {showMoreMenu && (
                    <div className="absolute right-0 top-full z-20 mt-1 w-44 rounded-xl border border-border-strong bg-surface-raised p-1.5 shadow-2xl">
                      <button
                        onClick={() => { setShowEdit(true); setShowMoreMenu(false); }}
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
                      >
                        Edit Profile
                      </button>
                      <button
                        onClick={() => {
                          // Duplicate talent
                          const copy = { ...selectedTalent, name: `${selectedTalent?.name} (copy)` } as Record<string, unknown>;
                          delete copy.id;
                          createTalent(copy).then(() => refresh());
                          setShowMoreMenu(false);
                        }}
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
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
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
                      >
                        Copy DNA
                      </button>
                      <button
                        onClick={() => {
                          window.location.href = `/training?talent_id=${selectedTalent?.id}`;
                          setShowMoreMenu(false);
                        }}
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
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
                        className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-content-secondary hover:bg-surface-hover"
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

            <p className="text-sm text-content-tertiary">
              {(selectedTalent.bio as string) || "Fashion and commercial model with a versatile look suitable for luxury, lifestyle, and editorial campaigns."}
            </p>

            {/* Tabs - dynamic based on talent type */}
            <div className="mt-4 flex gap-1 border-b border-border-subtle overflow-x-auto scrollbar-hide">
              {getTabsForType((selectedTalent.default_style as string) || "model").map((t) => (
                <button
                  key={t}
                  onClick={() => setDetailTab(t)}
                  className={`px-3 py-2 text-xs transition-colors whitespace-nowrap shrink-0 ${
                    detailTab === t
                      ? "text-status-info border-b border-purple-500"
                      : "text-content-muted hover:text-content-secondary"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            {detailTab === "Overview" && (
              <div className="mt-4 space-y-3">
                <h4 className="text-xs font-semibold text-content-tertiary uppercase">Profile</h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-content-muted">Full Name</span><p className="text-content-secondary">{(selectedTalent.name as string) || "—"}</p></div>
                  <div><span className="text-content-muted">Age</span><p className="text-content-secondary">{(selectedTalent.age as string) || "—"}</p></div>
                  <div><span className="text-content-muted">Height</span><p className="text-content-secondary">{(selectedTalent.height as string) || "—"}</p></div>
                  <div><span className="text-content-muted">Ethnicity</span><p className="text-content-secondary">{(selectedTalent.ethnicity as string) || "—"}</p></div>
                </div>

                {/* Creative DNA */}
                <div className="mt-4 rounded-lg border border-border-subtle bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold text-content-primary">Creative DNA</h4>
                    <button onClick={() => setShowEdit(true)} className="text-[10px] text-status-info">Edit</button>
                  </div>
                  <div className="mt-2 space-y-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-purple-500" />
                      <span className="text-content-tertiary">Visual Style:</span>
                      <span className="text-content-secondary">{(selectedTalent.visual_style as string) || "Not set"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-pink-500" />
                      <span className="text-content-tertiary">Best For:</span>
                      <span className="text-content-secondary">{(selectedTalent.best_for as string) || "Not set"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-blue-500" />
                      <span className="text-content-tertiary">Persona:</span>
                      <span className="text-content-secondary">{(selectedTalent.persona as string) || "Not set"}</span>
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
                <h4 className="text-xs font-semibold text-content-tertiary uppercase">All Fields</h4>
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Name</span><span className="text-content-secondary">{(selectedTalent.name as string) || "—"}</span></div>
                  <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Bio</span><span className="text-content-secondary text-right max-w-[200px] truncate">{(selectedTalent.bio as string) || "—"}</span></div>
                  <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Age</span><span className="text-content-secondary">{(selectedTalent.age as string) || "—"}</span></div>
                  <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Height</span><span className="text-content-secondary">{(selectedTalent.height as string) || "—"}</span></div>
                  <div className="flex justify-between border-b border-border-subtle pb-2"><span className="text-content-muted">Ethnicity</span><span className="text-content-secondary">{(selectedTalent.ethnicity as string) || "—"}</span></div>
                  <div className="flex justify-between"><span className="text-content-muted">Default Style</span><span className="text-content-secondary">{(selectedTalent.default_style as string) || "—"}</span></div>
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
                <TalentRelationshipsSection talentId={selectedTalent.id as string} allTalent={allTalent} />
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
              refresh(); // Re-fetch via page state
              setShowEdit(false);
              show("Talent updated successfully", "success");
            } catch {
              show("Failed to update talent", "error");
            }
          }}
        />
      )}

      {/* Governed Confirmation Dialog */}
      <GovernedConfirmationDialog
        dialogState={dialogState}
        onConfirm={executeAction}
        onCancel={cancel}
        onRetry={retry}
      />
    </div>
    </PageStateRenderer>
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

  const inputClass = "w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-sm text-white placeholder:text-content-muted focus:border-purple-500 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-border-default bg-surface-overlay p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-content-primary">Edit Talent</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg text-content-tertiary hover:text-content-primary hover:bg-surface-hover">
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
          <div className="rounded-lg border border-border-subtle p-4">
            <p className="text-xs font-semibold text-content-secondary mb-3">Physical Attributes</p>
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
          <div className="rounded-lg border border-border-subtle p-4">
            <p className="text-xs font-semibold text-content-secondary mb-3">Generation Settings</p>
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
