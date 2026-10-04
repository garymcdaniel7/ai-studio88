"use client";

import type { Dispatch, SetStateAction } from "react";
import type { WorkshopControls } from "../_lib/make-contract";
import { ASPECT_RATIOS } from "../_lib/make-contract";

interface WorkshopControlsProps {
  controls: WorkshopControls;
  setControls: Dispatch<SetStateAction<WorkshopControls>>;
  modelOptions: { id: string; name: string }[];
  mode: "simple" | "advanced";
}

const inputClass = "mt-1 w-full rounded-lg border border-border-default bg-surface-hover px-3 py-2 text-xs text-content-secondary outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500";
const labelClass = "text-[11px] font-medium text-content-muted";

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className={labelClass}>{label}</span>
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} className={inputClass}>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function RangeField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block">
      <span className={labelClass}>{label}: <strong className="text-content-secondary">{value}</strong></span>
      <input
        aria-label={label}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-2 w-full accent-purple-600"
      />
    </label>
  );
}

export function WorkshopControls({ controls, setControls, modelOptions, mode }: WorkshopControlsProps) {
  const update = <K extends keyof WorkshopControls>(key: K, value: WorkshopControls[K]) => {
    setControls((current) => ({ ...current, [key]: value }));
  };

  function chooseQuality(quality: WorkshopControls["quality"]) {
    if (quality === "quick") {
      setControls((current) => ({ ...current, quality, steps: 4, cfg: 1, sampler: "res_multistep", scheduler: "simple" }));
    } else {
      setControls((current) => ({ ...current, quality, steps: 20, cfg: 1.2, sampler: "res_multistep", scheduler: "simple" }));
    }
  }

  return (
    <div className="space-y-4" data-testid="workshop-controls">
      <section aria-labelledby="tier-one-heading" className="rounded-xl border border-border-subtle bg-surface-raised p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 id="tier-one-heading" className="text-sm font-semibold text-content-primary">Tier 1 · Render controls</h2>
            <p className="text-[11px] text-content-muted">The essentials stay visible in every mode.</p>
          </div>
          <span className="rounded-full bg-purple-500/10 px-2 py-1 text-[10px] text-purple-300">Typed + bounded</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <SelectField label="Model" value={controls.model} options={modelOptions.map((model) => ({ value: model.id, label: model.name }))} onChange={(value) => update("model", value)} />
          <label className="block"><span className={labelClass}>Checkpoint</span><select aria-label="Checkpoint" value={controls.checkpoint} onChange={(event) => update("checkpoint", event.target.value)} className={inputClass}><option value="flux-dev">Flux Dev</option><option value="sdxl-turbo">SDXL Turbo</option><option value="sd15">SD 1.5</option></select></label>
          <label className="block"><span className={labelClass}>Workflow</span><select aria-label="Workflow" value={controls.workflow} onChange={(event) => update("workflow", event.target.value)} className={inputClass}><option value="h3-ref2va">H3 Ref2VA</option><option value="sdxl-turbo">SDXL Turbo</option><option value="flux-dev">Flux Dev</option></select></label>
          <RangeField label="CFG" value={controls.cfg} min={0} max={30} step={0.1} onChange={(value) => update("cfg", value)} />
          <RangeField label="Steps" value={controls.steps} min={1} max={150} step={1} onChange={(value) => update("steps", value)} />
          <SelectField label="Sampler" value={controls.sampler} options={[{ value: "res_multistep", label: "res_multistep" }, { value: "euler", label: "Euler" }, { value: "euler_a", label: "Euler a" }]} onChange={(value) => update("sampler", value)} />
          <SelectField label="Scheduler" value={controls.scheduler} options={[{ value: "simple", label: "simple" }, { value: "normal", label: "normal" }, { value: "karras", label: "karras" }]} onChange={(value) => update("scheduler", value)} />
          <SelectField label="Seed mode" value={controls.seedMode} options={[{ value: "random", label: "Random" }, { value: "lock", label: "Lock current" }, { value: "manual", label: "Manual" }]} onChange={(value) => update("seedMode", value as WorkshopControls["seedMode"])} />
          <label className="block"><span className={labelClass}>Seed</span><input aria-label="Seed" type="number" min={0} max={2147483647} disabled={controls.seedMode === "random"} value={controls.seed} onChange={(event) => update("seed", Math.min(2147483647, Math.max(0, Number(event.target.value))))} className={inputClass} /></label>
          <SelectField label="Aspect ratio" value={controls.aspectRatio} options={Object.keys(ASPECT_RATIOS).map((value) => ({ value, label: value }))} onChange={(value) => update("aspectRatio", value)} />
        </div>
        <label className="mt-3 block"><span className={labelClass}>Negative prompt</span><textarea aria-label="Negative prompt" value={controls.negativePrompt} onChange={(event) => update("negativePrompt", event.target.value.slice(0, 2000))} maxLength={2000} rows={2} className={`${inputClass} font-mono`} /></label>
      </section>

      {mode === "advanced" && (
        <>
          <details open className="rounded-xl border border-border-subtle bg-surface-raised p-4">
            <summary className="cursor-pointer list-none text-sm font-semibold text-content-primary">Tier 2 · Advanced inspector</summary>
            <p className="mt-1 text-[11px] text-content-muted">Schema-style controls, not a node graph.</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <RangeField label="Denoise" value={controls.denoise} min={0} max={1} step={0.01} onChange={(value) => update("denoise", value)} />
              <RangeField label="Batch size" value={controls.batchSize} min={1} max={16} step={1} onChange={(value) => update("batchSize", value)} />
              <RangeField label="CLIP skip" value={controls.clipSkip} min={1} max={12} step={1} onChange={(value) => update("clipSkip", value)} />
              <SelectField label="VAE" value={controls.vae} options={[{ value: "auto", label: "Auto" }, { value: "flux", label: "Flux VAE" }, { value: "sdxl", label: "SDXL VAE" }]} onChange={(value) => update("vae", value)} />
              <SelectField label="Precision" value={controls.precision} options={[{ value: "fp16", label: "FP16" }, { value: "bf16", label: "BF16" }, { value: "fp32", label: "FP32" }]} onChange={(value) => update("precision", value)} />
              <SelectField label="ControlNet" value={controls.controlNet} options={[{ value: "none", label: "None" }, { value: "canny", label: "Canny" }, { value: "depth", label: "Depth" }, { value: "openpose", label: "OpenPose" }]} onChange={(value) => update("controlNet", value)} />
            </div>
            <label className="mt-3 block"><span className={labelClass}>LoRA stack</span><input aria-label="LoRA stack" value={controls.loras} onChange={(event) => update("loras", event.target.value)} placeholder="character:0.8, style:0.6" className={`${inputClass} font-mono`} /></label>
          </details>

          <section aria-labelledby="tier-three-heading" className="rounded-xl border border-border-subtle bg-surface-raised p-4">
            <h2 id="tier-three-heading" className="text-sm font-semibold text-content-primary">Tier 3 · Pipeline</h2>
            <p className="mt-1 text-[11px] text-content-muted">Keep identity, sequence, and quality decisions attributable to the job.</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <RangeField label="Shot sequence" value={controls.shotSequence} min={1} max={100} step={1} onChange={(value) => update("shotSequence", value)} />
              <SelectField label="Motion preset" value={controls.motion} options={[{ value: "static", label: "Static" }, { value: "slow_push", label: "Slow push" }, { value: "tracking", label: "Tracking" }, { value: "orbit", label: "Orbit" }]} onChange={(value) => update("motion", value)} />
              <RangeField label="Batch variations" value={controls.variations} min={1} max={50} step={1} onChange={(value) => update("variations", value)} />
            </div>
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-content-secondary">
              <label className="flex items-center gap-2"><input type="checkbox" checked={controls.characterLock} onChange={(event) => update("characterLock", event.target.checked)} /> Character lock</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={controls.styleLock} onChange={(event) => update("styleLock", event.target.checked)} /> Style lock</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={controls.upscale} onChange={(event) => update("upscale", event.target.checked)} /> Upscale stage</label>
            </div>
          </section>
        </>
      )}

      <section aria-labelledby="quality-heading" className="rounded-xl border border-border-subtle bg-surface-raised p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h2 id="quality-heading" className="text-sm font-semibold text-content-primary">Quality preset</h2><p className="text-[11px] text-content-muted">Quick Preview: 4 steps / CFG 1 / shift 1. Full Quality: 20 steps / CFG 1.2 / shift 10.</p></div>
          <div className="flex rounded-lg border border-border-default p-1" role="group" aria-label="Quality preset">
            <button type="button" aria-pressed={controls.quality === "quick"} onClick={() => chooseQuality("quick")} className={`rounded-md px-3 py-1.5 text-xs ${controls.quality === "quick" ? "bg-purple-600 text-white" : "text-content-muted"}`}>Quick Preview</button>
            <button type="button" aria-pressed={controls.quality === "full"} onClick={() => chooseQuality("full")} className={`rounded-md px-3 py-1.5 text-xs ${controls.quality === "full" ? "bg-purple-600 text-white" : "text-content-muted"}`}>Full Quality</button>
          </div>
        </div>
      </section>
    </div>
  );
}
