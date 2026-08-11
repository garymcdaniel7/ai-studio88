"use client";

/**
 * Page State UI Components — Story 141
 *
 * Reusable, accessible components for every page data state.
 * Each component is visually and semantically distinct, with:
 * - Appropriate ARIA announcements (live regions)
 * - Domain-specific actions (retry, refresh, login, clear filters)
 * - Reduced-motion support
 * - Consistent dark-theme styling matching the app design
 */

import { Loader2, AlertCircle, WifiOff, ShieldAlert, SearchX, Inbox, RefreshCw, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PageError, DataFreshness, SectionStatus } from "@/lib/page-state";

// =============================================================================
// Shared wrapper for state containers
// =============================================================================

interface StateContainerProps {
  children: React.ReactNode;
  /** ARIA role for the container */
  role?: string;
  /** ARIA live region priority */
  "aria-live"?: "polite" | "assertive" | "off";
  className?: string;
  testId?: string;
}

function StateContainer({ children, role, "aria-live": ariaLive, className, testId }: StateContainerProps) {
  return (
    <div
      role={role}
      aria-live={ariaLive}
      aria-atomic="true"
      data-testid={testId}
      className={cn("flex flex-col items-center justify-center py-16 px-4 text-center", className)}
    >
      {children}
    </div>
  );
}

// =============================================================================
// PageLoading — Initial load, no data yet
// =============================================================================

interface PageLoadingProps {
  /** What is being loaded (e.g. "talent", "models") */
  resource?: string;
  className?: string;
}

export function PageLoading({ resource, className }: PageLoadingProps) {
  return (
    <StateContainer
      role="status"
      aria-live="polite"
      testId="page-state-loading"
      className={className}
    >
      <Loader2 className="h-8 w-8 animate-spin text-purple-500 motion-reduce:animate-none" />
      <p className="mt-3 text-sm text-gray-400">
        {resource ? `Loading ${resource}…` : "Loading…"}
      </p>
    </StateContainer>
  );
}

// =============================================================================
// PageRefreshing — Background refresh indicator (inline, non-blocking)
// =============================================================================

interface PageRefreshingProps {
  className?: string;
}

export function PageRefreshing({ className }: PageRefreshingProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Updating data"
      data-testid="page-state-refreshing"
      className={cn(
        "flex items-center gap-2 rounded-lg border border-purple-500/20 bg-purple-500/5 px-3 py-1.5 text-xs text-purple-300",
        className
      )}
    >
      <RefreshCw className="h-3 w-3 animate-spin motion-reduce:animate-none" />
      <span>Updating…</span>
    </div>
  );
}

// =============================================================================
// PageStale — Data is present but exceeds freshness threshold
// =============================================================================

interface PageStaleProps {
  freshness: DataFreshness;
  onRefresh?: () => void;
  className?: string;
}

export function PageStale({ freshness, onRefresh, className }: PageStaleProps) {
  const age = freshness.lastFetched > 0
    ? formatAge(Date.now() - freshness.lastFetched)
    : "unknown";

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="page-state-stale"
      className={cn(
        "flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-1.5 text-xs text-amber-300",
        className
      )}
    >
      <Clock className="h-3 w-3" />
      <span>Data is {age} old</span>
      {onRefresh && (
        <button
          onClick={onRefresh}
          className="ml-1 underline hover:text-amber-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-amber-400 rounded"
          aria-label="Refresh stale data"
        >
          Refresh
        </button>
      )}
    </div>
  );
}

// =============================================================================
// PageEmpty — No data (unfiltered)
// =============================================================================

interface PageEmptyProps {
  /** What's empty (e.g. "talent", "models") */
  resource?: string;
  /** Icon to display */
  icon?: React.ReactNode;
  /** Call-to-action button */
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function PageEmpty({ resource, icon, action, className }: PageEmptyProps) {
  return (
    <StateContainer
      role="status"
      aria-live="polite"
      testId="page-state-empty"
      className={className}
    >
      {icon || <Inbox className="h-10 w-10 text-gray-600" />}
      <p className="mt-3 text-sm text-gray-400">
        {resource ? `No ${resource} yet` : "No data yet"}
      </p>
      <p className="mt-1 text-xs text-gray-600">
        {resource ? `Create your first ${resource} to get started.` : "Nothing to show here yet."}
      </p>
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
        >
          {action.label}
        </button>
      )}
    </StateContainer>
  );
}

// =============================================================================
// PageFilteredEmpty — Filters active but no results match
// =============================================================================

interface PageFilteredEmptyProps {
  /** Description of active filter */
  filterDescription?: string;
  onClearFilters?: () => void;
  className?: string;
}

