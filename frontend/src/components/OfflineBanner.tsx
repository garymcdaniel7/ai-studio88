"use client";

/**
 * OfflineBanner — Persistent banner displayed when the user is offline.
 *
 * Shows a dismissible (but re-appearing) banner at the top of the viewport
 * when offline. Also provides a context for disabling mutations globally.
 *
 * Validates: Requirement R17.5
 */

import { createContext, useContext, type ReactNode } from "react";
import { WifiOff, RefreshCw } from "lucide-react";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";

// =============================================================================
// Context — allows children to check if mutations should be disabled
// =============================================================================

interface OfflineContextValue {
  /** Whether the user is offline (browser-level) */
  isOffline: boolean;
  /** Whether the backend is unreachable (even if browser says online) */
  isBackendDown: boolean;
  /** Whether mutations should be disabled (true if offline OR backend unreachable) */
  isMutationDisabled: boolean;
  /** Trigger a connectivity check */
  checkNow: () => void;
}

const OfflineContext = createContext<OfflineContextValue>({
  isOffline: false,
  isBackendDown: false,
  isMutationDisabled: false,
  checkNow: () => {},
});

/**
 * Hook to access offline/mutation-disabled state from any component.
 *
 * @example
 * ```tsx
 * const { isMutationDisabled } = useOfflineContext();
 * <button disabled={isMutationDisabled}>Save</button>
 * ```
 */
export function useOfflineContext(): OfflineContextValue {
  return useContext(OfflineContext);
}

// =============================================================================
// Provider + Banner
// =============================================================================

interface OfflineBannerProviderProps {
  children: ReactNode;
}

/**
 * Wraps children with offline detection context and renders a banner when offline.
 * Place high in the component tree (inside Providers, outside page content).
 */
export function OfflineBannerProvider({ children }: OfflineBannerProviderProps) {
  const { isOnline, isBackendReachable, checkNow } = useOnlineStatus();

  const isOffline = !isOnline;
  const isBackendDown = isOnline && !isBackendReachable;
  const isMutationDisabled = isOffline || isBackendDown;

  const contextValue: OfflineContextValue = {
    isOffline,
    isBackendDown,
    isMutationDisabled,
    checkNow,
  };

  return (
    <OfflineContext.Provider value={contextValue}>
      {isMutationDisabled && (
        <OfflineBannerUI
          isOffline={isOffline}
          isBackendDown={isBackendDown}
          onRetry={checkNow}
        />
      )}
      {children}
    </OfflineContext.Provider>
  );
}

// =============================================================================
// Banner UI
// =============================================================================

interface OfflineBannerUIProps {
  isOffline: boolean;
  isBackendDown: boolean;
  onRetry: () => void;
}

function OfflineBannerUI({ isOffline, isBackendDown, onRetry }: OfflineBannerUIProps) {
  const message = isOffline
    ? "You're offline. Changes cannot be saved until connection is restored."
    : "Backend unreachable. Mutations are disabled until connectivity is confirmed.";

  return (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="offline-banner"
      className="fixed top-0 left-0 right-0 z-[100] bg-amber-900/95 border-b border-amber-500/50 px-4 py-2.5 flex items-center justify-center gap-3 backdrop-blur-sm"
    >
      <WifiOff className="h-4 w-4 text-amber-300 shrink-0" />
      <span className="text-sm text-amber-200">
        {message}
      </span>
      <button
        onClick={onRetry}
        className="flex items-center gap-1.5 rounded bg-amber-800 px-2.5 py-1 text-xs text-amber-200 hover:bg-amber-700 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-amber-400"
        aria-label="Retry connection"
      >
        <RefreshCw className="h-3 w-3" />
        Retry
      </button>
      {isBackendDown && !isOffline && (
        <span className="text-[10px] text-amber-400 ml-2">
          Browser online, but API server is not responding
        </span>
      )}
    </div>
  );
}
