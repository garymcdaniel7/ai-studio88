import { ApiError, type ApiErrorCode } from "@/lib/api";

export interface StartProjectSummary {
  id: string;
  name: string;
  description?: string;
  status: string;
  category?: string;
  color?: string;
  asset_count?: number;
  generation_count?: number;
  created_at?: string;
}

export interface StartProjectsResponse {
  projects?: StartProjectSummary[];
}

export interface StartRequestError {
  code: ApiErrorCode | "UNKNOWN";
  detail: string;
  message: string;
  requestId: string;
  retryable: boolean;
  status: number;
}

export type StartViewState = "loading" | "error" | "empty" | "ready";

export function normalizeStartProjects(
  response: StartProjectsResponse | StartProjectSummary[],
): StartProjectSummary[] {
  return Array.isArray(response) ? response : response.projects ?? [];
}

export function getStartViewState(input: {
  isLoading: boolean;
  error: StartRequestError | null;
  projects: StartProjectSummary[];
}): StartViewState {
  if (input.isLoading && input.projects.length === 0) return "loading";
  if (input.error && input.projects.length === 0) return "error";
  if (input.projects.filter((project) => project.status === "active").length === 0) return "empty";
  return "ready";
}

export function toStartRequestError(error: unknown): StartRequestError {
  if (error instanceof ApiError) {
    return {
      code: error.code,
      detail: error.detail,
      message: error.message,
      requestId: error.requestId || "unavailable",
      retryable: ["NETWORK_ERROR", "TIMEOUT", "RATE_LIMITED", "SERVER_ERROR"].includes(error.code),
      status: error.status,
    };
  }

  const message = error instanceof Error ? error.message : "Unable to load your projects.";
  return {
    code: "UNKNOWN",
    detail: message,
    message: "Unable to load your projects. Please try again.",
    requestId: "unavailable",
    retryable: true,
    status: 0,
  };
}

export function formatProjectDate(value?: string): string {
  if (!value) return "Recently created";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently created";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
