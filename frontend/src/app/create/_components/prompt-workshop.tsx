"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { WorkshopControls } from "./workshop-controls";
import { WorkshopQueue, type WorkshopQueueJob } from "./workshop-queue";
import { ConflictDisplay, type ConflictDisplayState } from "./conflict-display";
import {
  assemblePrompt,
  classifyQueueError,
  DEFAULT_WORKSHOP_CONTROLS,
  estimateWorkshopCost,
  ASPECT_RATIOS,
  FRAME_GRID_VALUES,
  SHOT_TEMPLATES,
  serializeWorkshopRequest,
  type PromptSections,
  type ShotTemplate,
  type WorkshopControls as WorkshopControlsState,
} from "../_lib/make-contract";

const sectionLabels: { key: keyof PromptSections; label: string }[] = [
  { key: "subject", label: "Subject" },
  { key: "action", label: "Action" },
  { key: "camera", label: "Camera" },
  { key: "lighting", label: "Lighting" },
  { key: "sound", label: "Sound" },
];

interface BatchResponse {
  batch_id: string;
  state?: string;
  total_estimated_usd?: number;
  progress_pct?: number;
  variations?: { job_id: string; state: string; asset_id?: string; error_message?: string }[];
}

function toQueueJob(batch: BatchResponse, model: string, fallbackCost: number): WorkshopQueueJob {
  const variations = batch.variations || [];
  const hasFailed = variations.some((item) => item.state === "failed");
  const hasRunning = variations.some((item) => item.state === "executing" || item.state === "running");
  const status: WorkshopQueueJob["status"] = hasFailed || batch.state === "failed" ? "failed" : batch.state === "cancelled" ? "cancelled" : batch.state === "completed" || variations.every((item) => item.state === "completed") ? "completed" : hasRunning || batch.state === "in_progress" ? "running" : "queued";
  const firstError = variations.find((item) => item.error_message)?.error_message;
  return {
    id: batch.batch_id,
    batchId: batch.batch_id,
    status,
    progress: Number(batch.progress_pct || (status === "completed" ? 100 : 0)),
    estimatedCost: Number(batch.total_estimated_usd ?? fallbackCost),
    model,
    error: firstError,
    errorKind: firstError ? classifyQueueError(firstError) : undefined,
    outputs: variations.filter((item) => item.state === "completed").map((item, index) => ({ id: item.job_id || `variation-${index + 1}`, status: "pending", assetId: item.asset_id })),
  };
}

