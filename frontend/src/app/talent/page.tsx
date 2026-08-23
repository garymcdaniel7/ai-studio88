"use client";

import { useEffect, useState } from "react";
import {
  GovernedConfirmationDialog,
  useGovernedAction,
} from "@/components/governed-action";
import type { ActionResult } from "@/components/governed-action";
import {
  Plus,
  Upload,
  Users,
} from "lucide-react";
import { getTalent, createTalent, deleteTalent, updateTalent } from "@/lib/api";
import { useToast } from "@/components/toast";

import { usePageState } from "@/lib/page-state";
import { PageStateRenderer } from "@/components/page-state";
import { readFavorites, toggleFavorite } from "./_hooks/use-talent-favorites";
import { TalentTabs } from "./_components/talent-tabs";
import { TalentMetrics } from "./_components/talent-metrics";
import { TalentGrid, type TalentRecord } from "./_components/talent-grid";
import { TalentDetail } from "./_components/talent-detail";
import { TalentEditModal } from "./_components/edit-talent-modal";
import { CreateTalentForm } from "./_components/create-talent-form";

export default function TalentPage() {
  const [selectedTab, setSelectedTab] = useState("All Talent");
  const [selectedTalent, setSelectedTalent] = useState<TalentRecord | null>(null);
  const { show } = useToast();
  const { dialogState, requestConfirmation, executeAction, cancel, retry } = useGovernedAction();

  // Unified page state: loading, error, stale, offline, retry — all handled
  const { state, data: talentData, error, freshness, isFetching, isOffline, retryAttempt, refresh, retry: retryFetch } = usePageState<TalentRecord[]>({
    fetcher: async () => {
      const data = await getTalent();
      const items = Array.isArray(data) ? data : [];
      // Sort favorites to top
      const favs = readFavorites();
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

  function handleToggleFavorite(id: string) {
    toggleFavorite(id);
    // Force re-render by refreshing data
    refresh();
  }

  function handleDuplicate() {
    // Duplicate talent
    if (!selectedTalent) return;
    const copy = { ...selectedTalent, name: `${selectedTalent?.name} (copy)` } as Record<string, unknown>;
    delete copy.id;
    createTalent(copy)
      .then(() => refresh())
      .catch(() => show("Failed to duplicate talent", "error"));
  }

  function handleDeleteConfirmation() {
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

      {/* Create Talent Form */}
      {showCreate && (
        <CreateTalentForm
          name={newName}
          bio={newBio}
          onNameChange={setNewName}
          onBioChange={setNewBio}
          onCreate={createNewTalent}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {/* Tabs */}
      <TalentTabs selectedTab={selectedTab} onSelectTab={setSelectedTab} />

      {/* Metrics */}
      <TalentMetrics items={allTalent} />

      {/* Main Content: Grid + Detail Panel */}
      <div className="grid grid-cols-[1fr_380px] gap-6">
        {/* Talent Grid */}
        <TalentGrid
          items={filtered}
          selectedId={(selectedTalent?.id as string) || null}
          selectedTab={selectedTab}
          isFetching={isFetching}
          onSelect={setSelectedTalent}
          onCreateClick={() => setShowCreate(true)}
        />

        {/* Detail Panel */}
        {selectedTalent && (
          <TalentDetail
            talent={selectedTalent}
            allTalent={allTalent}
            detailTab={detailTab}
            onDetailTabChange={setDetailTab}
            onEdit={() => setShowEdit(true)}
            onDelete={handleDeleteConfirmation}
            onDuplicate={handleDuplicate}
            onToggleFavorite={handleToggleFavorite}
            onAvatarChange={(url) => setSelectedTalent((prev) => prev ? { ...prev, avatar_url: url } : prev)}
          />
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
