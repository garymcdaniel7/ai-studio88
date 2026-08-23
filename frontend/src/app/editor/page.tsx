"use client";

import { useState, useEffect } from "react";
import { authFetch } from "@/lib/api";
import { Film, Plus, Layers, Scissors } from "lucide-react";
import {
  getTalent,
  getStoryboards,
  createStoryboard,
  updateStoryboard,
  buildTalentPrompt,
} from "@/lib/api";
import { QuickEditPanel } from "./_components/quick-edit-panel";
import { API_BASE, createShot, type Shot } from "./_components/editor-types";
import { ShotCard } from "./_components/shot-card";
import { StoryboardHeader } from "./_components/storyboard-header";
import { StatsBar } from "./_components/stats-bar";
import { LoadStoryboardModal } from "./_components/load-storyboard-modal";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function EditorPage() {
  const [editorMode, setEditorMode] = useState<"storyboard" | "quickedit">("storyboard");
  const [shots, setShots] = useState<Shot[]>([]);
  const [generating, setGenerating] = useState(false);
  const [assembling, setAssembling] = useState(false);
  const [assemblyResult, setAssemblyResult] = useState<string | null>(null);
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [storyboardId, setStoryboardId] = useState<string | null>(null);
  const [storyboardName, setStoryboardName] = useState("Untitled Storyboard");
  const [saving, setSaving] = useState(false);
  const [talents, setTalents] = useState<Record<string, unknown>[]>([]);
  const [selectedTalentId, setSelectedTalentId] = useState<string | null>(null);
  const [showLoadModal, setShowLoadModal] = useState(false);
  const [savedStoryboards, setSavedStoryboards] = useState<Record<string, unknown>[]>([]);

  // Load talents on mount
  useEffect(() => {
    getTalent()
      .then((data) => setTalents(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  function addShot() {
    setShots((prev) => [...prev, createShot(prev.length)]);
  }

  function removeShot(id: string) {
    setShots((prev) => prev.filter((s) => s.id !== id).map((s, i) => ({ ...s, order: i })));
  }

  function updateShot(id: string, updates: Partial<Shot>) {
    setShots((prev) => prev.map((s) => (s.id === id ? { ...s, ...updates } : s)));
  }

  // Drag reorder
  function handleDragStart(idx: number) {
    setDragIdx(idx);
  }

  function handleDragOver(e: React.DragEvent, idx: number) {
    e.preventDefault();
    if (dragIdx === null || dragIdx === idx) return;
    setShots((prev) => {
      const updated = [...prev];
      const [dragged] = updated.splice(dragIdx, 1);
      updated.splice(idx, 0, dragged);
      return updated.map((s, i) => ({ ...s, order: i }));
    });
    setDragIdx(idx);
  }

  function handleDragEnd() {
    setDragIdx(null);
  }

  // Save storyboard to DB
  const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "error">("idle");

  async function saveStoryboard() {
    setSaving(true);
    setSaveStatus("idle");
    try {
      if (storyboardId) {
        await updateStoryboard(storyboardId, { name: storyboardName, shots });
      } else {
        const result = await createStoryboard({ name: storyboardName, shots });
        setStoryboardId((result as Record<string, unknown>).id as string);
      }
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 3000);
    } catch {
      setSaveStatus("error");
      setTimeout(() => setSaveStatus("idle"), 3000);
    } finally {
      setSaving(false);
    }
  }

  // Load storyboards list
  async function loadStoryboardsList() {
    try {
      const data = await getStoryboards();
      setSavedStoryboards(Array.isArray(data) ? data : []);
    } catch {}
    setShowLoadModal(true);
  }

  // Load a specific storyboard
  function loadStoryboard(sb: Record<string, unknown>) {
    setStoryboardId(sb.id as string);
    setStoryboardName((sb.name as string) || "Untitled");
    const savedShots = sb.shots as Shot[] | undefined;
    if (Array.isArray(savedShots) && savedShots.length > 0) {
      setShots(savedShots);
    }
    setShowLoadModal(false);
  }

  // Inject talent DNA into a shot's prompt before generation
  async function injectTalentDNA(shotPrompt: string): Promise<{ prompt: string; negative: string }> {
    if (!selectedTalentId) return { prompt: shotPrompt, negative: "" };
    try {
      const result = await buildTalentPrompt(selectedTalentId, shotPrompt);
      return { prompt: result.enriched_prompt, negative: result.negative_prompt };
    } catch {
      return { prompt: shotPrompt, negative: "" };
    }
  }

  // Generate a single shot (with talent DNA injection)
  async function generateShot(id: string) {
    const shot = shots.find((s) => s.id === id);
    if (!shot || !shot.prompt.trim()) return;

    updateShot(id, { status: "generating", error: undefined });

    try {
      // Inject talent DNA into prompt
      const { prompt: enrichedPrompt, negative } = await injectTalentDNA(shot.prompt);

      const isVideo = shot.model.includes("wan");
      const endpoint = isVideo
        ? `${API_BASE}/api/v1/videos/generate`
        : `${API_BASE}/api/v1/generate/image`;

      const body = isVideo
        ? { prompt: enrichedPrompt, negative_prompt: negative, model_id: shot.model, duration: shot.duration, camera_motion: shot.camera_motion }
        : { prompt: enrichedPrompt, negative_prompt: negative, model: shot.model };

      const resp = await authFetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();

      if (data.success || data.video_url || data.asset_id || data.image_base64) {
        const thumbnail = data.image_base64
          ? `data:image/png;base64,${data.image_base64}`
          : data.thumbnail_url || undefined;
        updateShot(id, {
          status: "completed",
          asset_id: data.asset_id || data.id || id,
          thumbnail_url: thumbnail,
        });
      } else {
        updateShot(id, { status: "failed", error: data.detail || "Generation failed" });
      }
    } catch (err) {
      updateShot(id, { status: "failed", error: (err as Error).message });
    }
  }

  // Batch generate all draft shots
  async function batchGenerate() {
    setGenerating(true);
    const drafts = shots.filter((s) => s.status === "draft" || s.status === "failed");
    for (const shot of drafts) {
      await generateShot(shot.id);
    }
    setGenerating(false);
  }

  // Assemble all completed shots into a video
  async function assembleProduction() {
    const completed = shots.filter((s) => s.status === "completed" && s.asset_id);
    if (completed.length < 2) {
      alert("Need at least 2 completed shots to assemble.");
      return;
    }

    setAssembling(true);
    setAssemblyResult(null);

    try {
      const resp = await authFetch(`${API_BASE}/api/v1/productions/assemble`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shots: completed.map((s) => ({
            asset_id: s.asset_id,
            duration: s.duration,
            transition: s.transition,
          })),
          output_format: "mp4",
          aspect_ratio: shots[0]?.aspect_ratio || "16:9",
        }),
      });
      const data = await resp.json();
      setAssemblyResult(data.output_url || data.message || "Assembly complete");
    } catch (err) {
      setAssemblyResult(`Assembly failed: ${(err as Error).message}`);
    } finally {
      setAssembling(false);
    }
  }

  const completedCount = shots.filter((s) => s.status === "completed").length;
  const draftCount = shots.filter((s) => s.status === "draft" || s.status === "failed").length;
  const totalDuration = shots.reduce((sum, s) => sum + s.duration, 0);
  const selectedTalentName = selectedTalentId
    ? ((talents.find((t) => t.id === selectedTalentId)?.name as string) || "Unknown")
    : null;

  return (
    <div className="space-y-6">
      {/* Editor Mode Tabs */}
      <div className="flex items-center gap-1 border-b border-white/[0.06] pb-px -mb-2">
        <button
          onClick={() => setEditorMode("storyboard")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors ${
            editorMode === "storyboard" ? "border-b-2 border-purple-500 text-purple-400" : "text-gray-500 hover:text-gray-300"
          }`}
        >
          <Layers className="h-4 w-4" /> Storyboard
        </button>
        <button
          onClick={() => setEditorMode("quickedit")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors ${
            editorMode === "quickedit" ? "border-b-2 border-purple-500 text-purple-400" : "text-gray-500 hover:text-gray-300"
          }`}
        >
          <Scissors className="h-4 w-4" /> Quick Edit
        </button>
      </div>

      {/* Quick Edit Mode */}
      {editorMode === "quickedit" && <QuickEditPanel />}

      {/* Storyboard Mode */}
      {editorMode === "storyboard" && (<>
      {/* Header */}
      <StoryboardHeader
        storyboardName={storyboardName}
        onNameChange={setStoryboardName}
        talents={talents}
        selectedTalentId={selectedTalentId}
        onTalentChange={(value) => setSelectedTalentId(value || null)}
        saving={saving}
        saveStatus={saveStatus}
        onSave={saveStoryboard}
        onLoad={loadStoryboardsList}
        generating={generating}
        draftCount={draftCount}
        onGenerateAll={batchGenerate}
        assembling={assembling}
        completedCount={completedCount}
        onAssemble={assembleProduction}
      />

      {/* Stats Bar */}
      <StatsBar
        shotCount={shots.length}
        totalDuration={totalDuration}
        completedCount={completedCount}
        draftCount={draftCount}
        talentName={selectedTalentName}
      />

      {/* Assembly Result */}
      {assemblyResult && (
        <div className="rounded-xl border border-green-500/20 bg-green-500/5 px-5 py-3">
          <p className="text-sm text-green-300">{assemblyResult}</p>
        </div>
      )}

      {/* Shot Grid */}
      <div className="space-y-3">
        {shots.length === 0 && (
          <div className="rounded-xl border border-dashed border-white/[0.1] bg-[#12122a] p-10 text-center">
            <Film className="h-10 w-10 text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-400">Add your first shot to begin your storyboard.</p>
            <p className="text-xs text-gray-600 mt-1">Each shot is a prompt that becomes a generated clip.</p>
          </div>
        )}
        {shots.map((shot, idx) => (
          <ShotCard
            key={shot.id}
            shot={shot}
            index={idx}
            onUpdate={(updates) => updateShot(shot.id, updates)}
            onRemove={() => removeShot(shot.id)}
            onGenerate={() => generateShot(shot.id)}
            onDragStart={() => handleDragStart(idx)}
            onDragOver={(e) => handleDragOver(e, idx)}
            onDragEnd={handleDragEnd}
            isDragging={dragIdx === idx}
          />
        ))}
      </div>

      {/* Add Shot */}
      <button
        onClick={addShot}
        className="w-full flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-white/[0.08] py-4 text-sm text-gray-400 hover:border-purple-500/30 hover:text-purple-400 transition-colors"
      >
        <Plus className="h-4 w-4" /> Add Shot
      </button>

      {/* Load Storyboard Modal */}
      {showLoadModal && (
        <LoadStoryboardModal
          storyboards={savedStoryboards}
          onSelect={loadStoryboard}
          onClose={() => setShowLoadModal(false)}
        />
      )}
      </>)}
    </div>
  );
}
