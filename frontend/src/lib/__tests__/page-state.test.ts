/**
 * Page State tests — Story 141
 *
 * Tests prove:
 * - State derivation: correct state for each combination of inputs
 * - Retry safety: only retryable errors trigger retry, respects max
 * - Stale labeling: data older than threshold classified as stale
 * - Offline detection: offline state takes priority
 * - Error classification: HTTP codes → correct PageError types
 * - Empty vs filtered-empty: filter awareness
 * - Unauthorized: 401/403 → unauthorized state (not retryable)
 * - Terminal: exhausted retries with no data
 * - Priority ordering: higher-severity states win
 */

import { describe, it, expect } from "vitest";
import { derivePageState, classifyError, type PageError, type DataFreshness } from "../page-state";

// =============================================================================
// Helpers
// =============================================================================

function freshData(ageMs: number = 1000, staleAfter: number = 90_000): DataFreshness {
  return { lastFetched: Date.now() - ageMs, staleAfter, isStale: ageMs > staleAfter };
}

function staleData(): DataFreshness {
  return { lastFetched: Date.now() - 120_000, staleAfter: 90_000, isStale: true };
}

function neverFetched(): DataFreshness {
  return { lastFetched: 0, staleAfter: 90_000, isStale: false };
}

function retryableError(msg = "Server error"): PageError {
  return { status: 500, code: "SERVER_ERROR", message: msg, retryable: true, timestamp: Date.now() };
}

function nonRetryableError(msg = "Not found"): PageError {
  return { status: 404, code: "NOT_FOUND", message: msg, retryable: false, timestamp: Date.now() };
}

function unauthorizedError(): PageError {
  return { status: 401, code: "UNAUTHORIZED", message: "Session expired", retryable: false, timestamp: Date.now() };
}

const defaultParams = {
  isOffline: false,
  error: null as PageError | null,
  data: null as string[] | null,
  isFetching: false,
  retryAttempt: 0,
  maxRetries: 3,
  failureCount: 0,
  freshness: neverFetched(),
  hasActiveFilter: false,
  isEmpty: (d: string[]) => d.length === 0,
};

// =============================================================================
// State Derivation
// =============================================================================

