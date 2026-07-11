/**
 * SWR-based data fetching hooks for AI Studio.
 *
 * These hooks cache responses client-side so page navigation is instant
 * (shows cached data immediately, revalidates in the background).
 */

import useSWR from "swr";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

type ApiRecord = Record<string, unknown>;

function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const keys = Object.keys(localStorage);
    const sbKey = keys.find((k) => k.startsWith("sb-") && k.endsWith("-auth-token"));
    if (sbKey) {
      const session = JSON.parse(localStorage.getItem(sbKey) || "{}");
      return session?.access_token || null;
    }
  } catch {}
  return null;
}

async function fetcher<T>(path: string): Promise<T> {
  const token = getAuthToken();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Fetch talent list with SWR caching */
export function useTalent() {
  const { data, error, isLoading, mutate } = useSWR<ApiRecord[]>(
    "/api/v1/talent",
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 5000 }
  );
  return { talent: data || [], error, isLoading, mutate };
}

/** Fetch assets list with SWR caching */
export function useAssets() {
  const { data, error, isLoading, mutate } = useSWR<ApiRecord[]>(
    "/api/v1/assets",
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 5000 }
  );
  return { assets: data || [], error, isLoading, mutate };
}

/** Fetch jobs list with SWR caching */
export function useJobs(status?: string) {
  const params = status ? `?status=${status}` : "";
  const { data, error, isLoading, mutate } = useSWR<ApiRecord[]>(
    `/api/v1/jobs${params}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 3000 }
  );
  return { jobs: data || [], error, isLoading, mutate };
}

/** Fetch infrastructure status with SWR caching */
export function useInfrastructureStatus() {
  const { data, error, isLoading, mutate } = useSWR<ApiRecord>(
    "/api/v1/infrastructure/status",
    fetcher,
    { refreshInterval: 10000, dedupingInterval: 5000 }
  );
  return { status: data, error, isLoading, mutate };
}

/** Fetch registered models with SWR caching */
export function useModels(params?: { type?: string; family?: string }) {
  const searchParams = new URLSearchParams();
  if (params?.type) searchParams.set("type", params.type);
  if (params?.family) searchParams.set("family", params.family);
  const qs = searchParams.toString();
  const key = `/api/v1/models${qs ? `?${qs}` : ""}`;

  const { data, error, isLoading, mutate } = useSWR<ApiRecord[]>(
    key,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 5000 }
  );
  return { models: data || [], error, isLoading, mutate };
}

/** Fetch brain health with SWR caching + auto refresh */
export function useBrainHealth() {
  const { data, error } = useSWR<ApiRecord>(
    "/api/v1/brain/health",
    fetcher,
    { refreshInterval: 10000, dedupingInterval: 5000 }
  );
  return { health: data, connected: Boolean(data?.connected), error };
}

/** Fetch cost summary with SWR caching */
export function useCostSummary() {
  const { data, error, isLoading, mutate } = useSWR<ApiRecord>(
    "/api/v1/infrastructure/cost",
    fetcher,
    { refreshInterval: 30000, dedupingInterval: 10000 }
  );
  return { cost: data, error, isLoading, mutate };
}
