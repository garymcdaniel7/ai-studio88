/**
 * AI Studio API Client
 *
 * Centralized API communication with the FastAPI backend.
 * Handles errors, loading states, and base URL configuration.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
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
  return request<any>("/api/v1/infrastructure/status");
}

export async function getServiceConnections() {
  return request<any>("/api/v1/infrastructure/admin/services");
}

export async function getCostSummary() {
  return request<any>("/api/v1/infrastructure/cost");
}

export async function getFleetStatus() {
  return request<any>("/api/v1/infrastructure/fleet");
}

export async function launchWorker(params: {
  max_price?: number;
  min_vram_gb?: number;
  num_candidates?: number;
}) {
  return request<any>("/api/v1/infrastructure/launch", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function stopWorker() {
  return request<any>("/api/v1/infrastructure/stop", { method: "POST" });
}

export async function pauseWorker() {
  return request<any>("/api/v1/infrastructure/pause", { method: "POST" });
}

export async function resumeWorker() {
  return request<any>("/api/v1/infrastructure/resume", { method: "POST" });
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

// =============================================================================
// Talent
// =============================================================================

export async function getTalent() {
  return request<any[]>("/talent");
}

export async function createTalent(data: any) {
  return request<any>("/talent", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// =============================================================================
// Assets
// =============================================================================

export async function getAssets() {
  return request<any[]>("/api/v1/assets");
}

// =============================================================================
// Jobs
// =============================================================================

export async function getJobs(status?: string) {
  const params = status ? `?status=${status}` : "";
  return request<any[]>(`/api/v1/jobs${params}`);
}

// =============================================================================
// Generation
// =============================================================================

export async function getAvailableModels() {
  return request<any[]>("/api/v1/generation/available-models");
}

export async function getProvidersHealth() {
  return request<any[]>("/api/v1/providers/health");
}

// =============================================================================
// Video
// =============================================================================

export async function getVideoProviders() {
  return request<any>("/api/v1/video/providers");
}

// =============================================================================
// Publishing
// =============================================================================

export async function getPublishingPosts() {
  return request<any[]>("/api/v1/publishing/posts");
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
  return request<any>("/api/v1/brain/chat", {
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
  return request<any>("/api/v1/brain/health");
}

export async function getBrainSessions() {
  return request<any[]>("/api/v1/brain/sessions");
}
