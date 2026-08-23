/**
 * AI Studio — Unified Authenticated API Transport
 *
 * Single approved client for ALL frontend-to-backend communication.
 * Supports: JSON, multipart uploads, streaming, polling, cancellation,
 * correlation IDs, standardized error mapping, and bounded retries.
 *
 * Auth: Obtains tokens via Supabase session (not raw localStorage).
 * Errors: Typed ApiError with status codes and structured error info.
 * Retries: Safe (GET/HEAD/OPTIONS) only, bounded, with backoff.
 * Production: Rejects localhost fallback.
 *
 * Usage:
 *   import { api } from "@/lib/api";
 *   const data = await api.get<Talent[]>("/api/v1/talent");
 *   const result = await api.post("/api/v1/talent", { name: "Nova" });
 */

import { getAccessToken } from "@/lib/supabase";

// =============================================================================
// Base URL Configuration
// =============================================================================

const RAW_API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
const IS_PRODUCTION = process.env.NODE_ENV === "production";

/**
 * Validated API base URL.
 * In production, rejects localhost fallback.
 * In development, defaults to localhost:8000.
 */
function getBaseUrl(): string {
  if (RAW_API_BASE) return RAW_API_BASE.replace(/\/$/, "");

  if (IS_PRODUCTION) {
    console.error(
      "[API] NEXT_PUBLIC_API_URL is not set in production. API calls will fail."
    );
    return "";
  }

  return "http://localhost:8000";
}

const API_BASE = getBaseUrl();

// Re-export for backward compatibility with pages that import API_BASE
export { API_BASE };

// =============================================================================
// Auth-aware fetch helper
// =============================================================================

/**
 * Fetch with the Supabase access token attached.
 *
 * Waits for the session to resolve (so page-load data fetches don't race the
 * auth context) and attaches the Authorization header. Pages that use raw
 * `fetch()` for data loading should use this instead, so requests are
 * org-scoped and don't fall back to the dev-user path.
 */
export async function authFetch(
  input: string,
  init: RequestInit = {}
): Promise<Response> {
  const token = await getAccessToken();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return fetch(input, { ...init, headers });
}

// =============================================================================
// Error Model
// =============================================================================

/**
 * Error codes representing distinct failure categories.
 */
export type ApiErrorCode =
  | "UNAUTHORIZED"       // 401 — session invalid/expired
  | "FORBIDDEN"          // 403 — insufficient permissions
  | "NOT_FOUND"          // 404
  | "VALIDATION"         // 422 — input validation failed
  | "CONFLICT"           // 409
  | "RATE_LIMITED"       // 429 — with optional retry-after
  | "SERVER_ERROR"       // 500+
  | "NETWORK_ERROR"      // Failed to connect
  | "TIMEOUT"            // Request timed out
  | "CANCELLED"          // AbortController cancelled
  | "UNKNOWN";           // Unexpected

export class ApiError extends Error {
  /** HTTP status code (0 for network/timeout/cancel errors) */
  readonly status: number;
  /** Typed error category */
  readonly code: ApiErrorCode;
  /** Server-provided error detail (if any) */
  readonly detail: string;
  /** Correlation ID for support/debugging */
  readonly requestId: string;
  /** Retry-After header value in seconds (for 429) */
  readonly retryAfter?: number;

