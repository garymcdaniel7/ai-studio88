/**
 * AI Studio API Client
 *
 * Centralized API communication with the FastAPI backend.
 * Handles errors, loading states, and base URL configuration.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Build-time check: this logs during next build to verify env var is set
if (typeof window === "undefined") {
  console.log("[BUILD] NEXT_PUBLIC_API_URL =", process.env.NEXT_PUBLIC_API_URL || "(not set - using localhost)");
}

/** Generic record type for dynamic API responses */
type ApiRecord = Record<string, unknown>;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    // Supabase stores session in localStorage
    const keys = Object.keys(localStorage);
    const sbKey = keys.find((k) => k.startsWith("sb-") && k.endsWith("-auth-token"));
    if (sbKey) {
      const session = JSON.parse(localStorage.getItem(sbKey) || "{}");
      return session?.access_token || null;
    }
  } catch {}
  return null;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const token = getAuthToken();
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options?.headers,
      },
    });

    if (!res.ok) {
      const body = await res.text();
      throw new ApiError(body || `HTTP ${res.status}`, res.status);
    }

    return res.json();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Network error: ${(err as Error).message}`, 0);
  }
}

// =============================================================================
// Infrastructure
// =============================================================================

export async function getInfrastructureStatus() {
  return request<ApiRecord>("/api/v1/infrastructure/status");
}

export async function getServiceConnections() {
  return request<ApiRecord>("/api/v1/infrastructure/admin/services");
}

export async function getCostSummary() {
  return request<ApiRecord>("/api/v1/infrastructure/cost");
}

export async function getFleetStatus() {
  return request<ApiRecord>("/api/v1/infrastructure/fleet");
}

export async function launchWorker(params: {
  max_price?: number;
  min_vram_gb?: number;
  num_candidates?: number;
}) {
  return request<ApiRecord>("/api/v1/infrastructure/launch", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function stopWorker() {
  return request<ApiRecord>("/api/v1/infrastructure/stop", { method: "POST" });
}

export async function pauseWorker() {
  return request<ApiRecord>("/api/v1/infrastructure/pause", { method: "POST" });
}

export async function resumeWorker() {
  return request<ApiRecord>("/api/v1/infrastructure/resume", { method: "POST" });
}

export async function getVastStatus() {
  return request<{
    api_connected: boolean;
    instance_active: boolean;
    instance_paused: boolean;
    balance: number;
    instance_info: {
      id: number;
      gpu_name: string;
      price_per_hour: number;
      status: string;
    } | null;
    error?: string;
  }>("/api/v1/infrastructure/vast/status");
}

export async function getRunPodStatus() {
  return request<{
    provider: string;
    api_connected: boolean;
    instance_active: boolean;
    instance_paused: boolean;
    balance: number;
    spend_per_hr?: number;
    instance_info: {
      id: string;
      gpu_name: string;
      price_per_hour: number;
      status: string;
      name?: string;
    } | null;
    total_pods?: number;
    active_pods?: number;
    paused_pods?: number;
    error?: string;
  }>("/api/v1/infrastructure/runpod/status");
}

export async function getGpuProviders() {
  return request<{
    providers: {
      vast: Record<string, unknown>;
      runpod: Record<string, unknown>;
    };
    summary: {
      any_active: boolean;
      any_paused: boolean;
      any_connected: boolean;
      total_balance: number;
      active_provider: string | null;
    };
  }>("/api/v1/infrastructure/gpu/providers");
}

// =============================================================================
// Talent
// =============================================================================

export async function getTalent() {
  return request<ApiRecord[]>("/talent");
}

export async function createTalent(data: ApiRecord) {
  return request<ApiRecord>("/talent", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteTalent(talentId: string) {
  return request<{ deleted: boolean; id: string }>(`/api/v1/talent/${talentId}`, {
    method: "DELETE",
  });
}

export async function updateTalent(talentId: string, data: Record<string, unknown>) {
  return request<ApiRecord>(`/api/v1/talent/${talentId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function buildTalentPrompt(talentId: string, prompt: string) {
  return request<{
    enriched_prompt: string;
    negative_prompt: string;
    talent_name: string;
    dna_injected: boolean;
    dna_components: string[];
  }>(`/api/v1/talent/${talentId}/build-prompt`, {
    method: "POST",
    body: JSON.stringify({ prompt, include_negative: true }),
  });
}

// =============================================================================
// Storyboards
// =============================================================================

export async function getStoryboards() {
  return request<ApiRecord[]>("/api/v1/storyboards");
}

export async function createStoryboard(data: { name: string; description?: string; shots?: unknown[] }) {
  return request<ApiRecord>("/api/v1/storyboards", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getStoryboard(id: string) {
  return request<ApiRecord>(`/api/v1/storyboards/${id}`);
}

export async function updateStoryboard(id: string, data: Record<string, unknown>) {
  return request<ApiRecord>(`/api/v1/storyboards/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteStoryboard(id: string) {
  return request<{ deleted: boolean }>(`/api/v1/storyboards/${id}`, {
    method: "DELETE",
  });
}

// =============================================================================
// Assets
// =============================================================================

export async function getAssets() {
  return request<ApiRecord[]>("/api/v1/assets");
}

// =============================================================================
// Jobs
// =============================================================================

export async function getJobs(status?: string) {
  const params = status ? `?status=${status}` : "";
  return request<ApiRecord[]>(`/api/v1/jobs${params}`);
}

// =============================================================================
// Generation
// =============================================================================

export async function getAvailableModels() {
  return request<ApiRecord[]>("/api/v1/generation/available-models");
}

export async function getRegisteredModels(params?: {
  type?: string;
  family?: string;
  status?: string;
}) {
  const searchParams = new URLSearchParams();
  if (params?.type) searchParams.set("type", params.type);
  if (params?.family) searchParams.set("family", params.family);
  if (params?.status) searchParams.set("status", params.status);
  const qs = searchParams.toString();
  return request<ApiRecord[]>(`/api/v1/models${qs ? `?${qs}` : ""}`);
}

export interface ModelUploadResponse {
  model: Record<string, unknown>;
  asset: Record<string, unknown>;
  lora_version: Record<string, unknown> | null;
  comfyui_path: string;
  size_mb: number;
  upload_status: string;
}

export async function uploadModel(
  file: File,
  params: {
    name?: string;
    model_type?: string;
    family?: string;
    trigger_words?: string;
    base_model?: string;
    recommended_strength?: number;
    talent_id?: string;
    project_id?: string;
  },
  onProgress?: (pct: number) => void,
): Promise<ModelUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (params.name) formData.append("name", params.name);
  if (params.model_type) formData.append("model_type", params.model_type);
  if (params.family) formData.append("family", params.family);
  if (params.trigger_words) formData.append("trigger_words", params.trigger_words);
  if (params.base_model) formData.append("base_model", params.base_model);
  if (params.recommended_strength != null)
    formData.append("recommended_strength", String(params.recommended_strength));
  if (params.talent_id) formData.append("talent_id", params.talent_id);
  if (params.project_id) formData.append("project_id", params.project_id);

  const url = `${API_BASE}/api/v1/models/upload`;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new ApiError(xhr.responseText || `HTTP ${xhr.status}`, xhr.status));
      }
    };

    xhr.onerror = () => reject(new ApiError("Network error during upload", 0));
    xhr.send(formData);
  });
}

export async function deleteModel(modelId: string) {
  return request<{ deleted: boolean }>(`/api/v1/models/${modelId}`, {
    method: "DELETE",
  });
}

export async function hardDeleteModel(modelId: string) {
  return request<{ deleted: boolean; mode: string; message: string }>(`/api/v1/models/${modelId}/permanent`, {
    method: "DELETE",
  });
}

export async function getProvidersHealth() {
  return request<ApiRecord[]>("/api/v1/providers/health");
}

// =============================================================================
// Video
// =============================================================================

export async function getVideoProviders() {
  return request<ApiRecord>("/api/v1/video/providers");
}

// =============================================================================
// Publishing
// =============================================================================

export async function getPublishingPosts() {
  return request<ApiRecord[]>("/api/v1/publishing/posts");
}

// =============================================================================
// Health
// =============================================================================

export async function checkHealth() {
  return request<{ status: string }>("/");
}

// =============================================================================
// Direct Generation (ComfyUI)
// =============================================================================

export async function generateImage(params: {
  prompt: string;
  negative_prompt?: string;
  model?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg?: number;
  seed?: number;
  guidance?: number;
}) {
  return request<{
    success: boolean;
    image_base64: string;
    filename: string;
    generation_time: number;
    model: string;
    prompt: string;
    seed: number;
  }>("/api/v1/generate/image", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// =============================================================================
// Brain (LLM Chat)
// =============================================================================

export async function brainChat(message: string, sessionId?: string) {
  return request<ApiRecord>("/api/v1/brain/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId }),
  });
}

export async function brainLLMChat(messages: Array<{ role: string; content: string }>) {
  return request<{ response: string; model: string }>("/api/v1/brain/llm/chat", {
    method: "POST",
    body: JSON.stringify({ messages }),
  });
}

export async function getBrainHealth() {
  return request<ApiRecord>("/api/v1/brain/health");
}

export async function getBrainSessions() {
  return request<ApiRecord[]>("/api/v1/brain/sessions");
}
