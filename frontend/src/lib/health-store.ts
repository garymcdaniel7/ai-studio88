/**
 * Unified System Health Store — Story 118
 *
 * One typed application-wide store for all health/capability state.
 * All surfaces subscribe to the same authoritative data. No independent
 * duplicate polling. Unknown/stale is NEVER presented as healthy.
 *
 * Features:
 * - Single polling loop with configurable interval
 * - Request deduplication (only one in-flight request at a time)
 * - Freshness tracking with staleness threshold
 * - Visibility-aware: pauses polling when tab is hidden, resumes on focus
 * - Exponential backoff on repeated failures
 * - Last-known state preserved on network failure (labeled stale)
 * - Typed selectors for specific capabilities
 * - Incident acknowledgement support
 */

// =============================================================================
// Types
// =============================================================================

export type ServiceState = "healthy" | "degraded" | "unavailable" | "unknown";

export interface ServiceStatus {
  name: string;
  state: ServiceState;
  lastChecked: number; // Unix timestamp ms
  message?: string;
  incident?: string;
}

export interface SystemHealthState {
  // Overall
  overall: ServiceState;
  lastUpdated: number; // Unix timestamp ms
  isStale: boolean;
  isLoading: boolean;
  isFetching: boolean; // In-flight request
  error: string | null;

  // Individual services
  services: {
    backend: ServiceStatus;
    generation: ServiceStatus;
    storage: ServiceStatus;
    llm: ServiceStatus;
    gpu: ServiceStatus;
    database: ServiceStatus;
  };

  // Polling state
  pollInterval: number; // ms
  backoffMultiplier: number;
  consecutiveFailures: number;
  isVisible: boolean; // Tab visible

  // Incidents
  acknowledgedIncidents: Set<string>;
}

export type ServiceName = keyof SystemHealthState["services"];

export interface HealthStoreActions {
  refresh: () => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
  setVisible: (visible: boolean) => void;
  acknowledgeIncident: (incidentId: string) => void;
  getServiceState: (service: ServiceName) => ServiceState;
  isServiceHealthy: (service: ServiceName) => boolean;
  canGenerate: () => boolean;
}

export type HealthStore = SystemHealthState & HealthStoreActions;

// =============================================================================
// Constants
// =============================================================================

const DEFAULT_POLL_INTERVAL = 30_000; // 30 seconds
const STALE_THRESHOLD = 90_000; // 90 seconds — mark stale if older
const MAX_BACKOFF_INTERVAL = 300_000; // 5 minutes max
const HIDDEN_POLL_INTERVAL = 120_000; // 2 minutes when hidden
const BACKOFF_BASE = 2;

// =============================================================================
// Default State
// =============================================================================

function createDefaultServiceStatus(name: string): ServiceStatus {
  return { name, state: "unknown", lastChecked: 0 };
}

export function createDefaultState(): SystemHealthState {
  return {
    overall: "unknown",
    lastUpdated: 0,
    isStale: true,
    isLoading: false,
    isFetching: false,
    error: null,
    services: {
      backend: createDefaultServiceStatus("Backend API"),
      generation: createDefaultServiceStatus("Generation"),
      storage: createDefaultServiceStatus("Storage"),
      llm: createDefaultServiceStatus("LLM"),
      gpu: createDefaultServiceStatus("GPU Workers"),
      database: createDefaultServiceStatus("Database"),
    },
    pollInterval: DEFAULT_POLL_INTERVAL,
    backoffMultiplier: 1,
    consecutiveFailures: 0,
    isVisible: true,
    acknowledgedIncidents: new Set(),
  };
}

// =============================================================================
// Health Store Implementation
// =============================================================================

type Listener = () => void;
type FetchFn = () => Promise<Record<string, unknown>>;