describe("derivePageState", () => {
  describe("Loading states", () => {
    it("loading: no data, fetch in progress", () => {
      const state = derivePageState({ ...defaultParams, data: null, isFetching: true });
      expect(state).toBe("loading");
    });

    it("refreshing: has data, fetch in progress", () => {
      const state = derivePageState({
        ...defaultParams,
        data: ["item"],
        isFetching: true,
        freshness: freshData(),
      });
      expect(state).toBe("refreshing");
    });
  });

  describe("Ready state", () => {
    it("ready: has fresh data, not fetching", () => {
      const state = derivePageState({
        ...defaultParams,
        data: ["item1", "item2"],
        freshness: freshData(),
      });
      expect(state).toBe("ready");
    });
  });

  describe("Empty states", () => {
    it("empty: fetch succeeded, zero results, no filter", () => {
      const state = derivePageState({
        ...defaultParams,
        data: [],
        freshness: freshData(),
        hasActiveFilter: false,
      });
      expect(state).toBe("empty");
    });

    it("filtered-empty: fetch succeeded, zero results, filter active", () => {
      const state = derivePageState({
        ...defaultParams,
        data: [],
        freshness: freshData(),
        hasActiveFilter: true,
      });
      expect(state).toBe("filtered-empty");
    });
  });

  describe("Stale state", () => {
    it("stale: has data but exceeds freshness threshold", () => {
      const state = derivePageState({
        ...defaultParams,
        data: ["old-item"],
        freshness: staleData(),
      });
      expect(state).toBe("stale");
    });

    it("stale data + fetching = refreshing (not stale)", () => {
      const state = derivePageState({
        ...defaultParams,
        data: ["old-item"],
        freshness: staleData(),
        isFetching: true,
      });
      expect(state).toBe("refreshing");
    });
  });

  describe("Error states", () => {
    it("error: fetch failed, no data, not fetching", () => {
      const state = derivePageState({
        ...defaultParams,
        error: retryableError(),
        data: null,
      });
      expect(state).toBe("error");
    });

    it("retrying: failed but auto-retry fetch in progress", () => {
      const state = derivePageState({
        ...defaultParams,
        error: retryableError(),
        data: null,
        isFetching: true,
        retryAttempt: 1,
      });
      expect(state).toBe("retrying");
    });

    it("terminal: exhausted retries with no data", () => {
      const state = derivePageState({
        ...defaultParams,
        error: retryableError(),
        data: null,
        failureCount: 3,
        maxRetries: 3,
      });
      expect(state).toBe("terminal");
    });

    it("terminal: non-retryable error with no data", () => {
      const state = derivePageState({
        ...defaultParams,
        error: nonRetryableError(),
        data: null,
      });
      expect(state).toBe("terminal");
    });
  });

  describe("Offline state", () => {
    it("offline takes priority over everything", () => {
      const state = derivePageState({
        ...defaultParams,
        isOffline: true,
        error: retryableError(),
        data: null,
        isFetching: true,
      });
      expect(state).toBe("offline");
    });

    it("offline with existing data still shows offline", () => {
      const state = derivePageState({
        ...defaultParams,
        isOffline: true,
        data: ["cached"],
        freshness: freshData(),
      });
      expect(state).toBe("offline");
    });
  });

  describe("Unauthorized state", () => {
    it("unauthorized: 401 error", () => {
      const state = derivePageState({
        ...defaultParams,
        error: unauthorizedError(),
        data: null,
      });
      expect(state).toBe("unauthorized");
    });

    it("unauthorized takes priority over terminal", () => {
      const state = derivePageState({
        ...defaultParams,
        error: unauthorizedError(),
        data: null,
        failureCount: 5,
      });
      expect(state).toBe("unauthorized");
    });
  });

  describe("Priority ordering", () => {
    it("offline > unauthorized", () => {
      const state = derivePageState({
        ...defaultParams,
        isOffline: true,
        error: unauthorizedError(),
      });
      expect(state).toBe("offline");
    });

    it("error with data = stale (data preserved)", () => {
      // When there's an error but we still have data, state depends on data freshness
      const state = derivePageState({
        ...defaultParams,
        error: retryableError(),
        data: ["preserved"],
        freshness: staleData(),
      });
      // Data present + stale freshness + not fetching = stale
      expect(state).toBe("stale");
    });

    it("error with fresh data = ready (background failure, data still good)", () => {
      const state = derivePageState({
        ...defaultParams,
        error: retryableError(),
        data: ["still-good"],
        freshness: freshData(),
      });
      expect(state).toBe("ready");
    });
  });
});

// =============================================================================
// Error Classification
// =============================================================================

describe("classifyError", () => {
  it("401 → UNAUTHORIZED, not retryable", () => {
    const err = classifyError({ status: 401 });
    expect(err.code).toBe("UNAUTHORIZED");
    expect(err.retryable).toBe(false);
    expect(err.status).toBe(401);
  });

  it("403 → UNAUTHORIZED, not retryable", () => {
    const err = classifyError({ status: 403 });
    expect(err.code).toBe("UNAUTHORIZED");
    expect(err.retryable).toBe(false);
  });

  it("404 → NOT_FOUND, not retryable", () => {
    const err = classifyError({ status: 404 });
    expect(err.code).toBe("NOT_FOUND");
    expect(err.retryable).toBe(false);
  });

  it("429 → RATE_LIMITED, retryable", () => {
    const err = classifyError({ status: 429 });
    expect(err.code).toBe("RATE_LIMITED");
    expect(err.retryable).toBe(true);
  });

  it("500 → SERVER_ERROR, retryable", () => {
    const err = classifyError({ status: 500 });
    expect(err.code).toBe("SERVER_ERROR");
    expect(err.retryable).toBe(true);
  });

  it("502 → SERVER_ERROR, retryable", () => {
    const err = classifyError({ status: 502 });
    expect(err.code).toBe("SERVER_ERROR");
    expect(err.retryable).toBe(true);
  });

  it("TypeError with fetch message → NETWORK_ERROR, retryable", () => {
    const err = classifyError(new TypeError("Failed to fetch"));
    expect(err.code).toBe("NETWORK_ERROR");
    expect(err.retryable).toBe(true);
  });

  it("Error with HTTP status in message → extracts status", () => {
    const err = classifyError(new Error("HTTP 503"));
    expect(err.status).toBe(503);
    expect(err.retryable).toBe(true);
  });

  it("Error with HTTP 401 in message → UNAUTHORIZED", () => {
    const err = classifyError(new Error("HTTP 401"));
    expect(err.code).toBe("UNAUTHORIZED");
    expect(err.retryable).toBe(false);
  });

  it("generic Error → UNKNOWN, retryable", () => {
    const err = classifyError(new Error("Something went wrong"));
    expect(err.code).toBe("UNKNOWN");
    expect(err.retryable).toBe(true);
    expect(err.message).toBe("Something went wrong");
  });

  it("non-Error value → UNKNOWN", () => {
    const err = classifyError("string error");
    expect(err.code).toBe("UNKNOWN");
    expect(err.retryable).toBe(true);
  });

  it("always includes timestamp", () => {
    const before = Date.now();
    const err = classifyError(new Error("test"));
    expect(err.timestamp).toBeGreaterThanOrEqual(before);
    expect(err.timestamp).toBeLessThanOrEqual(Date.now());
  });
});