export function PageFilteredEmpty({ filterDescription, onClearFilters, className }: PageFilteredEmptyProps) {
  return (
    <StateContainer
      role="status"
      aria-live="polite"
      testId="page-state-filtered-empty"
      className={className}
    >
      <SearchX className="h-10 w-10 text-gray-600" />
      <p className="mt-3 text-sm text-gray-400">
        No results{filterDescription ? ` for "${filterDescription}"` : " match your filters"}
      </p>
      <p className="mt-1 text-xs text-gray-600">
        Try adjusting your filters or search terms.
      </p>
      {onClearFilters && (
        <button
          onClick={onClearFilters}
          className="mt-4 rounded-lg border border-white/[0.08] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
        >
          Clear filters
        </button>
      )}
    </StateContainer>
  );
}

// =============================================================================
// PageError — Fetch failed, no usable data
// =============================================================================

interface PageErrorProps {
  error: PageError;
  onRetry?: () => void;
  className?: string;
}

export function PageError({ error, onRetry, className }: PageErrorProps) {
  return (
    <StateContainer
      role="alert"
      aria-live="assertive"
      testId="page-state-error"
      className={className}
    >
      <AlertCircle className="h-10 w-10 text-red-400" />
      <p className="mt-3 text-sm text-red-300 font-medium">
        {error.message}
      </p>
      {error.status && (
        <p className="mt-1 text-xs text-gray-600">
          Error {error.status}{error.code ? ` · ${error.code}` : ""}
        </p>
      )}
      {onRetry && error.retryable && (
        <button
          onClick={onRetry}
          className="mt-4 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-300 hover:bg-red-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
          aria-label="Retry loading data"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Try again
        </button>
      )}
    </StateContainer>
  );
}

// =============================================================================
// PageRetrying — Auto-retry in progress
// =============================================================================

interface PageRetryingProps {
  attempt: number;
  maxAttempts: number;
  className?: string;
}

export function PageRetrying({ attempt, maxAttempts, className }: PageRetryingProps) {
  return (
    <StateContainer
      role="status"
      aria-live="polite"
      testId="page-state-retrying"
      className={className}
    >
      <Loader2 className="h-8 w-8 animate-spin text-amber-400 motion-reduce:animate-none" />
      <p className="mt-3 text-sm text-amber-300">
        Connection issue — retrying…
      </p>
      <p className="mt-1 text-xs text-gray-600">
        Attempt {attempt} of {maxAttempts}
      </p>
    </StateContainer>
  );
}

// =============================================================================
// PageOffline — Browser is offline
// =============================================================================

interface PageOfflineProps {
  /** Whether there is last-known data available */
  hasData?: boolean;
  className?: string;
}

export function PageOffline({ hasData, className }: PageOfflineProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="page-state-offline"
      className={cn(
        "flex items-center gap-3 rounded-lg border border-gray-500/20 bg-gray-500/5 px-4 py-3",
        !hasData && "flex-col py-16",
        className
      )}
    >
      <WifiOff className={cn("text-gray-400", hasData ? "h-4 w-4" : "h-10 w-10")} />
      <div className={cn(!hasData && "text-center mt-3")}>
        <p className={cn("text-sm text-gray-300", !hasData && "font-medium")}>
          You're offline
        </p>
        <p className="text-xs text-gray-500 mt-0.5">
          {hasData
            ? "Showing last-known data. Changes will sync when reconnected."
            : "Check your internet connection and try again."}
        </p>
      </div>
    </div>
  );
}

// =============================================================================
// PageUnauthorized — 401/403
// =============================================================================

interface PageUnauthorizedProps {
  message?: string;
  onLogin?: () => void;
  className?: string;
}

export function PageUnauthorized({ message, onLogin, className }: PageUnauthorizedProps) {
  return (
    <StateContainer
      role="alert"
      aria-live="assertive"
      testId="page-state-unauthorized"
      className={className}
    >
      <ShieldAlert className="h-10 w-10 text-amber-400" />
      <p className="mt-3 text-sm text-amber-300 font-medium">
        {message || "Session expired or insufficient permissions"}
      </p>
      <p className="mt-1 text-xs text-gray-600">
        Please sign in again to continue.
      </p>
      {onLogin && (
        <button
          onClick={onLogin}
          className="mt-4 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
        >
          Sign in
        </button>
      )}
    </StateContainer>
  );
}

// =============================================================================
// PagePartial — Some sections loaded, some failed
// =============================================================================

interface PagePartialProps {
  sections: SectionStatus[];
  onRetrySection?: (key: string) => void;
  className?: string;
}

