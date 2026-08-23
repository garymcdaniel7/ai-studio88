"use client";

import { useState, useEffect } from "react";
import { authFetch } from "@/lib/api";
import {
  Film,
  Plus,
  Download,
  Sparkles,
  Loader2,
  Clock,
  CheckCircle,
  XCircle,
  Layers,
  Save,
  FolderOpen,
  Users,
  Scissors,
} from "lucide-react";
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
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <input
              value={storyboardName}
              onChange={(e) => setStoryboardName(e.target.value)}
              className="text-2xl font-bold text-white bg-transparent border-none outline-none focus:border-b focus:border-purple-500"
              placeholder="Storyboard name..."
            />
            <p className="text-sm text-gray-500">
              Plan shots, generate clips, assemble your production.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Talent Selector */}
          <select
            value={selectedTalentId || ""}
            onChange={(e) => setSelectedTalentId(e.target.value || null)}
            className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none"
          >
            <option value="">No talent (raw prompts)</option>
            {talents.map((t) => (
              <option key={t.id as string} value={t.id as string}>
                {t.name as string} — DNA inject
              </option>
            ))}
          </select>
          {/* Save */}
          <button
            onClick={saveStoryboard}
            disabled={saving}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm disabled:opacity-50 ${
              saveStatus === "saved" ? "border-green-500/30 bg-green-500/10 text-green-400" :
              saveStatus === "error" ? "border-red-500/30 bg-red-500/10 text-red-400" :
              "border-white/[0.08] bg-white/[0.03] text-gray-300 hover:bg-white/[0.06]"
            }`}
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : saveStatus === "saved" ? <CheckCircle className="h-4 w-4" /> : <Save className="h-4 w-4" />}
            {saveStatus === "saved" ? "Saved!" : saveStatus === "error" ? "Error" : "Save"}
          </button>
          {/* Load */}
          <button
            onClick={loadStoryboardsList}
            className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]"
          >
            <FolderOpen className="h-4 w-4" /> Load
          </button>
          {/* Generate All */}
          <button
            onClick={batchGenerate}
            disabled={generating || draftCount === 0}
            className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {generating ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Generating...</>
            ) : (
              <><Sparkles className="h-4 w-4" /> Generate All ({draftCount})</>
            )}
          </button>
          {/* Assemble */}
          <button
            onClick={assembleProduction}
            disabled={assembling || completedCount < 2}
            className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-gray-300 hover:bg-white/[0.06] disabled:opacity-50"
          >
            {assembling ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Assembling...</>
            ) : (
              <><Download className="h-4 w-4" /> Assemble Video</>
            )}
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="flex items-center gap-6 rounded-xl border border-white/[0.06] bg-[#12122a] px-5 py-3">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-purple-400" />
          <span className="text-xs text-gray-400">{shots.length} shots</span>
        </div>
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-blue-400" />
          <span className="text-xs text-gray-400">{totalDuration}s total</span>
        </div>
        <div className="flex items-center gap-2">
          <CheckCircle className="h-4 w-4 text-green-400" />
          <span className="text-xs text-gray-400">{completedCount} generated</span>
        </div>
        <div className="flex items-center gap-2">
          <Film className="h-4 w-4 text-amber-400" />
          <span className="text-xs text-gray-400">{draftCount} pending</span>
        </div>
        {selectedTalentId && (
          <div className="flex items-center gap-2 ml-auto">
            <Users className="h-4 w-4 text-pink-400" />
            <span className="text-xs text-pink-300">
              DNA: {talents.find((t) => t.id === selectedTalentId)?.name as string || "Unknown"}
            </span>
          </div>
        )}
      </div>

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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl max-h-[70vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white">Load Storyboard</h2>
              <button onClick={() => setShowLoadModal(false)} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">
                <XCircle className="h-5 w-5" />
              </button>
            </div>
            {savedStoryboards.length > 0 ? (
              <div className="space-y-2">
                {savedStoryboards.map((sb) => (
                  <button
                    key={sb.id as string}
                    onClick={() => loadStoryboard(sb)}
                    className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 text-left hover:border-purple-500/30"
                  >
                    <p className="text-sm font-medium text-white">{sb.name as string || "Untitled"}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {Array.isArray(sb.shots) ? `${(sb.shots as unknown[]).length} shots` : "0 shots"}
                      {sb.updated_at ? ` · ${new Date(sb.updated_at as string).toLocaleDateString()}` : ""}
                    </p>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500 text-center py-6">No saved storyboards yet.</p>
            )}
          </div>
        </div>
      )}
      </>)}
    </div>
  );
}
