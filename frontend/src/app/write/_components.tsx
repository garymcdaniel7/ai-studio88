"use client";

import { useRef, useState } from "react";
import {
  AlertTriangle,
  ChevronRight,
  Film,
  ImagePlus,
  Loader2,
  RefreshCw,
  RotateCcw,
  Save,
  Upload,
  X,
} from "lucide-react";
import {
  H3_FRAME_GRID,
  H3_SECTIONS,
  type Episode,
  type PromptSection,
  type PromptSections,
  type Scene,
  type Shot,
  type UploadedReference,
  getApiError,
  parseH3Prompt,
  serializeH3Prompt,
  uploadReference,
} from "./contracts";

const panelClass = "rounded-xl border border-slate-700/70 bg-slate-900/80 shadow-sm";
const inputClass = "w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-violet-500 focus:ring-1 focus:ring-violet-500/40";

export function WriteSkeleton() {
  return (
    <div className="space-y-5" aria-label="Loading WRITE editor">
      <div className="h-8 w-64 animate-pulse rounded bg-slate-800" />
      <div className="grid min-h-[620px] grid-cols-[220px_minmax(0,1fr)_360px] gap-4">
        {["w-52", "w-full", "w-full"].map((width, index) => (
          <div key={index} className={`${panelClass} animate-pulse p-4`}>
            <div className={`h-4 ${width} rounded bg-slate-800`} />
            <div className="mt-5 space-y-3">
              {[1, 2, 3, 4, 5].map((row) => <div key={row} className="h-12 rounded bg-slate-800/70" />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function RecoverableError({ message, requestId, onRetry }: { message: string; requestId?: string; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-red-500/30 bg-red-950/20 p-6" role="alert">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-red-200">WRITE could not load this story.</p>
          <p className="mt-1 text-xs text-red-300/80">{message}</p>
          {requestId && <p className="mt-3 font-mono text-[10px] text-red-300/60">Request ID: {requestId}</p>}
          <button onClick={onRetry} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-red-500/15 px-3 py-2 text-xs font-medium text-red-200 hover:bg-red-500/25">
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      </div>
    </div>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: React.ReactNode }) {
  return (
    <div className={`${panelClass} flex min-h-[360px] flex-col items-center justify-center p-8 text-center`}>
      <Film className="h-10 w-10 text-slate-600" />
      <h2 className="mt-4 text-sm font-semibold text-slate-200">{title}</h2>
      <p className="mt-2 max-w-sm text-xs leading-5 text-slate-500">{detail}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function EpisodeList({ episodes, selectedId, onSelect }: { episodes: Episode[]; selectedId?: string; onSelect: (episode: Episode) => void }) {
  return (
    <aside className={`${panelClass} min-h-[620px] p-3`} aria-label="Episodes">
      <div className="flex items-center justify-between px-2 py-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Write</p>
          <h2 className="mt-1 text-sm font-semibold text-slate-100">Episodes</h2>
        </div>
        <span className="rounded-full bg-slate-800 px-2 py-1 text-[10px] text-slate-400">{episodes.length}</span>
      </div>
      <div className="mt-3 space-y-1.5">
        {episodes.map((episode) => (
          <button key={episode.id} onClick={() => onSelect(episode)} className={`group flex w-full items-center gap-2 rounded-lg px-3 py-3 text-left transition ${selectedId === episode.id ? "bg-violet-500/15 text-violet-100 ring-1 ring-violet-500/30" : "text-slate-300 hover:bg-slate-800/80"}`}>
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-slate-800 font-mono text-[10px] text-slate-400">{episode.episode_number ?? "—"}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium">{episode.title || "Untitled episode"}</span>
              <span className="mt-1 block truncate text-[10px] text-slate-500">{episode.status ?? "draft"}</span>
            </span>
            <ChevronRight className="h-3.5 w-3.5 text-slate-600 group-hover:text-slate-400" />
          </button>
        ))}
      </div>
    </aside>
  );
}

export function StoryboardTimeline({ scenes, shots, selectedId, onSelect }: { scenes: Scene[]; shots: Shot[]; selectedId?: string; onSelect: (shot: Shot) => void }) {
  const sceneById = new Map(scenes.map((scene) => [scene.id, scene]));
  return (
    <section className={`${panelClass} min-h-[620px] overflow-hidden`} aria-label="Storyboard timeline">
      <div className="border-b border-slate-800 px-5 py-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Storyboard</p>
        <div className="mt-1 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-100">Visual timeline</h2>
          <span className="text-[10px] text-slate-500">{shots.length} shots</span>
        </div>
      </div>
      <div className="overflow-x-auto p-5">
        {shots.length === 0 ? (
          <div className="flex min-h-[480px] items-center justify-center text-center">
            <div><Film className="mx-auto h-9 w-9 text-slate-700" /><p className="mt-3 text-xs text-slate-400">No shots in this episode yet.</p><p className="mt-1 text-[10px] text-slate-600">Add shots through the Story Engine, then return here to customize them.</p></div>
          </div>
        ) : (
          <div className="flex min-w-max gap-3 pb-2">
            {shots.map((shot) => {
              const scene = sceneById.get(shot.scene_id);
              const thumbnail = shot.thumbnail_url || shot.signed_url || shot.cdn_url;
              return (
                <button key={shot.id} data-testid={`shot-card-${shot.id}`} onClick={() => onSelect(shot)} className={`w-44 rounded-xl border p-2 text-left transition ${selectedId === shot.id ? "border-violet-500 bg-violet-500/10 ring-2 ring-violet-500/20" : "border-slate-700 bg-slate-950/60 hover:border-slate-600"}`} aria-label={`Shot ${shot.shot_number ?? ""} ${shot.description ?? ""}`}>
                  <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-slate-800">
                    {thumbnail ? <img src={thumbnail} alt="" className="h-full w-full object-cover" /> : <ImagePlus className="h-6 w-6 text-slate-600" />}
                    <span className="absolute left-2 top-2 rounded bg-slate-950/80 px-1.5 py-1 font-mono text-[10px] text-slate-300">#{shot.shot_number ?? "—"}</span>
                  </div>
                  <p className="mt-2 truncate text-xs font-medium text-slate-200">{shot.shot_type || shot.shot_size || "Shot"}</p>
                  <p className="mt-1 truncate text-[10px] text-slate-500">{scene?.location || "Scene context"}</p>
                  <div className="mt-3 flex items-center justify-between text-[10px] text-slate-500"><span>{shot.duration_seconds ? `${shot.duration_seconds}s` : "Preview"}</span><span className={shot.status === "completed" ? "text-emerald-400" : "text-slate-500"}>{shot.status || "draft"}</span></div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

export function PromptPreview({ sections }: { sections: PromptSections }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3" aria-label="Prompt preview">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Prompt preview</p>
      <pre className="max-h-44 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-5 text-slate-300">{serializeH3Prompt(sections)}</pre>
    </div>
  );
}

export function PromptEditor({ initialPrompt, onSave, onCancel, saving }: { initialPrompt: string; onSave: (prompt: string) => Promise<void>; onCancel: () => void; saving: boolean }) {
  const [sections, setSections] = useState<PromptSections>(() => parseH3Prompt(initialPrompt));
  const [active, setActive] = useState<PromptSection>(H3_SECTIONS[0]);
  const [error, setError] = useState("");

  async function save() {
    if (!sections.Subject.trim() || !sections.Action.trim()) {
      setError("Subject and Action are required before saving a preview prompt.");
      return;
    }
    setError("");
    await onSave(serializeH3Prompt(sections));
  }

  return (
    <div className="space-y-3" data-testid="prompt-editor">
      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Prompt sections">
        {H3_SECTIONS.map((section) => <button key={section} role="tab" aria-selected={active === section} onClick={() => setActive(section)} className={`rounded-md px-2 py-1.5 text-[10px] font-medium ${active === section ? "bg-violet-500/20 text-violet-200" : "text-slate-500 hover:bg-slate-800 hover:text-slate-300"}`}>### {section}</button>)}
      </div>
      <label className="block text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500" htmlFor={`prompt-${active}`}>### {active}</label>
      <textarea id={`prompt-${active}`} value={sections[active]} onChange={(event) => setSections((current) => ({ ...current, [active]: event.target.value }))} rows={4} className={`${inputClass} resize-y font-mono text-xs leading-5`} aria-label={`${active} prompt section`} />
      {error && <p className="text-xs text-amber-300" role="alert">{error}</p>}
      <PromptPreview sections={sections} />
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-400 hover:text-slate-100"><X className="h-3.5 w-3.5" /> Cancel</button>
        <button onClick={save} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-medium text-white hover:bg-violet-500 disabled:opacity-50"><Save className="h-3.5 w-3.5" /> {saving ? "Saving…" : "Save prompt"}</button>
      </div>
    </div>
  );
}

export function ReferenceImages({ references, onAdd, onRemove }: { references: UploadedReference[]; onAdd: (reference: UploadedReference) => void; onRemove: (id: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  async function chooseFile(file: File | undefined) {
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.type)) { setError("Use a JPEG, PNG, WebP, or GIF reference image."); return; }
    setUploading(true); setError("");
    try { onAdd(await uploadReference(file)); } catch (reason) { setError(getApiError(reason).message); } finally { setUploading(false); if (input.current) input.current.value = ""; }
  }

  return (
    <div className="space-y-2" data-testid="reference-images">
      <div className="flex items-center justify-between"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Reference images</p><span className="text-[10px] text-slate-600">{references.length}/4</span></div>
      <div className="grid grid-cols-4 gap-2">
        {references.map((reference, index) => { const url = reference.thumbnail_url || reference.signed_url || reference.cdn_url; return <div key={reference.id} className="group relative aspect-square overflow-hidden rounded-lg border border-slate-700 bg-slate-950">{url ? <img src={url} alt={`Reference ${index + 1}`} className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-[9px] text-slate-500">Uploaded</div>}<span className="absolute bottom-1 left-1 rounded bg-slate-950/80 px-1 py-0.5 font-mono text-[9px] text-slate-300">{index + 1}</span><button onClick={() => onRemove(reference.id)} aria-label={`Remove reference ${index + 1}`} className="absolute right-1 top-1 rounded bg-slate-950/80 p-1 text-slate-300 opacity-0 transition group-hover:opacity-100"><X className="h-3 w-3" /></button></div>; })}
        {references.length < 4 && <button onClick={() => input.current?.click()} disabled={uploading} className="flex aspect-square flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 text-slate-500 hover:border-violet-500 hover:text-violet-300 disabled:opacity-50"><Upload className="h-4 w-4" /> <span className="mt-1 text-[9px]">{uploading ? "Uploading" : "Add"}</span></button>}
      </div>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" onChange={(event) => void chooseFile(event.target.files?.[0])} />
      {error && <p className="text-[10px] text-amber-300" role="alert">{error}</p>}
    </div>
  );
}

export function ShotDetails({ shot, scene, previousShot, onUpdate, onRegenerate }: { shot: Shot; scene?: Scene; previousShot?: Shot; onUpdate: (shot: Shot) => void; onRegenerate: (prompt: string, frameGrid: (typeof H3_FRAME_GRID)[number], references: UploadedReference[], continuity: string) => Promise<void> }) {
  const [editingPrompt, setEditingPrompt] = useState(false);
  const [saving, setSaving] = useState(false);
  const [prompt, setPrompt] = useState(() => (shot.generation_params?.prompt as string) || shot.description || "");
  const [references, setReferences] = useState<UploadedReference[]>(() => ((shot.metadata?.references as UploadedReference[]) || []));
  const [frameGrid, setFrameGrid] = useState<(typeof H3_FRAME_GRID)[number]>(() => { const value = Number(shot.generation_params?.frame_grid ?? 226); return H3_FRAME_GRID.includes(value as (typeof H3_FRAME_GRID)[number]) ? value as (typeof H3_FRAME_GRID)[number] : 226; });
  const [continuity, setContinuity] = useState((shot.metadata?.continuity as string) || "");
  const [actionError, setActionError] = useState<{ message: string; requestId: string } | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  async function savePrompt(nextPrompt: string) {
    setSaving(true); setActionError(null);
    try {
      const updated = await import("./contracts").then(({ updateShot }) => updateShot(shot.id, { description: nextPrompt, generation_params: { ...(shot.generation_params || {}), prompt: nextPrompt, frame_grid: frameGrid }, metadata: { ...(shot.metadata || {}), references, continuity } }));
      onUpdate({ ...shot, ...updated, description: nextPrompt, generation_params: { ...(shot.generation_params || {}), prompt: nextPrompt, frame_grid: frameGrid } });
      setPrompt(nextPrompt); setEditingPrompt(false);
    } catch (reason) { setActionError(getApiError(reason)); } finally { setSaving(false); }
  }

  async function regenerate() {
    setRegenerating(true); setActionError(null);
    try { await onRegenerate(prompt, frameGrid, references, continuity); } catch (reason) { setActionError(getApiError(reason)); } finally { setRegenerating(false); }
  }

  return (
    <aside className={`${panelClass} min-h-[620px] overflow-y-auto`} aria-label="Shot details">
      <div className="border-b border-slate-800 px-5 py-4"><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Shot {shot.shot_number ?? "—"}</p><h2 className="mt-1 truncate text-sm font-semibold text-slate-100">{shot.shot_type || shot.shot_size || "Shot detail"}</h2><p className="mt-1 text-[10px] text-slate-500">{scene?.location || "Location not set"} · {scene?.time_of_day || "time not set"}</p></div>
      <div className="space-y-5 p-5">
        <div className="grid grid-cols-2 gap-2 text-[10px]"><div className="rounded-lg bg-slate-800/60 p-2"><span className="block text-slate-600">Character context</span><span className="mt-1 block text-slate-300">{scene?.characters?.join(", ") || "Inherited from talent"}</span></div><div className="rounded-lg bg-slate-800/60 p-2"><span className="block text-slate-600">Continuity</span><span className="mt-1 block text-slate-300">{previousShot ? `After shot ${previousShot.shot_number ?? "—"}` : "Opening shot"}</span></div></div>
        <div className="space-y-2"><div className="flex items-center justify-between"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Prompt</p>{!editingPrompt && <button data-testid="edit-prompt" onClick={() => setEditingPrompt(true)} className="text-[10px] text-violet-300 hover:text-violet-200">Edit inline</button>}</div>{editingPrompt ? <PromptEditor initialPrompt={prompt} onSave={savePrompt} onCancel={() => setEditingPrompt(false)} saving={saving} /> : <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3"><pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-5 text-slate-400">{prompt || "No prompt yet. Edit to add the six-section H3 prompt."}</pre></div>}</div>
        <div className="space-y-2"><label htmlFor="continuity" className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Continuity context</label><textarea id="continuity" value={continuity} onChange={(event) => setContinuity(event.target.value)} rows={2} placeholder="Wardrobe, screen direction, props, or emotional state…" className={`${inputClass} resize-none text-xs`} /></div>
        <ReferenceImages references={references} onAdd={(reference) => setReferences((current) => [...current, reference])} onRemove={(id) => setReferences((current) => current.filter((reference) => reference.id !== id))} />
        <div className="space-y-2"><label htmlFor="frame-grid" className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Preview frame grid</label><select id="frame-grid" value={frameGrid} onChange={(event) => setFrameGrid(Number(event.target.value) as (typeof H3_FRAME_GRID)[number])} className={inputClass}>{H3_FRAME_GRID.map((value) => <option key={value} value={value}>{value} frames</option>)}</select><p className="text-[10px] text-slate-600">Exact H3 values only. WRITE uses Turbo preview at 4 steps / 480p.</p></div>
        {actionError && <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 p-3" role="alert"><p className="text-xs text-amber-200">{actionError.message}</p>{actionError.requestId && <p className="mt-1 font-mono text-[10px] text-amber-300/70">Request ID: {actionError.requestId}</p>}</div>}
        <button onClick={() => void regenerate()} disabled={regenerating || saving} className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 px-3 py-2.5 text-xs font-semibold text-white hover:bg-violet-500 disabled:opacity-50">{regenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}{regenerating ? "Queueing preview…" : "Regenerate preview"}</button>
        <p className="text-center text-[10px] text-slate-600">Preview only. Full-quality rendering and final generation controls belong in MAKE.</p>
        <div className="grid grid-cols-3 gap-2 border-t border-slate-800 pt-4 text-[10px]"><div><span className="block text-slate-600">Job</span><span className="mt-1 block truncate font-mono text-slate-400">{shot.job_id || "—"}</span></div><div><span className="block text-slate-600">Model</span><span className="mt-1 block truncate text-slate-400">{String(shot.generation_params?.model_id || "Turbo")}</span></div><div><span className="block text-slate-600">Seed</span><span className="mt-1 block truncate font-mono text-slate-400">{String(shot.generation_params?.seed || "new on retry")}</span></div></div>
      </div>
    </aside>
  );
}
