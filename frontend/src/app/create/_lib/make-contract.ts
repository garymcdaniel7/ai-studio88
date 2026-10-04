export const FRAME_GRID_VALUES = [124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600] as const;

export type FrameGrid = (typeof FRAME_GRID_VALUES)[number];
export type ShotTemplate = "Dialogue" | "Action" | "Establishing" | "Reaction";
export type QualityPreset = "quick" | "full";
export type SeedMode = "random" | "lock" | "manual";

export interface PromptSections {
  subject: string;
  action: string;
  camera: string;
  lighting: string;
  sound: string;
}

export interface WorkshopControls {
  model: string;
  checkpoint: string;
  workflow: string;
  cfg: number;
  steps: number;
  sampler: string;
  scheduler: string;
  seedMode: SeedMode;
  seed: number;
  aspectRatio: string;
  negativePrompt: string;
  denoise: number;
  batchSize: number;
  clipSkip: number;
  vae: string;
  precision: string;
  loras: string;
  controlNet: string;
  shotSequence: number;
  motion: string;
  characterLock: boolean;
  styleLock: boolean;
  variations: number;
  upscale: boolean;
  quality: QualityPreset;
  frameGrid: FrameGrid;
}

export const SHOT_TEMPLATES: Record<ShotTemplate, PromptSections> = {
  Dialogue: {
    subject: "A consistent character in a conversational close-up",
    action: "speaks with clear expressive eyes and natural gestures",
    camera: "medium close-up, eye-level, shallow depth of field",
    lighting: "soft key light with a controlled rim light",
    sound: "clean dialogue, subtle room tone",
  },
  Action: {
    subject: "A consistent character in a dynamic environment",
    action: "moves decisively through the scene with readable momentum",
    camera: "tracking wide shot with controlled motion blur",
    lighting: "directional contrast with practical highlights",
    sound: "rhythmic movement, grounded impacts, cinematic atmosphere",
  },
  Establishing: {
    subject: "A richly detailed location that establishes the scene",
    action: "holds a clear visual story beat with natural environmental motion",
    camera: "wide establishing shot, deliberate composition, deep focus",
    lighting: "motivated time-of-day light with atmospheric depth",
    sound: "environmental ambience and distant world detail",
  },
  Reaction: {
    subject: "A consistent character reacting in a believable close-up",
    action: "responds with a restrained, readable emotional shift",
    camera: "over-the-shoulder reaction shot, gentle push-in",
    lighting: "soft facial light with subtle background separation",
    sound: "quiet room tone with a precise emotional accent",
  },
};

export const ASPECT_RATIOS: Record<string, { width: number; height: number }> = {
  "16:9": { width: 1024, height: 576 },
  "9:16": { width: 576, height: 1024 },
  "1:1": { width: 1024, height: 1024 },
  "4:3": { width: 1024, height: 768 },
  "21:9": { width: 1344, height: 576 },
};

export const DEFAULT_WORKSHOP_CONTROLS: WorkshopControls = {
  model: "flux-dev",
  checkpoint: "flux-dev",
  workflow: "h3-ref2va",
  cfg: 1,
  steps: 4,
  sampler: "res_multistep",
  scheduler: "simple",
  seedMode: "random",
  seed: 42,
  aspectRatio: "16:9",
  negativePrompt: "plastic skin, waxy face, deformed anatomy, blur, watermark",
  denoise: 1,
  batchSize: 1,
  clipSkip: 1,
  vae: "auto",
  precision: "fp16",
  loras: "",
  controlNet: "none",
  shotSequence: 1,
  motion: "static",
  characterLock: true,
  styleLock: true,
  variations: 1,
  upscale: false,
  quality: "quick",
  frameGrid: 124,
};

export function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Number.isFinite(value) ? value : min));
}

export function snapFrameGrid(value: number): FrameGrid {
  return FRAME_GRID_VALUES.reduce((closest, candidate) =>
    Math.abs(candidate - value) < Math.abs(closest - value) ? candidate : closest
  ) as FrameGrid;
}

export function assemblePrompt(
  sections: PromptSections,
  toggles: { antiPlastic: boolean; speedVerbs: boolean; frameGrid: boolean },
  frameGrid: FrameGrid,
): string {
  const action = toggles.speedVerbs
    ? sections.action.replace(/\b(is|was|being|with)\b/gi, "").replace(/\s+/g, " ").trim()
    : sections.action;
  const lines = [
    "### Subject",
    sections.subject.trim(),
    "",
    "### Action",
    action.trim(),
    "",
    "### Camera",
    sections.camera.trim(),
    "",
    "### Lighting",
    sections.lighting.trim(),
    "",
    "### Sound",
    sections.sound.trim(),
  ];
  if (toggles.antiPlastic) lines.push("", "### Anti-Plastic", "natural skin texture, authentic material response");
  if (toggles.frameGrid) lines.push("", "### Frame Grid", String(frameGrid));
  return lines.join("\n").trim();
}

export function serializeWorkshopRequest(
  controls: WorkshopControls,
  prompt: string,
  variationCount: number,
): Record<string, unknown> {
  const aspect = ASPECT_RATIOS[controls.aspectRatio] ?? ASPECT_RATIOS["16:9"];
  const seed = controls.seedMode === "random" ? undefined : controls.seed;
  return {
    prompt,
    negative_prompt: controls.negativePrompt,
    model: controls.model,
    checkpoint: controls.checkpoint,
    workflow: controls.workflow,
    variation_count: clampNumber(variationCount, 1, 50),
    width: aspect.width,
    height: aspect.height,
    steps: clampNumber(controls.steps, 1, 150),
    cfg_scale: clampNumber(controls.cfg, 0, 30),
    sampler: controls.sampler,
    scheduler: controls.scheduler,
    seed,
    frame_grid: controls.frameGrid,
    denoise: clampNumber(controls.denoise, 0, 1),
    batch_size: clampNumber(controls.batchSize, 1, 16),
    clip_skip: clampNumber(controls.clipSkip, 1, 12),
    vae: controls.vae,
    precision: controls.precision,
    loras: controls.loras,
    controlnet: controls.controlNet,
    shot_sequence: clampNumber(controls.shotSequence, 1, 100),
    motion: controls.motion,
    character_lock: controls.characterLock,
    style_lock: controls.styleLock,
    upscale: controls.upscale,
    quality: controls.quality,
  };
}

export function estimateWorkshopCost(controls: WorkshopControls, variationCount: number): number {
  const base = controls.model.includes("flux") ? 0.08 : controls.model.includes("sdxl") ? 0.04 : 0.03;
  const qualityMultiplier = controls.quality === "full" ? 2.5 : 1;
  const resolutionMultiplier = controls.quality === "full" ? 1.4 : 1;
  return Number((base * (controls.steps / 4) * qualityMultiplier * resolutionMultiplier * clampNumber(variationCount, 1, 50)).toFixed(4));
}

export function classifyQueueError(message: string): "oom" | "provider-down" | "timeout" | "generic" {
  const normalized = message.toLowerCase();
  if (normalized.includes("out of memory") || normalized.includes("cuda oom") || normalized.includes("oom")) return "oom";
  if (normalized.includes("provider") || normalized.includes("unreachable") || normalized.includes("connection")) return "provider-down";
  if (normalized.includes("timeout") || normalized.includes("timed out")) return "timeout";
  return "generic";
}
