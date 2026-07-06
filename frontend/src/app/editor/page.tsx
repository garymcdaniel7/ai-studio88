"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useState, useEffect, useRef } from "react";
import {
  Film,
  Plus,
  Download,
  Sparkles,
  Loader2,
  GripVertical,
  Trash2,
  Play,
  Clock,
  ChevronDown,
  CheckCircle,
  XCircle,
  Layers,
  Image as ImageIcon,
  Save,
  FolderOpen,
  Users,
  Upload,
  Scissors,
  Gauge,
  Palette,
  Type,
} from "lucide-react";
import {
  getTalent,
  getStoryboards,
  createStoryboard,
  updateStoryboard,
  buildTalentPrompt,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Shot {
  id: string;
  order: number;
  prompt: string;
  model: string;
  duration: number; // seconds
  camera_motion: string;
  transition: string;
  aspect_ratio: string;
  status: "draft" | "generating" | "completed" | "failed";
  asset_id?: string;
  thumbnail_url?: string;
  error?: string;
}

type TransitionType = "cut" | "crossfade" | "fade_black" | "fade_white" | "wipe_left";
type CameraMotion = "static" | "pan_left" | "pan_right" | "dolly_in" | "dolly_out" | "tilt_up" | "tilt_down" | "orbit";

const MODELS = [
  { id: "wan-2.1-t2v", name: "WAN 2.1 T2V", type: "text-to-video" },
  { id: "wan-2.1-i2v", name: "WAN 2.1 I2V", type: "image-to-video" },
  { id: "flux-dev", name: "Flux Dev (Image)", type: "text-to-image" },
  { id: "sdxl-turbo", name: "SDXL Turbo (Image)", type: "text-to-image" },
];

const TRANSITIONS: { value: TransitionType; label: string }[] = [
  { value: "cut", label: "Hard Cut" },
  { value: "crossfade", label: "Crossfade" },
  { value: "fade_black", label: "Fade to Black" },
  { value: "fade_white", label: "Fade to White" },
  { value: "wipe_left", label: "Wipe Left" },
];

const CAMERA_MOTIONS: { value: CameraMotion; label: string }[] = [
  { value: "static", label: "Static" },
  { value: "pan_left", label: "Pan Left" },
  { value: "pan_right", label: "Pan Right" },
  { value: "dolly_in", label: "Dolly In" },
  { value: "dolly_out", label: "Dolly Out" },
  { value: "tilt_up", label: "Tilt Up" },
  { value: "tilt_down", label: "Tilt Down" },
  { value: "orbit", label: "Orbit" },
];

const ASPECT_RATIOS = ["16:9", "9:16", "1:1", "4:3", "21:9"];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function EditorPage() {
  const [editorMode, setEditorMode] = useState<"storyboard" | "quickedit">("storyboard");
  const [shots, setShots] = useState<Shot[]>([
    createShot(0, "A luxury penthouse interior at golden hour, cinematic lighting, wide shot"),
    createShot(1, "Close-up of a champagne glass being filled, bokeh background"),
    createShot(2, "Aerial view of Dubai marina at sunset, drone shot"),
  ]);
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

  function createShot(order: number, prompt = ""): Shot {
    return {
      id: crypto.randomUUID(),
      order,
      prompt,
      model: "wan-2.1-t2v",
      duration: 3,
      camera_motion: "static",
      transition: "crossfade",
      aspect_ratio: "16:9",
      status: "draft",
    };
  }

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

      const resp = await fetch(endpoint, {
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
      const resp = await fetch(`${API_BASE}/api/v1/productions/assemble`, {
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

// ---------------------------------------------------------------------------
// Quick Edit Panel — Upload video, apply ffmpeg transforms, export
// ---------------------------------------------------------------------------

function QuickEditPanel() {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Transform settings
  const [trimStart, setTrimStart] = useState("0");
  const [trimEnd, setTrimEnd] = useState("");
  const [speed, setSpeed] = useState("1.0");
  const [resolution, setResolution] = useState("original");
  const [colorGrade, setColorGrade] = useState("none");
  const [textOverlay, setTextOverlay] = useState("");
  const [textFont, setTextFont] = useState("Arial");

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file && file.type.startsWith("video/")) {
      setVideoFile(file);
      setVideoUrl(URL.createObjectURL(file));
      setResult(null);
    }
  }

  async function handleProcess() {
    if (!videoFile) return;
    setProcessing(true);
    setResult(null);

    try {
      // Upload the video first
      const formData = new FormData();
      formData.append("file", videoFile);
      formData.append("asset_type", "video");

      const uploadResp = await fetch(`${API_BASE}/api/v1/assets`, {
        method: "POST",
        body: formData,
      });
      const uploadData = await uploadResp.json();
      const assetId = uploadData?.id || uploadData?.asset_id;

      // Submit transform job
      const transformResp = await fetch(`${API_BASE}/api/v1/productions/assemble`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shots: [{ asset_id: assetId, duration: parseFloat(trimEnd || "0") - parseFloat(trimStart), transition: "cut" }],
          output_format: "mp4",
          transform: {
            trim_start: trimStart,
            trim_end: trimEnd || undefined,
            speed: parseFloat(speed),
            resolution: resolution !== "original" ? resolution : undefined,
            color_grade: colorGrade !== "none" ? colorGrade : undefined,
            text_overlay: textOverlay || undefined,
            text_font: textFont || undefined,
          },
        }),
      });
      const data = await transformResp.json();
      setResult(data.message || data.output_url || "Processing complete");
    } catch {
      setResult("Processing failed. Is the backend running?");
    } finally {
      setProcessing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Quick Edit</h2>
        <p className="text-sm text-gray-500">Upload a video → apply transforms → export via FFmpeg on GPU.</p>
      </div>

      <div className="grid grid-cols-[1fr_350px] gap-6">
        {/* Preview / Upload Area */}
        <div className="space-y-4">
          <div
            onClick={() => fileRef.current?.click()}
            className="aspect-video rounded-xl border-2 border-dashed border-white/[0.1] bg-[#0a0a1a] flex items-center justify-center cursor-pointer hover:border-purple-500/30 transition-colors overflow-hidden"
          >
            {videoUrl ? (
              <video src={videoUrl} controls className="w-full h-full object-contain rounded-lg" />
            ) : (
              <div className="text-center">
                <Upload className="h-12 w-12 text-gray-600 mx-auto mb-3" />
                <p className="text-sm text-gray-400">Drop a video or click to upload</p>
                <p className="text-xs text-gray-600 mt-1">MP4, MOV, WEBM — processed via FFmpeg on GPU</p>
              </div>
            )}
          </div>
          <input ref={fileRef} type="file" accept="video/*" className="hidden" onChange={handleFileSelect} />

          {videoFile && (
            <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-[#12122a] px-4 py-2">
              <div>
                <p className="text-sm text-white">{videoFile.name}</p>
                <p className="text-xs text-gray-500">{(videoFile.size / (1024 * 1024)).toFixed(1)} MB</p>
              </div>
              <button
                onClick={handleProcess}
                disabled={processing}
                className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
              >
                {processing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                {processing ? "Processing..." : "Export"}
              </button>
            </div>
          )}

          {result && (
            <div className="rounded-lg border border-green-500/20 bg-green-500/5 px-4 py-3">
              <p className="text-sm text-green-300">{result}</p>
            </div>
          )}
        </div>

        {/* Transform Controls */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5 space-y-4">
          <h3 className="text-sm font-semibold text-white">Transforms</h3>

          {/* Trim */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Scissors className="h-3.5 w-3.5 text-purple-400" />
              <label className="text-xs font-medium text-gray-300">Trim</label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-[10px] text-gray-500">Start (s)</span>
                <input type="number" step="0.1" min="0" value={trimStart} onChange={(e) => setTrimStart(e.target.value)} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-300 outline-none" />
              </div>
              <div>
                <span className="text-[10px] text-gray-500">End (s)</span>
                <input type="number" step="0.1" min="0" value={trimEnd} onChange={(e) => setTrimEnd(e.target.value)} placeholder="end" className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-300 outline-none placeholder:text-gray-600" />
              </div>
            </div>
          </div>

          {/* Speed */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Gauge className="h-3.5 w-3.5 text-blue-400" />
              <label className="text-xs font-medium text-gray-300">Speed: {speed}x</label>
            </div>
            <input type="range" min="0.25" max="4" step="0.25" value={speed} onChange={(e) => setSpeed(e.target.value)} className="w-full accent-purple-500" />
            <div className="flex justify-between text-[9px] text-gray-600 mt-0.5">
              <span>0.25x (slow-mo)</span><span>4x (timelapse)</span>
            </div>
          </div>

          {/* Resolution */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Film className="h-3.5 w-3.5 text-green-400" />
              <label className="text-xs font-medium text-gray-300">Resolution</label>
            </div>
            <select value={resolution} onChange={(e) => setResolution(e.target.value)} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none">
              <option value="original">Original</option>
              <option value="1920x1080">1080p (1920×1080)</option>
              <option value="1280x720">720p (1280×720)</option>
              <option value="3840x2160">4K (3840×2160)</option>
              <option value="1080x1920">Vertical 1080p (9:16)</option>
              <option value="1080x1080">Square (1:1)</option>
            </select>
          </div>

          {/* Color Grade */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Palette className="h-3.5 w-3.5 text-amber-400" />
              <label className="text-xs font-medium text-gray-300">Color Grade</label>
            </div>
            <select value={colorGrade} onChange={(e) => setColorGrade(e.target.value)} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none">
              <option value="none">None</option>
              <option value="cinematic">Cinematic (Teal & Orange)</option>
              <option value="vintage">Vintage Film</option>
              <option value="bw">Black & White</option>
              <option value="warm">Warm / Golden Hour</option>
              <option value="cool">Cool / Blue Hour</option>
              <option value="high-contrast">High Contrast</option>
              <option value="desaturated">Desaturated</option>
            </select>
          </div>

          {/* Text Overlay */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Type className="h-3.5 w-3.5 text-pink-400" />
              <label className="text-xs font-medium text-gray-300">Text Overlay</label>
            </div>
            <input type="text" value={textOverlay} onChange={(e) => setTextOverlay(e.target.value)} placeholder="Add text..." className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none placeholder:text-gray-600" />
            <select value={textFont} onChange={(e) => setTextFont(e.target.value)} className="w-full mt-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-300 outline-none">
              <option value="Arial">Arial (Clean)</option>
              <option value="Helvetica">Helvetica (Modern)</option>
              <option value="Georgia">Georgia (Serif)</option>
              <option value="Courier">Courier (Monospace)</option>
              <option value="Impact">Impact (Bold)</option>
              <option value="Comic Sans MS">Comic Sans (Casual)</option>
              <option value="Times New Roman">Times New Roman (Classic)</option>
              <option value="Futura">Futura (Geometric)</option>
            </select>
          </div>

          {/* Info */}
          <div className="rounded-lg border border-white/[0.04] bg-white/[0.01] p-3">
            <p className="text-[10px] text-gray-500">
              Transforms are applied server-side via FFmpeg on the GPU worker. Upload → process → download the result.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shot Card Component
// ---------------------------------------------------------------------------

function ShotCard({
  shot,
  index,
  onUpdate,
  onRemove,
  onGenerate,
  onDragStart,
  onDragOver,
  onDragEnd,
  isDragging,
}: {
  shot: Shot;
  index: number;
  onUpdate: (updates: Partial<Shot>) => void;
  onRemove: () => void;
  onGenerate: () => void;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  isDragging: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  const statusColors: Record<Shot["status"], string> = {
    draft: "border-white/[0.06]",
    generating: "border-purple-500/50 bg-purple-500/5",
    completed: "border-green-500/30",
    failed: "border-red-500/30",
  };

  const statusBadge: Record<Shot["status"], { text: string; color: string }> = {
    draft: { text: "Draft", color: "text-gray-500" },
    generating: { text: "Generating...", color: "text-purple-400" },
    completed: { text: "Done", color: "text-green-400" },
    failed: { text: "Failed", color: "text-red-400" },
  };

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      className={`rounded-xl border bg-[#12122a] transition-all ${statusColors[shot.status]} ${
        isDragging ? "opacity-50 scale-[0.98]" : ""
      }`}
    >
      {/* Main Row */}
      <div className="flex items-center gap-4 p-4">
        {/* Drag Handle */}
        <div className="cursor-grab active:cursor-grabbing text-gray-600 hover:text-gray-400">
          <GripVertical className="h-5 w-5" />
        </div>

        {/* Shot Number */}
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-purple-600/20 text-sm font-bold text-purple-400">
          {index + 1}
        </div>

        {/* Thumbnail */}
        <div className="h-14 w-24 shrink-0 rounded-lg bg-gradient-to-br from-[#1a1a3a] to-[#0d0d20] border border-white/[0.04] flex items-center justify-center overflow-hidden">
          {shot.thumbnail_url ? (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img src={shot.thumbnail_url} alt={`Shot ${index + 1}`} className="h-full w-full object-cover rounded-lg" />
          ) : shot.status === "generating" ? (
            <Loader2 className="h-5 w-5 text-purple-400 animate-spin" />
          ) : (
            <ImageIcon className="h-5 w-5 text-gray-700" />
          )}
        </div>

        {/* Prompt */}
        <div className="flex-1 min-w-0">
          <input
            type="text"
            value={shot.prompt}
            onChange={(e) => onUpdate({ prompt: e.target.value })}
            placeholder="Describe this shot..."
            className="w-full bg-transparent text-sm text-gray-200 placeholder:text-gray-600 outline-none"
          />
          <div className="flex items-center gap-3 mt-1">
            <span className="text-[10px] text-gray-600">{shot.model}</span>
            <span className="text-[10px] text-gray-600">{shot.duration}s</span>
            <span className="text-[10px] text-gray-600">{shot.camera_motion}</span>
            <span className="text-[10px] text-gray-600">→ {shot.transition}</span>
          </div>
        </div>

        {/* Status */}
        <span className={`text-xs font-medium ${statusBadge[shot.status].color}`}>
          {statusBadge[shot.status].text}
        </span>

        {/* Actions */}
        <div className="flex items-center gap-1">
          {(shot.status === "draft" || shot.status === "failed") && (
            <button
              onClick={onGenerate}
              className="rounded-lg bg-purple-600/20 p-2 text-purple-400 hover:bg-purple-600/30"
              title="Generate this shot"
            >
              <Play className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="rounded-lg p-2 text-gray-500 hover:text-gray-300 hover:bg-white/[0.04]"
            title="Settings"
          >
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
          </button>
          <button
            onClick={onRemove}
            className="rounded-lg p-2 text-gray-500 hover:text-red-400 hover:bg-red-400/10"
            title="Remove shot"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Expanded Settings */}
      {expanded && (
        <div className="border-t border-white/[0.04] px-4 py-3 grid grid-cols-5 gap-3">
          {/* Model */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Model</label>
            <select
              value={shot.model}
              onChange={(e) => onUpdate({ model: e.target.value })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>

          {/* Duration */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Duration (s)</label>
            <input
              type="number"
              min={1}
              max={15}
              value={shot.duration}
              onChange={(e) => onUpdate({ duration: parseInt(e.target.value) || 3 })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            />
          </div>

          {/* Camera Motion */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Camera</label>
            <select
              value={shot.camera_motion}
              onChange={(e) => onUpdate({ camera_motion: e.target.value })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {CAMERA_MOTIONS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>

          {/* Transition */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Transition</label>
            <select
              value={shot.transition}
              onChange={(e) => onUpdate({ transition: e.target.value })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {TRANSITIONS.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Aspect Ratio */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-1">Aspect Ratio</label>
            <select
              value={shot.aspect_ratio}
              onChange={(e) => onUpdate({ aspect_ratio: e.target.value })}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-xs text-gray-300 outline-none"
            >
              {ASPECT_RATIOS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Error */}
      {shot.error && (
        <div className="border-t border-red-500/10 px-4 py-2 flex items-center gap-2">
          <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
          <p className="text-xs text-red-300">{shot.error}</p>
        </div>
      )}
    </div>
  );
}