export function PromptWorkshop({ modelOptions }: { modelOptions: { id: string; name: string }[] }) {
  const { status: authStatus } = useAuth();
  const [mode, setMode] = useState<"simple" | "advanced">("simple");
  const [template, setTemplate] = useState<ShotTemplate>("Dialogue");
  const [sections, setSections] = useState<PromptSections>(SHOT_TEMPLATES.Dialogue);
  const [antiPlastic, setAntiPlastic] = useState(true);
  const [speedVerbs, setSpeedVerbs] = useState(false);
  const [includeFrameGrid, setIncludeFrameGrid] = useState(true);
  const [controls, setControls] = useState<WorkshopControlsState>(DEFAULT_WORKSHOP_CONTROLS);
  const [jobs, setJobs] = useState<WorkshopQueueJob[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mergeState, setMergeState] = useState<ConflictDisplayState>({ kind: "idle" });

  const prompt = useMemo(() => assemblePrompt(sections, { antiPlastic, speedVerbs, frameGrid: includeFrameGrid }, controls.frameGrid), [antiPlastic, controls.frameGrid, includeFrameGrid, sections, speedVerbs]);
  const estimatedCost = useMemo(() => estimateWorkshopCost(controls, controls.variations), [controls]);

  useEffect(() => {
    const activeBatchIds = jobs.filter((job) => job.batchId && (job.status === "queued" || job.status === "running")).map((job) => job.batchId as string);
    if (activeBatchIds.length === 0) return undefined;
    const timer = window.setInterval(() => {
      activeBatchIds.forEach((batchId) => {
        api.get<BatchResponse>(`/api/v1/generate/batch/${batchId}`).then((batch) => {
          setJobs((current) => current.map((job) => job.batchId === batchId ? { ...toQueueJob(batch, job.model, job.estimatedCost), id: job.id } : job));
        }).catch(() => { /* Keep the last durable state visible while the provider is unavailable. */ });
      });
    }, 4000);
    return () => window.clearInterval(timer);
  }, [jobs]);

  function updateSection(key: keyof PromptSections, value: string) {
    setSections((current) => ({ ...current, [key]: value }));
  }

  function changeTemplate(nextTemplate: ShotTemplate) {
    setTemplate(nextTemplate);
    setSections(SHOT_TEMPLATES[nextTemplate]);
  }

  async function submitJob(overrides?: Partial<WorkshopControlsState>) {
    const nextControls = { ...controls, ...overrides };
    const nextPrompt = assemblePrompt(sections, { antiPlastic, speedVerbs, frameGrid: includeFrameGrid }, nextControls.frameGrid);
    const nextCost = estimateWorkshopCost(nextControls, nextControls.variations);
    if (!nextPrompt.trim() || !nextCost || !Number.isFinite(nextCost)) {
      setMessage("Add a prompt and wait for a valid cost estimate before dispatching.");
      return;
    }
    // Block dispatch if preset composer found conflicts or hard dependencies
    if (mergeState.kind === "blocked" || mergeState.kind === "conflicts") {
      setMessage("Resolve preset conflicts before dispatching.");
      return;
    }
    setSubmitting(true);
    setMessage("Cost estimate ready. Requesting a backend reservation before dispatch…");
    try {
      const aspect = ASPECT_RATIOS[nextControls.aspectRatio] ?? ASPECT_RATIOS["16:9"];
      const request = serializeWorkshopRequest(nextControls, nextPrompt, nextControls.variations);
      const batch = await api.post<BatchResponse>("/api/v1/generate/batch", { ...request, width: aspect.width, height: aspect.height, idempotency_key: `make-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` });
      const nextJob = toQueueJob(batch, nextControls.model, nextCost);
      setJobs((current) => [nextJob, ...current]);
      setMessage(`Queued ${nextControls.quality === "quick" ? "Quick Preview" : "Full Quality"}. Backend reserved the estimated cost.`);
    } catch (error) {
      const detail = error instanceof ApiError ? error.detail : "The generation provider rejected the request.";
      const failed: WorkshopQueueJob = { id: `local-${Date.now()}`, status: "failed", progress: 0, estimatedCost: nextCost, model: nextControls.model, error: detail, errorKind: classifyQueueError(detail), outputs: [] };
      setJobs((current) => [failed, ...current]);
      setMessage("Dispatch blocked. No render was started without a successful cost-gated request.");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancelJob(job: WorkshopQueueJob) {
    if (!job.batchId) return;
    try {
      await api.post(`/api/v1/generate/batch/${job.batchId}/cancel`);
      setJobs((current) => current.map((item) => item.id === job.id ? { ...item, status: "cancelled", progress: item.progress } : item));
      setMessage("Queued work cancelled. Any completed variations remain available for review.");
    } catch (error) {
      setMessage(error instanceof ApiError ? error.detail : "Unable to cancel this job.");
    }
  }

  async function retryJob(job: WorkshopQueueJob, lowerResolution: boolean) {
    if (lowerResolution || !job.batchId) {
      await submitJob(lowerResolution ? { quality: "quick", aspectRatio: "16:9", steps: 4, cfg: 1 } : undefined);
      return;
    }
    try {
      const batch = await api.post<BatchResponse>(`/api/v1/generate/batch/${job.batchId}/retry`);
      setJobs((current) => current.map((item) => item.id === job.id ? { ...toQueueJob(batch, item.model, item.estimatedCost), id: item.id } : item));
      setMessage("Retry queued through the existing idempotent batch contract.");
    } catch (error) {
      setMessage(error instanceof ApiError ? error.detail : "Unable to retry this job.");
    }
  }

  function reviewOutput(jobId: string, outputId: string, decision: "approved" | "rejected") {
    setJobs((current) => current.map((job) => job.id === jobId ? { ...job, outputs: job.outputs.map((output) => output.id === outputId ? { ...output, status: decision } : output) } : job));
  }

  return (
    <div className="space-y-5" data-testid="prompt-workshop">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><p className="text-xs font-medium uppercase tracking-[0.16em] text-purple-300">MAKE · Generation Studio</p><h2 className="mt-1 text-2xl font-semibold text-content-primary">Prompt Workshop</h2><p className="mt-1 max-w-2xl text-sm text-content-muted">Assemble a production-ready shot, preview every parameter, and send only cost-gated jobs to the existing async generation queue.</p></div>
        <div className="rounded-lg border border-border-default bg-surface-raised px-3 py-2 text-right"><p className="text-[10px] uppercase tracking-wide text-content-muted">Auth state</p><p className="text-xs text-content-secondary">{authStatus === "authenticated" ? "Authenticated workspace" : authStatus === "loading" ? "Checking session…" : "Session required for dispatch"}</p></div>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border-subtle bg-surface-raised p-3" role="tablist" aria-label="Workshop mode">
        <button type="button" role="tab" aria-selected={mode === "simple"} onClick={() => setMode("simple")} className={`rounded-lg px-4 py-2 text-xs ${mode === "simple" ? "bg-purple-600 text-white" : "text-content-muted hover:text-content-secondary"}`}>Simple · 3-step</button>
        <button type="button" role="tab" aria-selected={mode === "advanced"} onClick={() => setMode("advanced")} className={`rounded-lg px-4 py-2 text-xs ${mode === "advanced" ? "bg-purple-600 text-white" : "text-content-muted hover:text-content-secondary"}`}>Advanced · Inspector</button>
        {mode === "simple" && <span className="ml-2 text-[11px] text-content-muted">1. Prompt → 2. Style → 3. Queue render</span>}
      </div>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <div className="space-y-4">
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-semibold text-content-primary">Shot recipe</h2><p className="text-[11px] text-content-muted">Start with a template, then tune each H3 section.</p></div><label className="text-xs text-content-muted">Shot type<select aria-label="Shot type template" value={template} onChange={(event) => changeTemplate(event.target.value as ShotTemplate)} className="ml-2 rounded-lg border border-border-default bg-surface-hover px-2 py-1.5 text-xs text-content-secondary"><option>Dialogue</option><option>Action</option><option>Establishing</option><option>Reaction</option></select></label></div><div className="mt-4 grid gap-3 sm:grid-cols-2">{sectionLabels.map(({ key, label }) => <label key={key} className="block"><span className="text-[11px] font-medium text-content-muted">{label}</span><textarea aria-label={`${label} injector`} value={sections[key]} onChange={(event) => updateSection(key, event.target.value)} rows={2} className="mt-1 w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-xs text-content-secondary outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500" /></label>)}</div><div className="mt-4 flex flex-wrap gap-4 text-xs text-content-secondary"><label className="flex items-center gap-2"><input type="checkbox" checked={antiPlastic} onChange={(event) => setAntiPlastic(event.target.checked)} /> Anti-Plastic</label><label className="flex items-center gap-2"><input type="checkbox" checked={speedVerbs} onChange={(event) => setSpeedVerbs(event.target.checked)} /> Speed Verbs</label><label className="flex items-center gap-2"><input type="checkbox" checked={includeFrameGrid} onChange={(event) => setIncludeFrameGrid(event.target.checked)} /> Frame Grid</label></div></div>
          <div className="rounded-xl border border-border-subtle bg-surface-raised p-4"><div className="flex items-center justify-between"><div><h2 className="text-sm font-semibold text-content-primary">Prompt preview</h2><p className="text-[11px] text-content-muted">This exact assembled prompt is sent with the job request.</p></div><span className="font-mono text-[10px] text-purple-300">H3</span></div><pre data-testid="prompt-preview" className="mt-3 max-h-72 overflow-auto rounded-lg border border-border-default bg-surface-hover p-3 font-mono text-xs leading-5 text-content-secondary">{prompt}</pre></div>
        </div>
        <div className="space-y-4"><WorkshopControls controls={controls} setControls={setControls} modelOptions={modelOptions.length ? modelOptions : [{ id: "flux-dev", name: "Flux Dev" }, { id: "sdxl-turbo", name: "SDXL Turbo" }, { id: "sd15", name: "SD 1.5" }]} mode={mode} /><section className="rounded-xl border border-border-subtle bg-surface-raised p-4"><h2 className="text-sm font-semibold text-content-primary">Frame grid</h2><p className="mt-1 text-[11px] text-content-muted">Only H3-supported values are selectable.</p><select aria-label="Preview frame grid" value={controls.frameGrid} onChange={(event) => setControls((current) => ({ ...current, frameGrid: Number(event.target.value) as WorkshopControlsState["frameGrid"] }))} className="mt-3 w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-xs text-content-secondary">{FRAME_GRID_VALUES.map((value) => <option key={value} value={value}>{value} frames</option>)}</select><div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-3"><span className="text-xs text-content-muted">Backend cost estimate</span><strong className="text-sm text-content-primary">${estimatedCost.toFixed(4)}</strong></div><ConflictDisplay state={mergeState} onDismissWarnings={() => setMergeState({ kind: "success" })} /><button type="button" disabled={submitting || !prompt.trim() || !estimatedCost || authStatus !== "authenticated" || mergeState.kind === "conflicts" || mergeState.kind === "blocked"} onClick={() => void submitJob()} className="mt-3 w-full rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-50">{submitting ? "Requesting reservation…" : mergeState.kind === "blocked" ? "Blocked — missing dependencies" : mergeState.kind === "conflicts" ? "Conflicts need resolution" : "Queue render"}</button><p className="mt-2 text-[10px] text-content-muted">Dispatch requires a valid session and backend reservation. No client-supplied org selector or secret is sent.</p></section></div>
      </section>
      {message && <div role="status" className="rounded-lg border border-purple-500/30 bg-purple-500/10 px-3 py-2 text-xs text-purple-200">{message}</div>}
      <WorkshopQueue jobs={jobs} onCancel={(job) => void cancelJob(job)} onRetry={(job, lowerResolution) => void retryJob(job, lowerResolution)} onReview={reviewOutput} />
    </div>
  );
}
