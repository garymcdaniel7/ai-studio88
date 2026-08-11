/**
 * Page State — Story 141
 *
 * Truthful page-state vocabulary and hook for consistent data display.
 * Every page should present one of these documented states — never a blank
 * area or misleading spinner when data is actually failed/stale/offline.
 *
 * State priority (highest wins when multiple conditions apply):
 *   offline > unauthorized > terminal > error > retrying > stale >
 *   partial > loading > refreshing > filtered-empty > empty > ready
 *
 * Integrates with:
 * - health-store.ts (Story 118) for staleness/capability awareness
 * - notification-store.ts (Story 140) for recovery action toasts
 */

// =============================================================================
// State Vocabulary
// =============================================================================

/**
 * All possible page data states, ordered by severity.
 */
export type PageDataState =
  | "loading"        // Initial load — no data yet, first fetch in progress
  | "refreshing"     // Background refresh — showing last-known data, fetch in progress
  | "ready"          // Data loaded successfully, fresh
  | "empty"          // Fetch succeeded but returned zero results (no filter active)
  | "filtered-empty" // Fetch succeeded but active filters yield zero results
  | "stale"          // Showing last-known data that exceeds freshness threshold
  | "partial"        // Some panels/sections loaded, others failed
  | "error"          // Fetch failed, no usable data to show
  | "retrying"       // Fetch failed, automatic retry in progress
  | "offline"        // Browser is offline (navigator.onLine === false)
  | "unauthorized"   // 401/403 — session expired or insufficient permissions
  | "terminal";      // Unrecoverable failure — manual intervention required

/**
 * Typed error with enough context for UI decisions.
 */
export interface PageError {
  /** HTTP status code if available */
  status?: number;
  /** Machine-readable error code */
  code?: string;
  /** Human-readable message for display */
  message: string;
  /** Whether automatic retry is safe for this error */
  retryable: boolean;
  /** When the error occurred */
  timestamp: number;
}

/**
 * Describes what data is available and how fresh it is.
 */
export interface DataFreshness {
  /** When data was last successfully fetched (Unix ms) */
  lastFetched: number;
  /** Freshness threshold in ms — data older than this is "stale" */
  staleAfter: number;
  /** Whether current data exceeds the stale threshold */
  isStale: boolean;
}

/**
 * For partial failures: which sections succeeded and which failed.
 */
export interface SectionStatus {
  key: string;
  label: string;
  state: "ready" | "error" | "loading";
  error?: PageError;
}

// =============================================================================
// Hook Options
// =============================================================================

export interface UsePageStateOptions<T> {
  /** The async function to fetch data */
  fetcher: () => Promise<T>;
  /** How often to auto-refresh (ms). null = no auto-refresh */
  refreshInterval?: number | null;
  /** How long before data is considered stale (ms). Default: 90_000 */
  staleThreshold?: number;
  /** Maximum retry attempts for retryable errors. Default: 3 */
  maxRetries?: number;
  /** Base delay between retries (ms), exponentially backed off. Default: 2000 */
  retryDelay?: number;
  /** Whether to detect empty vs filtered-empty. Default: false */
  hasActiveFilter?: boolean;
  /** Dependencies that trigger a re-fetch (like useEffect deps) */
  deps?: unknown[];
  /** Whether the data represents "no items" when result is empty array/null */
  isEmpty?: (data: T) => boolean;
}

// =============================================================================
// Hook Return
// =============================================================================

export interface PageState<T> {
  /** Current state classification */
  state: PageDataState;
  /** The data (may be last-known if stale/refreshing) */
  data: T | null;
  /** Error details if state is error/retrying/terminal */
  error: PageError | null;
  /** Data freshness information */
  freshness: DataFreshness;
  /** Whether a background fetch is in progress */
  isFetching: boolean;
  /** Whether the browser is offline */
  isOffline: boolean;
  /** Number of consecutive failures */
  failureCount: number;
  /** Retry attempt number (0 = not retrying) */
  retryAttempt: number;
  /** Manually trigger a refresh */
  refresh: () => void;
  /** Manually retry after an error */
  retry: () => void;
}