export function createHealthStore(fetchHealth?: FetchFn): HealthStore {
  let state = createDefaultState();
  const listeners: Set<Listener> = new Set();
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let inFlightRequest: Promise<void> | null = null;

  function notify(): void {
    for (const listener of listeners) {
      listener();
    }
  }

  function updateState(partial: Partial<SystemHealthState>): void {
    state = { ...state, ...partial };
    // Recalculate staleness
    if (state.lastUpdated > 0) {
      state.isStale = Date.now() - state.lastUpdated > STALE_THRESHOLD;
    }
    notify();
  }

  // ─── Deduplication ───────────────────────────────────────────────────────

  async function refresh(): Promise<void> {
    // Deduplication: if already fetching, don't start another
    if (inFlightRequest) {
      return inFlightRequest;
    }

    inFlightRequest = doFetch();
    try {
      await inFlightRequest;
    } finally {
      inFlightRequest = null;
    }
  }

  async function doFetch(): Promise<void> {
    if (!fetchHealth) return;

    updateState({ isFetching: true, isLoading: state.lastUpdated === 0 });

    try {
      const data = await fetchHealth();
      const now = Date.now();

      // Parse response into typed service statuses
      const services = parseHealthResponse(data, now);

      updateState({
        services,
        overall: computeOverall(services),
        lastUpdated: now,
        isStale: false,
        isLoading: false,
        isFetching: false,
        error: null,
        consecutiveFailures: 0,
        backoffMultiplier: 1,
      });
    } catch (err) {
      const failures = state.consecutiveFailures + 1;
      const backoff = Math.min(
        Math.pow(BACKOFF_BASE, failures),
        MAX_BACKOFF_INTERVAL / DEFAULT_POLL_INTERVAL
      );

      updateState({
        isFetching: false,
        isLoading: false,
        error: err instanceof Error ? err.message : "Health check failed",
        consecutiveFailures: failures,
        backoffMultiplier: backoff,
        // Keep last-known services but mark stale
        isStale: state.lastUpdated > 0,
      });
    }
  }

  // ─── Polling ─────────────────────────────────────────────────────────────

  function getEffectiveInterval(): number {
    const base = state.isVisible ? DEFAULT_POLL_INTERVAL : HIDDEN_POLL_INTERVAL;
    return Math.min(base * state.backoffMultiplier, MAX_BACKOFF_INTERVAL);
  }

  function schedulePoll(): void {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      await refresh();
      schedulePoll();
    }, getEffectiveInterval());
  }

  function startPolling(): void {
    refresh(); // Immediate first fetch
    schedulePoll();
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function setVisible(visible: boolean): void {
    const wasHidden = !state.isVisible;
    updateState({ isVisible: visible });

    if (visible && wasHidden) {
      // Resuming from hidden — refresh immediately if stale
      if (state.isStale || Date.now() - state.lastUpdated > STALE_THRESHOLD) {
        refresh();
      }
      // Reset poll interval (was using slower hidden interval)
      if (pollTimer) schedulePoll();
    }
  }

  // ─── Selectors ───────────────────────────────────────────────────────────

  function getServiceState(service: ServiceName): ServiceState {
    return state.services[service].state;
  }

  function isServiceHealthy(service: ServiceName): boolean {
    return state.services[service].state === "healthy";
  }

  function canGenerate(): boolean {
    return (
      state.services.generation.state === "healthy" &&
      state.services.backend.state === "healthy" &&
      !state.isStale
    );
  }

  function acknowledgeIncident(incidentId: string): void {
    state.acknowledgedIncidents.add(incidentId);
    notify();
  }

  // ─── Public API ──────────────────────────────────────────────────────────

  return {
    get overall() { return state.overall; },
    get lastUpdated() { return state.lastUpdated; },
    get isStale() { return state.isStale; },
    get isLoading() { return state.isLoading; },
    get isFetching() { return state.isFetching; },
    get error() { return state.error; },
    get services() { return state.services; },
    get pollInterval() { return state.pollInterval; },
    get backoffMultiplier() { return state.backoffMultiplier; },
    get consecutiveFailures() { return state.consecutiveFailures; },
    get isVisible() { return state.isVisible; },
    get acknowledgedIncidents() { return state.acknowledgedIncidents; },
    refresh,
    startPolling,
    stopPolling,
    setVisible,
    acknowledgeIncident,
    getServiceState,
    isServiceHealthy,
    canGenerate,
  };
}

// =============================================================================
// Response Parsing
// =============================================================================

function parseHealthResponse(
  data: Record<string, unknown>,
  now: number
): SystemHealthState["services"] {
  function parseService(key: string, displayName: string): ServiceStatus {
    const raw = data[key];
    if (raw && typeof raw === "object") {
      const obj = raw as Record<string, unknown>;
      return {
        name: displayName,
        state: normalizeState(obj["status"] ?? obj["state"]),
        lastChecked: now,
        message: typeof obj["message"] === "string" ? obj["message"] : undefined,
        incident: typeof obj["incident"] === "string" ? obj["incident"] : undefined,
      };
    }
    // If key not present, state is unknown (NOT healthy)
    return { name: displayName, state: "unknown", lastChecked: now };
  }

  return {
    backend: parseService("backend", "Backend API"),
    generation: parseService("generation", "Generation"),
    storage: parseService("storage", "Storage"),
    llm: parseService("llm", "LLM"),
    gpu: parseService("gpu", "GPU Workers"),
    database: parseService("database", "Database"),
  };
}

function normalizeState(raw: unknown): ServiceState {
  if (typeof raw !== "string") return "unknown";
  const lower = raw.toLowerCase();
  if (lower === "healthy" || lower === "ok" || lower === "ready") return "healthy";
  if (lower === "degraded" || lower === "warning") return "degraded";
  if (lower === "unavailable" || lower === "error" || lower === "down") return "unavailable";
  return "unknown";
}

function computeOverall(services: SystemHealthState["services"]): ServiceState {
  const states = Object.values(services).map((s) => s.state);
  if (states.every((s) => s === "healthy")) return "healthy";
  if (states.some((s) => s === "unavailable")) return "unavailable";
  if (states.some((s) => s === "degraded")) return "degraded";
  return "unknown";
}