export function PagePartial({ sections, onRetrySection, className }: PagePartialProps) {
  const failedSections = sections.filter((s) => s.state === "error");

  if (failedSections.length === 0) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="page-state-partial"
      className={cn(
        "rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3",
        className
      )}
    >
      <p className="text-xs font-medium text-amber-300 mb-2">
        Some sections couldn't load:
      </p>
      <ul className="space-y-1">
        {failedSections.map((section) => (
          <li key={section.key} className="flex items-center justify-between text-xs">
            <span className="text-gray-400">
              {section.label}: <span className="text-red-400">{section.error?.message || "Failed"}</span>
            </span>
            {onRetrySection && section.error?.retryable && (
              <button
                onClick={() => onRetrySection(section.key)}
                className="text-amber-300 underline hover:text-amber-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-amber-400 rounded ml-2"
                aria-label={`Retry loading ${section.label}`}
              >
                Retry
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// =============================================================================
// PageTerminal — Unrecoverable failure
// =============================================================================

interface PageTerminalProps {
  error: PageError;
  className?: string;
}

export function PageTerminal({ error, className }: PageTerminalProps) {
  return (
    <StateContainer
      role="alert"
      aria-live="assertive"
      testId="page-state-terminal"
      className={className}
    >
      <AlertCircle className="h-10 w-10 text-red-500" />
      <p className="mt-3 text-sm text-red-300 font-medium">
        Unable to load this page
      </p>
      <p className="mt-1 text-xs text-gray-500 max-w-sm">
        {error.message}
      </p>
      <p className="mt-3 text-xs text-gray-600">
        If this persists, contact support or check the system status page.
      </p>
    </StateContainer>
  );
}

// =============================================================================
// PageStateRenderer — Orchestrator that selects the right component
// =============================================================================

import type { PageDataState } from "@/lib/page-state";

interface PageStateRendererProps {
  state: PageDataState;
  error: PageError | null;
  freshness: DataFreshness;
  retryAttempt: number;
  maxRetries?: number;
  isOffline: boolean;
  hasData: boolean;
  resource?: string;
  /** Rendered when state is ready/refreshing/stale (children = your content) */
  children: React.ReactNode;
  onRetry?: () => void;
  onRefresh?: () => void;
  onLogin?: () => void;
  onClearFilters?: () => void;
  /** Custom empty state */
  emptyState?: React.ReactNode;
  /** For partial failures */
  sections?: SectionStatus[];
  onRetrySection?: (key: string) => void;
  className?: string;
}

/**
 * Orchestrates which page-state component to render based on current state.
 * Wraps your content and prepends status banners (stale, refreshing, offline, partial)
 * when data IS available, or replaces content with full-page states when it isn't.
 */
export function PageStateRenderer({
  state,
  error,
  freshness,
  retryAttempt,
  maxRetries = 3,
  isOffline,
  hasData,
  resource,
  children,
  onRetry,
  onRefresh,
  onLogin,
  onClearFilters,
  emptyState,
  sections,
  onRetrySection,
  className,
}: PageStateRendererProps) {
  // Full-page replacement states (no data to show)
  switch (state) {
    case "loading":
      return <PageLoading resource={resource} className={className} />;
    case "retrying":
      return <PageRetrying attempt={retryAttempt} maxAttempts={maxRetries} className={className} />;
    case "error":
      return error ? <PageError error={error} onRetry={onRetry} className={className} /> : null;
    case "terminal":
      return error ? <PageTerminal error={error} className={className} /> : null;
    case "unauthorized":
      return <PageUnauthorized onLogin={onLogin} className={className} />;
    case "empty":
      return emptyState ? <>{emptyState}</> : <PageEmpty resource={resource} className={className} />;
    case "filtered-empty":
      return <PageFilteredEmpty onClearFilters={onClearFilters} className={className} />;
    case "offline":
      if (!hasData) return <PageOffline hasData={false} className={className} />;
      break;
  }

  // Banner states (data IS available, but with caveats)
  return (
    <div className={className}>
      {/* Status banners */}
      {isOffline && hasData && <PageOffline hasData className="mb-4" />}
      {state === "stale" && <PageStale freshness={freshness} onRefresh={onRefresh} className="mb-4" />}
      {state === "refreshing" && <PageRefreshing className="mb-4" />}
      {state === "partial" && sections && (
        <PagePartial sections={sections} onRetrySection={onRetrySection} className="mb-4" />
      )}
      {children}
    </div>
  );
}

// =============================================================================
// Utility
// =============================================================================

function formatAge(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}