// =============================================================================
// Constants
// =============================================================================

const DEFAULT_STALE_THRESHOLD = 90_000; // 90 seconds
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_DELAY = 2000;

// =============================================================================
// Helper: classify HTTP errors
// =============================================================================

export function classifyError(err: unknown): PageError {
  const timestamp = Date.now();

  if (err instanceof Response || (err && typeof err === "object" && "status" in err)) {
    const status = (err as { status: number }).status;
    if (status === 401 || status === 403) {
      return { status, code: "UNAUTHORIZED", message: "Session expired or insufficient permissions.", retryable: false, timestamp };
    }
    if (status === 404) {
      return { status, code: "NOT_FOUND", message: "Resource not found.", retryable: false, timestamp };
    }
    if (status === 429) {
      return { status, code: "RATE_LIMITED", message: "Too many requests. Please wait.", retryable: true, timestamp };
    }
    if (status >= 500) {
      return { status, code: "SERVER_ERROR", message: "Server error. Retrying...", retryable: true, timestamp };
    }
    return { status, code: "HTTP_ERROR", message: `Request failed (${status}).`, retryable: status >= 500, timestamp };
  }

  if (err instanceof TypeError && err.message.includes("fetch")) {
    return { code: "NETWORK_ERROR", message: "Network error. Check your connection.", retryable: true, timestamp };
  }

  if (err instanceof Error) {
    // Check for HTTP status in error message (common pattern in this codebase)
    const statusMatch = err.message.match(/HTTP (\d+)/);
    if (statusMatch) {
      const status = parseInt(statusMatch[1], 10);
      if (status === 401 || status === 403) {
        return { status, code: "UNAUTHORIZED", message: "Session expired or insufficient permissions.", retryable: false, timestamp };
      }
      return { status, code: "HTTP_ERROR", message: err.message, retryable: status >= 500, timestamp };
    }
    return { code: "UNKNOWN", message: err.message, retryable: true, timestamp };
  }

  return { code: "UNKNOWN", message: "An unexpected error occurred.", retryable: true, timestamp };
}

// =============================================================================
// Helper: determine composite state
// =============================================================================

export function derivePageState<T>(params: {
  isOffline: boolean;
  error: PageError | null;
  data: T | null;
  isFetching: boolean;
  retryAttempt: number;
  maxRetries: number;
  failureCount: number;
  freshness: DataFreshness;
  hasActiveFilter: boolean;
  isEmpty: (data: T) => boolean;
}): PageDataState {
  const { isOffline, error, data, isFetching, retryAttempt, maxRetries, failureCount, freshness, hasActiveFilter, isEmpty } = params;

  // Offline takes priority
  if (isOffline) return "offline";

  // Unauthorized is non-retryable and requires user action
  if (error && (error.code === "UNAUTHORIZED" || error.status === 401 || error.status === 403)) {
    return "unauthorized";
  }

  // Terminal: exhausted retries with no usable data
  if (error && !error.retryable && data === null) return "terminal";
  if (failureCount >= maxRetries && data === null) return "terminal";

  // Retrying: failed but auto-retry in progress
  if (retryAttempt > 0 && isFetching) return "retrying";

  // Error: failed, no data, not retrying
  if (error && data === null && !isFetching) return "error";

  // Initial loading: no data yet, fetch in progress
  if (data === null && isFetching) return "loading";

  // From here, we have data (possibly stale)

  // Stale: data present but exceeds freshness threshold
  if (freshness.isStale && !isFetching) return "stale";

  // Refreshing: have data, background fetch in progress
  if (data !== null && isFetching) return "refreshing";

  // Empty states (data present but logically empty)
  if (data !== null && isEmpty(data)) {
    return hasActiveFilter ? "filtered-empty" : "empty";
  }

  // Ready: data is fresh and available
  return "ready";
}

// =============================================================================
// Hook: usePageState
// =============================================================================

