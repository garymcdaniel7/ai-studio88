import { ApiError, api } from "@/lib/api";

export const H3_SECTIONS = [
  "Subject",
  "Action",
  "Camera",
  "Lighting",
  "Sound",
  "Style",
] as const;

export type PromptSection = (typeof H3_SECTIONS)[number];
export type PromptSections = Record<PromptSection, string>;

/** H3 only accepts the published temporal frame values. */
export const H3_FRAME_GRID = [124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600] as const;

export interface Universe {
  id: string;
  name: string;
  description?: string;
  genre?: string;
  created_at?: string;
}

export interface Episode {
  id: string;
  universe_id: string;
  title: string;
  episode_number?: number;
  synopsis?: string;
  description?: string;
  status?: string;
}

export interface Scene {
  id: string;
  episode_id: string;
  scene_number?: number;
  title?: string;
  location?: string;
  time_of_day?: string;
  mood?: string;
  purpose?: string;
  characters?: string[];
}

export interface Shot {
  id: string;
  scene_id: string;
  shot_number?: number;
  description?: string;
  shot_type?: string;
  shot_size?: string;
  camera_movement?: string;
  duration_seconds?: number;
  status?: string;
  asset_id?: string | null;
  job_id?: string | null;
  generation_params?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  thumbnail_url?: string;
  signed_url?: string;
  cdn_url?: string;
}

export interface PreviewGenerationResponse {
  shot_id: string;
  job_id?: string;
  status?: "queued" | "running" | "completed" | "failed" | string;
  asset_id?: string;
  asset?: {
    id?: string;
    signed_url?: string;
    cdn_url?: string;
    thumbnail_url?: string;
  };
  generation_result?: {
    job_id?: string;
    status?: string;
    asset?: PreviewGenerationResponse["asset"];
    workflow_id?: string;
    model_id?: string;
    seed?: number;
    error?: string;
  };
  workflow_id?: string;
  model_id?: string;
  seed?: number;
  error?: string;
}

export interface UploadedReference {
  id: string;
  filename?: string;
  content_type?: string;
  signed_url?: string;
  cdn_url?: string;
  thumbnail_url?: string;
}

export interface ShotPreviewRequest {
  prompt: string;
  negative_prompt: string;
  quality: "preview";
  steps: 4;
  height: 480;
  frame_grid: (typeof H3_FRAME_GRID)[number];
  seed: number;
  previous_shot_id?: string;
  character_ids: string[];
  location?: string;
  continuity: string;
  reference_asset_ids: string[];
  workflow_id?: string;
  model_id?: string;
}

export function emptyPromptSections(): PromptSections {
  return {
    Subject: "",
    Action: "",
    Camera: "",
    Lighting: "",
    Sound: "",
    Style: "",
  };
}

/** Parse the canonical six H3 prompt sections without dropping unknown text. */
export function parseH3Prompt(prompt: string): PromptSections {
  const sections = emptyPromptSections();
  let current: PromptSection | null = null;
  for (const line of prompt.split(/\r?\n/)) {
    const heading = line.match(/^###\s+(.+?)\s*$/)?.[1];
    if (heading && H3_SECTIONS.includes(heading as PromptSection)) {
      current = heading as PromptSection;
      continue;
    }
    if (current) {
      sections[current] = `${sections[current]}${sections[current] ? "\n" : ""}${line}`.trim();
    }
  }
  return sections;
}

/** Serialize prompt sections with stable H3 headings for backend lineage. */
export function serializeH3Prompt(sections: PromptSections): string {
  return H3_SECTIONS.map((section) => `### ${section}\n${sections[section].trim()}`).join("\n\n");
}

export function validateFrameGrid(value: number): value is (typeof H3_FRAME_GRID)[number] {
  return H3_FRAME_GRID.includes(value as (typeof H3_FRAME_GRID)[number]);
}

function list<T>(value: T[] | { items?: T[] } | null | undefined): T[] {
  return Array.isArray(value) ? value : value?.items ?? [];
}

export async function listUniverses(): Promise<Universe[]> {
  return list(await api.get<Universe[] | { items?: Universe[] }>("/api/v1/universes"));
}

export async function listEpisodes(universeId: string): Promise<Episode[]> {
  return list(await api.get<Episode[] | { items?: Episode[] }>(`/api/v1/universes/${universeId}/episodes`));
}

export async function listScenes(episodeId: string): Promise<Scene[]> {
  return list(await api.get<Scene[] | { items?: Scene[] }>(`/api/v1/episodes/${episodeId}/scenes`));
}

export async function listShots(sceneId: string): Promise<Shot[]> {
  return list(await api.get<Shot[] | { items?: Shot[] }>(`/api/v1/scenes/${sceneId}/shots`));
}

/** Uses the existing story mutation contract; the backend remains authoritative. */
export async function updateShot(shotId: string, data: Record<string, unknown>): Promise<Shot> {
  return api.put<Shot>(`/api/v1/shots/${shotId}`, data);
}

export async function generateShotPreview(
  shotId: string,
  request: ShotPreviewRequest,
): Promise<PreviewGenerationResponse> {
  return api.post<PreviewGenerationResponse>(`/api/v1/shots/${shotId}/generate`, request, { timeout: 120_000 });
}

export async function uploadReference(file: File): Promise<UploadedReference> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("tags", "story-reference");
  return api.upload<UploadedReference>("/api/v1/assets", formData, { timeout: 120_000 });
}

export function getApiError(error: unknown): { message: string; requestId: string } {
  if (error instanceof ApiError) {
    return { message: error.detail || error.message, requestId: error.requestId };
  }
  return {
    message: error instanceof Error ? error.message : "Something went wrong. Try again.",
    requestId: "",
  };
}