  constructor(params: {
    message: string;
    status: number;
    code: ApiErrorCode;
    detail?: string;
    requestId?: string;
    retryAfter?: number;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.detail = params.detail || params.message;
    this.requestId = params.requestId || "";
    this.retryAfter = params.retryAfter;
  }
}

function classifyStatus(status: number): ApiErrorCode {
  switch (status) {
    case 401: return "UNAUTHORIZED";
    case 403: return "FORBIDDEN";
    case 404: return "NOT_FOUND";
    case 409: return "CONFLICT";
    case 422: return "VALIDATION";
    case 429: return "RATE_LIMITED";
    default:
      if (status >= 500) return "SERVER_ERROR";
      return "UNKNOWN";
  }
}

// =============================================================================
// Request Configuration
// =============================================================================

interface RequestConfig {
  /** Request timeout in ms (default: 30000) */
  timeout?: number;
  /** AbortSignal for cancellation */
  signal?: AbortSignal;
  /** Additional headers */
  headers?: Record<string, string>;
  /** Skip auth header (for unauthenticated endpoints) */
  noAuth?: boolean;
  /** Custom Content-Type (null = let browser set for FormData) */
  contentType?: string | null;
}

interface UploadConfig extends RequestConfig {
  /** Progress callback (0-100) */
  onProgress?: (percent: number) => void;
}

// =============================================================================
// Retry Configuration
// =============================================================================

const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 1000;
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function shouldRetry(method: string, status: number, attempt: number): boolean {
  if (attempt >= MAX_RETRIES) return false;
  if (!SAFE_METHODS.has(method.toUpperCase())) return false;
  // Retry on server errors and rate limits
  return status >= 500 || status === 429 || status === 0;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// =============================================================================
// Core Transport
// =============================================================================

function generateRequestId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `req_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

async function getAuthHeader(): Promise<Record<string, string>> {
  const token = await getAccessToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

async function executeRequest<T>(
  method: string,
  path: string,
  body?: unknown,
  config: RequestConfig = {}
): Promise<T> {
  const requestId = generateRequestId();
  const url = `${API_BASE}${path}`;
  const timeoutMs = config.timeout ?? 30_000;

  // Build headers
  const headers: Record<string, string> = {
    "X-Request-ID": requestId,
    ...(!config.noAuth ? await getAuthHeader() : {}),
    ...(config.headers || {}),
  };

  // Set Content-Type for JSON bodies (not FormData)
  if (config.contentType !== null && body && !(body instanceof FormData)) {
    headers["Content-Type"] = config.contentType || "application/json";
  }

  // Serialize body
  let serializedBody: BodyInit | undefined;
  if (body instanceof FormData) {
    serializedBody = body;
  } else if (body !== undefined) {
    serializedBody = JSON.stringify(body);
  }

  // Create abort controller for timeout
  const controller = new AbortController();
  const signal = config.signal
    ? combineSignals(config.signal, controller.signal)
    : controller.signal;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let lastError: ApiError | null = null;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      // Wait with exponential backoff before retry
      const retryDelay = RETRY_DELAY_MS * Math.pow(2, attempt - 1);
      await delay(retryDelay);
    }

    try {
      const res = await fetch(url, {
        method,
        headers,
        body: serializedBody,
        signal,
      });

      clearTimeout(timeoutId);

      if (res.ok) {
        // Handle 204 No Content
        if (res.status === 204) return undefined as T;

        const contentType = res.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          return await res.json();
        }
        // Non-JSON success (rare) — return text as T
        return (await res.text()) as T;
      }

      // Error response — parse detail
      let detail = "";
      try {
        const errorBody = await res.text();
        try {
          const parsed = JSON.parse(errorBody);
          detail = parsed.detail || parsed.message || errorBody;
        } catch {
          detail = errorBody;
        }
      } catch {
        detail = `HTTP ${res.status}`;
      }

      const retryAfter = res.headers.get("retry-after");

      lastError = new ApiError({
        message: detail || `HTTP ${res.status}`,
        status: res.status,
        code: classifyStatus(res.status),
        detail,
        requestId,
        retryAfter: retryAfter ? parseInt(retryAfter, 10) : undefined,
      });

      // Handle 401 — redirect to login (don't retry)
      if (res.status === 401) {
        if (typeof window !== "undefined") {
          // Clear session and redirect — don't create a retry loop
          window.location.href = "/login";
        }
        throw lastError;
      }

      // Check if we should retry
      if (!shouldRetry(method, res.status, attempt)) {
        throw lastError;
      }
    } catch (err) {
      clearTimeout(timeoutId);

      if (err instanceof ApiError) {
        lastError = err;
        if (!shouldRetry(method, err.status, attempt)) throw err;
        continue;
      }

      // Handle abort/cancellation
      if (err instanceof DOMException && err.name === "AbortError") {
        const isCancelled = config.signal?.aborted;
        throw new ApiError({
          message: isCancelled ? "Request cancelled" : "Request timeout",
          status: 0,
          code: isCancelled ? "CANCELLED" : "TIMEOUT",
          requestId,
        });
      }

      // Network error
      const networkError = new ApiError({
        message: `Network error: ${(err as Error).message}`,
        status: 0,
        code: "NETWORK_ERROR",
        requestId,
      });

      lastError = networkError;
      if (!shouldRetry(method, 0, attempt)) throw networkError;
    }
  }

  // Exhausted retries
  throw lastError || new ApiError({
    message: "Request failed after retries",
    status: 0,
    code: "UNKNOWN",
    requestId,
  });
}

/**
 * Combine two AbortSignals — aborts if either fires.
 */
function combineSignals(
  userSignal: AbortSignal,
  timeoutSignal: AbortSignal
): AbortSignal {
  const controller = new AbortController();
  const abort = () => controller.abort();
  userSignal.addEventListener("abort", abort);
  timeoutSignal.addEventListener("abort", abort);
  return controller.signal;
}

// =============================================================================
// Upload Transport (XHR for progress reporting)
// =============================================================================

async function executeUpload<T>(
  path: string,
  formData: FormData,
  config: UploadConfig = {}
): Promise<T> {
  const requestId = generateRequestId();
  const url = `${API_BASE}${path}`;
  const authHeaders = config.noAuth ? {} : await getAuthHeader();

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);

    // Set headers
    xhr.setRequestHeader("X-Request-ID", requestId);
    Object.entries(authHeaders).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    if (config.headers) {
      Object.entries(config.headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    }

    // Progress
    if (config.onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && config.onProgress) {
          config.onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
    }

    // Timeout
    if (config.timeout) {
      xhr.timeout = config.timeout;
    }

    // Cancellation
    if (config.signal) {
      config.signal.addEventListener("abort", () => xhr.abort());
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          resolve(xhr.responseText as T);
        }
      } else {
        let detail = xhr.responseText;
        try {
          const parsed = JSON.parse(xhr.responseText);
          detail = parsed.detail || parsed.message || detail;
        } catch {}
        reject(new ApiError({
          message: detail || `HTTP ${xhr.status}`,
          status: xhr.status,
          code: classifyStatus(xhr.status),
          detail,
          requestId,
        }));
      }
    };

    xhr.onerror = () =>
      reject(new ApiError({
        message: "Network error during upload",
        status: 0,
        code: "NETWORK_ERROR",
        requestId,
      }));

    xhr.ontimeout = () =>
      reject(new ApiError({
        message: "Upload timed out",
        status: 0,
        code: "TIMEOUT",
        requestId,
      }));

    xhr.onabort = () =>
      reject(new ApiError({
        message: "Upload cancelled",
        status: 0,
        code: "CANCELLED",
        requestId,
      }));

    xhr.send(formData);
  });
}

// =============================================================================
// Public API Object
// =============================================================================

/**
 * The unified API client. Use this for ALL backend communication.
 *
 * Methods:
 *   api.get<T>(path, config?)     — GET with typed response
 *   api.post<T>(path, body?, config?) — POST
 *   api.put<T>(path, body?, config?)  — PUT
 *   api.patch<T>(path, body?, config?) — PATCH
 *   api.delete<T>(path, config?)  — DELETE
 *   api.upload<T>(path, formData, config?) — Multipart upload with progress
 *   api.stream(path, body?, config?) — Returns raw Response for streaming
 */
export const api = {
  get<T>(path: string, config?: RequestConfig): Promise<T> {
    return executeRequest<T>("GET", path, undefined, config);
  },

  post<T>(path: string, body?: unknown, config?: RequestConfig): Promise<T> {
    return executeRequest<T>("POST", path, body, config);
  },

  put<T>(path: string, body?: unknown, config?: RequestConfig): Promise<T> {
    return executeRequest<T>("PUT", path, body, config);
  },

  patch<T>(path: string, body?: unknown, config?: RequestConfig): Promise<T> {
    return executeRequest<T>("PATCH", path, body, config);
  },

  delete<T>(path: string, config?: RequestConfig): Promise<T> {
    return executeRequest<T>("DELETE", path, undefined, config);
  },

  upload<T>(path: string, formData: FormData, config?: UploadConfig): Promise<T> {
    return executeUpload<T>(path, formData, config);
  },

  /**
   * Stream endpoint — returns raw Response for SSE/streaming.
   * Caller is responsible for reading the body.
   */
  async stream(
    path: string,
    body?: unknown,
    config?: RequestConfig
  ): Promise<Response> {
    const requestId = generateRequestId();
    const url = `${API_BASE}${path}`;
    const authHeaders = config?.noAuth ? {} : await getAuthHeader();

    const res = await fetch(url, {
      method: body ? "POST" : "GET",
      headers: {
        "X-Request-ID": requestId,
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...authHeaders,
        ...(config?.headers || {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: config?.signal,
    });

    if (!res.ok) {
      const detail = await res.text().catch(() => `HTTP ${res.status}`);
      throw new ApiError({
        message: detail,
        status: res.status,
        code: classifyStatus(res.status),
        detail,
        requestId,
      });
    }

    return res;
  },
};

// =============================================================================
// Backward-Compatible Endpoint Wrappers
// =============================================================================
// These preserve the existing API surface that pages already import.
// They now route through the unified transport.

/** Generic record type for dynamic API responses */
type ApiRecord = Record<string, unknown>;

// ── Infrastructure ──────────────────────────────────────────────────────────

export async function getInfrastructureStatus() {
  return api.get<ApiRecord>("/api/v1/infrastructure/status");
}

export async function getServiceConnections() {
  return api.get<ApiRecord>("/api/v1/infrastructure/admin/services");
}

export async function getCostSummary() {
  return api.get<ApiRecord>("/api/v1/infrastructure/cost");
}

export async function getFleetStatus() {
  return api.get<ApiRecord>("/api/v1/infrastructure/fleet");
}

export async function launchWorker(params: {
  max_price?: number;
  min_vram_gb?: number;
  num_candidates?: number;
}) {
  return api.post<ApiRecord>("/api/v1/infrastructure/launch", params);
}

export async function stopWorker() {
  return api.post<ApiRecord>("/api/v1/infrastructure/stop");
}

export async function pauseWorker() {
  return api.post<ApiRecord>("/api/v1/infrastructure/pause");
}

export async function resumeWorker() {
  return api.post<ApiRecord>("/api/v1/infrastructure/resume");
}

export async function getVastStatus() {
  return api.get<{
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
  return api.get<{
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
  return api.get<{
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

// ── Talent ──────────────────────────────────────────────────────────────────

export async function getTalent() {
  return api.get<ApiRecord[]>("/api/v1/talent");
}

export async function createTalent(data: ApiRecord) {
  return api.post<ApiRecord>("/api/v1/talent", data);
}

export async function deleteTalent(talentId: string) {
  return api.delete<{ deleted: boolean; id: string }>(`/api/v1/talent/${talentId}`);
}

export async function updateTalent(talentId: string, data: Record<string, unknown>) {
  return api.put<ApiRecord>(`/api/v1/talent/${talentId}`, data);
}

export async function buildTalentPrompt(talentId: string, prompt: string) {
  return api.post<{
    enriched_prompt: string;
    negative_prompt: string;
    talent_name: string;
    dna_injected: boolean;
    dna_components: string[];
  }>(`/api/v1/talent/${talentId}/build-prompt`, { prompt, include_negative: true });
}

// ── Storyboards ─────────────────────────────────────────────────────────────

export async function getStoryboards() {
  return api.get<ApiRecord[]>("/api/v1/storyboards");
}

export async function createStoryboard(data: { name: string; description?: string; shots?: unknown[] }) {
  return api.post<ApiRecord>("/api/v1/storyboards", data);
}

export async function getStoryboard(id: string) {
  return api.get<ApiRecord>(`/api/v1/storyboards/${id}`);
}

export async function updateStoryboard(id: string, data: Record<string, unknown>) {
  return api.put<ApiRecord>(`/api/v1/storyboards/${id}`, data);
}

export async function deleteStoryboard(id: string) {
  return api.delete<{ deleted: boolean }>(`/api/v1/storyboards/${id}`);
}

// ── Assets ──────────────────────────────────────────────────────────────────

export async function getAssets() {
  return api.get<ApiRecord[]>("/api/v1/assets");
}

// ── Jobs ────────────────────────────────────────────────────────────────────

export async function getJobs(status?: string) {
  const params = status ? `?status=${status}` : "";
  return api.get<ApiRecord[]>(`/api/v1/jobs${params}`);
}

// ── Generation ──────────────────────────────────────────────────────────────

export async function getAvailableModels() {
  return api.get<ApiRecord[]>("/api/v1/generation/available-models");
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
  return api.get<ApiRecord[]>(`/api/v1/models${qs ? `?${qs}` : ""}`);
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
  onProgress?: (pct: number) => void
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

  return api.upload<ModelUploadResponse>("/api/v1/models/upload", formData, {
    onProgress,
    timeout: 600_000, // 10 min for large model uploads
  });
}

export async function deleteModel(modelId: string) {
  return api.delete<{ deleted: boolean }>(`/api/v1/models/${modelId}`);
}

export async function hardDeleteModel(modelId: string) {
  return api.delete<{ deleted: boolean; mode: string; message: string }>(
    `/api/v1/models/${modelId}/permanent`
  );
}

export interface ModelInventory {
  on_gpu: { count: number; models: ApiRecord[] };
  b2_only: { count: number; models: ApiRecord[] };
  archived: { count: number; models: ApiRecord[] };
  total_active: number;
  total_size_gb: number;
}

export async function getModelInventory() {
  return api.get<ModelInventory>("/api/v1/models/inventory");
}

export async function getProvidersHealth() {
  return api.get<ApiRecord[]>("/api/v1/providers/health");
}

// ── Video ───────────────────────────────────────────────────────────────────

export async function getVideoProviders() {
  return api.get<ApiRecord>("/api/v1/video/providers");
}

// ── Publishing ──────────────────────────────────────────────────────────────

export async function getPublishingPosts() {
  return api.get<ApiRecord[]>("/api/v1/publishing/posts");
}

// ── Health ──────────────────────────────────────────────────────────────────

export async function checkHealth() {
  return api.get<{ status: string }>("/", { noAuth: true });
}

// ── Generation (Direct ComfyUI) ─────────────────────────────────────────────

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
  return api.post<{
    success: boolean;
    image_base64: string;
    filename: string;
    generation_time: number;
    model: string;
    prompt: string;
    seed: number;
  }>("/api/v1/generate/image", params, { timeout: 120_000 });
}

// ── Brain (LLM Chat) ────────────────────────────────────────────────────────

export async function brainChat(message: string, sessionId?: string) {
  return api.post<ApiRecord>("/api/v1/brain/chat", {
    message,
    session_id: sessionId,
  });
}

export async function brainLLMChat(messages: Array<{ role: string; content: string }>) {
  return api.post<{ response: string; model: string }>("/api/v1/brain/llm/chat", {
    messages,
  });
}

export async function getBrainHealth() {
  return api.get<ApiRecord>("/api/v1/brain/health");
}

export async function getBrainSessions() {
  return api.get<ApiRecord[]>("/api/v1/brain/sessions");
}