import { useState, useEffect, useCallback, useRef } from "react";

export function usePageState<T>(options: UsePageStateOptions<T>): PageState<T> {
  const {
    fetcher,
    refreshInterval = null,
    staleThreshold = DEFAULT_STALE_THRESHOLD,
    maxRetries = DEFAULT_MAX_RETRIES,
    retryDelay = DEFAULT_RETRY_DELAY,
    hasActiveFilter = false,
    deps = [],
    isEmpty = (d: T) => Array.isArray(d) ? d.length === 0 : d === null || d === undefined,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<PageError | null>(null);
  const [isFetching, setIsFetching] = useState(false);
  const [lastFetched, setLastFetched] = useState(0);
  const [failureCount, setFailureCount] = useState(0);
  const [retryAttempt, setRetryAttempt] = useState(0);
  const [isOffline, setIsOffline] = useState(
    typeof navigator !== "undefined" ? !navigator.onLine : false
  );

  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // ─── Online/Offline detection ──────────────────────────────────────────

  useEffect(() => {
    function handleOnline() {
      setIsOffline(false);
      // Refresh when coming back online
      doFetch();
    }
    function handleOffline() {
      setIsOffline(true);
    }

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Core fetch ────────────────────────────────────────────────────────

  const doFetch = useCallback(async () => {
    if (!mountedRef.current) return;
    if (isOffline) return; // Don't fetch when offline

    setIsFetching(true);

    try {
      const result = await fetcherRef.current();
      if (!mountedRef.current) return;

      setData(result);
      setError(null);
      setLastFetched(Date.now());
      setFailureCount(0);
      setRetryAttempt(0);
    } catch (err) {
      if (!mountedRef.current) return;

      const classified = classifyError(err);
      setError(classified);
      setFailureCount((prev) => prev + 1);

      // Auto-retry if retryable and under limit
      if (classified.retryable && failureCount < maxRetries - 1) {
        const delay = retryDelay * Math.pow(2, failureCount);
        setRetryAttempt(failureCount + 1);
        retryTimerRef.current = setTimeout(() => {
          if (mountedRef.current) doFetch();
        }, delay);
      }
    } finally {
      if (mountedRef.current) setIsFetching(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOffline, failureCount, maxRetries, retryDelay]);

  // ─── Initial fetch + dep changes ──────────────────────────────────────

  useEffect(() => {
    doFetch();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps]);

  // ─── Auto-refresh interval ────────────────────────────────────────────

  useEffect(() => {
    if (refreshInterval === null || refreshInterval <= 0) return;

    refreshTimerRef.current = setInterval(() => {
      if (mountedRef.current && !isOffline) doFetch();
    }, refreshInterval) as unknown as ReturnType<typeof setTimeout>;

    return () => {
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current as unknown as number);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshInterval, isOffline]);

  // ─── Cleanup ──────────────────────────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current as unknown as number);
    };
  }, []);

  // ─── Derived state ────────────────────────────────────────────────────

  const freshness: DataFreshness = {
    lastFetched,
    staleAfter: staleThreshold,
    // eslint-disable-next-line react-hooks/purity
    isStale: lastFetched > 0 && Date.now() - lastFetched > staleThreshold,
  };

  const state = derivePageState({
    isOffline,
    error,
    data,
    isFetching,
    retryAttempt,
    maxRetries,
    failureCount,
    freshness,
    hasActiveFilter,
    isEmpty,
  });

  // ─── Manual actions ───────────────────────────────────────────────────

  const refresh = useCallback(() => {
    setRetryAttempt(0);
    setFailureCount(0);
    setError(null);
    doFetch();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doFetch]);

  const retryAction = useCallback(() => {
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    setRetryAttempt(0);
    setFailureCount(0);
    setError(null);
    doFetch();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doFetch]);

  return {
    state,
    data,
    error,
    freshness,
    isFetching,
    isOffline,
    failureCount,
    retryAttempt,
    refresh,
    retry: retryAction,
  };
}