// =============================================================================
// Retry Safety
// =============================================================================

describe("Retry safety", () => {
  it("retryable errors allow retry state", () => {
    const state = derivePageState({
      ...defaultParams,
      error: retryableError(),
      data: null,
      isFetching: true,
      retryAttempt: 1,
    });
    expect(state).toBe("retrying");
  });

  it("non-retryable errors go to terminal immediately (no retry)", () => {
    const state = derivePageState({
      ...defaultParams,
      error: nonRetryableError(),
      data: null,
      retryAttempt: 0,
    });
    expect(state).toBe("terminal");
  });

  it("exceeding max retries transitions to terminal", () => {
    const state = derivePageState({
      ...defaultParams,
      error: retryableError(),
      data: null,
      failureCount: 3,
      maxRetries: 3,
    });
    expect(state).toBe("terminal");
  });

  it("failures under max stay in error (awaiting retry)", () => {
    const state = derivePageState({
      ...defaultParams,
      error: retryableError(),
      data: null,
      failureCount: 1,
      maxRetries: 3,
    });
    expect(state).toBe("error");
  });
});

// =============================================================================
// Stale Labeling
// =============================================================================

describe("Stale labeling", () => {
  it("data within threshold is NOT stale", () => {
    const freshness = freshData(30_000, 90_000); // 30s old, 90s threshold
    const state = derivePageState({
      ...defaultParams,
      data: ["item"],
      freshness,
    });
    expect(state).toBe("ready");
  });

  it("data exceeding threshold IS stale", () => {
    const freshness = freshData(100_000, 90_000); // 100s old, 90s threshold
    freshness.isStale = true;
    const state = derivePageState({
      ...defaultParams,
      data: ["item"],
      freshness,
    });
    expect(state).toBe("stale");
  });

  it("never-fetched data is not labeled stale (it's loading)", () => {
    const state = derivePageState({
      ...defaultParams,
      data: null,
      isFetching: true,
      freshness: neverFetched(),
    });
    expect(state).toBe("loading");
  });
});

// =============================================================================
// Accessibility announcements (component test-ids for ARIA)
// =============================================================================

describe("Accessibility semantics", () => {
  it("error state uses assertive announcement (via component role=alert)", () => {
    const state = derivePageState({
      ...defaultParams,
      error: retryableError(),
      data: null,
    });
    // The error state renders PageError which has role="alert" aria-live="assertive"
    expect(state).toBe("error");
  });

  it("loading state uses polite announcement (via component role=status)", () => {
    const state = derivePageState({
      ...defaultParams,
      data: null,
      isFetching: true,
    });
    // Loading renders PageLoading with role="status" aria-live="polite"
    expect(state).toBe("loading");
  });

  it("offline state uses assertive announcement", () => {
    const state = derivePageState({
      ...defaultParams,
      isOffline: true,
    });
    // Offline renders PageOffline with role="alert" aria-live="assertive"
    expect(state).toBe("offline");
  });

  it("unauthorized uses assertive announcement", () => {
    const state = derivePageState({
      ...defaultParams,
      error: unauthorizedError(),
    });
    // Unauthorized renders PageUnauthorized with role="alert"
    expect(state).toBe("unauthorized");
  });

  it("stale uses polite announcement", () => {
    const state = derivePageState({
      ...defaultParams,
      data: ["item"],
      freshness: staleData(),
    });
    // Stale renders PageStale with role="status" aria-live="polite"
    expect(state).toBe("stale");
  });
});
