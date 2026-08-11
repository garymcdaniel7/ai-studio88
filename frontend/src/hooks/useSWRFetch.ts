"use client";

/**
 * useSWRFetch — Custom SWR hook wrapping the API client.
 *
 * Provides stale-while-revalidate (30s), background revalidation on focus,
 * request deduplication, and retry with exponential backoff (max 3 attempts).
 *
 * Validates: Requirements R17.1, R17.2, R17.4
 */

import useSWR, { type SWRConfiguration, type SWRResponse, type Key } from "swr";
import { api, ApiError } from "@/lib/api";

// =============================================================================
// Default SWR Configuration
// =============================================================================

/**
 * Base SWR options aligned with R17.1:
 * - dedupingInterval: 30000 (30s stale-while-revalidate)
 * - revalidateOnFocus: true (background revalidation on window focus)
 * - errorRetryCount: 3 (max retry attempts)
 * - onErrorRetry: exponential backoff (1s, 2s, 4s)
 */
const DEFAULT_SWR_OPTIONS: SWRConfiguration = {
  dedupingInterval: 30_000,
  revalidateOnFocus: true,
  revalidateOnReconnect: true,
  errorRetryCount: 3,
  onErrorRetry(error, _key, _config, revalidate, { retryCount }) {
    // Don't retry on auth errors — let the api client handle redirect
    if (error instanceof ApiError) {
      if (error.status === 401 || error.status === 403 || error.status === 404) {
        return;
      }
    }

    // Don't retry beyond max
    if (retryCount >= 3) return;

    // Exponential backoff: 1s, 2s, 4s
    const delay = Math.min(1000 * Math.pow(2, retryCount), 8000);
    setTimeout(() => revalidate({ retryCount }), delay);
  },
};

// =============================================================================
// Generic fetcher using the API client
// =============================================================================

/**
 * Default fetcher that calls api.get with the provided path.
 */
async function apiFetcher<T>(path: string): Promise<T> {
  return api.get<T>(path);
}

// =============================================================================
// Hook: useSWRFetch
// =============================================================================

export interface UseSWRFetchOptions<T> extends Partial<SWRConfiguration<T, ApiError>> {
  /** Skip fetching (useful for conditional fetches). Default: false */
  skip?: boolean;
}

/**
 * Custom SWR hook wrapping the AI Studio API client.
 *
 * @param path - API path to fetch (e.g. "/api/v1/talent")
 * @param options - Optional SWR configuration overrides
 * @returns SWR response with typed data, error, loading states, and mutate
 *
 * @example
 * ```tsx
 * const { data, error, isLoading, mutate } = useSWRFetch<Talent[]>("/api/v1/talent");
 * ```
 */
export function useSWRFetch<T = unknown>(
  path: string | null,
  options?: UseSWRFetchOptions<T>
): SWRResponse<T, ApiError> {
  const { skip, ...swrOptions } = options ?? {};

  // Use null key to skip fetching (SWR convention)
  const key: Key = skip ? null : path;

  return useSWR<T, ApiError>(key, apiFetcher as (key: string) => Promise<T>, {
    ...DEFAULT_SWR_OPTIONS,
    ...swrOptions,
  });
}

/**
 * Hook for fetching with a custom fetcher function.
 * Use when you need POST-based data fetching or custom parameters.
 *
 * @param key - SWR cache key (string or null to skip)
 * @param fetcher - Custom async function returning data
 * @param options - Optional SWR configuration overrides
 *
 * @example
 * ```tsx
 * const { data } = useSWRCustom(
 *   talentId ? `/api/v1/talent/${talentId}/prompt` : null,
 *   () => buildTalentPrompt(talentId!, "test prompt")
 * );
 * ```
 */
export function useSWRCustom<T = unknown>(
  key: Key,
  fetcher: () => Promise<T>,
  options?: Partial<SWRConfiguration<T, ApiError>>
): SWRResponse<T, ApiError> {
  return useSWR<T, ApiError>(key, fetcher, {
    ...DEFAULT_SWR_OPTIONS,
    ...options,
  });
}

export { DEFAULT_SWR_OPTIONS };
