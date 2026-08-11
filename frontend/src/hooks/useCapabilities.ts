"use client";

/**
 * useCapabilities — Hook for querying the platform Capability Registry.
 *
 * Fetches GET /api/v1/capabilities and provides helpers to determine
 * feature visibility and behavior based on capability classification:
 *
 * - DISABLED: feature should NOT be rendered at all
 * - SIMULATED: feature rendered with a simulation badge
 * - MISSING: feature returns 501 if called
 * - PRODUCTION / PARTIAL: feature fully available
 * - DEPRECATED: feature available but flagged for removal
 * - UNVERIFIED: feature available but unverified
 *
 * Validates: Requirements R77.1, R77.2, R77.3, R77.4, R77.5, R19.2
 */

import { useSWRFetch } from "./useSWRFetch";

// =============================================================================
// Types
// =============================================================================

export type CapabilityClassification =
  | "production"
  | "partial"
  | "simulated"
  | "missing"
  | "deprecated"
  | "disabled"
  | "unverified";

export type HealthStatus = "healthy" | "degraded" | "unavailable" | "not_applicable";

export interface Capability {
  name: string;
  classification: CapabilityClassification;
  required_providers: string[];
  health_status: HealthStatus;
  description: string;
}

interface CapabilityListResponse {
  items: Capability[];
  total: number;
}

// =============================================================================
// Hook
// =============================================================================

export interface UseCapabilitiesResult {
  /** All capabilities from the registry */
  capabilities: Capability[];
  /** Whether capabilities are still loading */
  isLoading: boolean;
  /** Error if fetch failed */
  error: Error | null;
  /** Check if a capability is usable (not disabled, not missing) */
  isAvailable: (name: string) => boolean;
  /** Check if a capability is in simulated mode (show badge) */
  isSimulated: (name: string) => boolean;
  /** Check if a capability is disabled (should not be rendered) */
  isDisabled: (name: string) => boolean;
  /** Check if a capability is degraded (provider health issue) */
  isDegraded: (name: string) => boolean;
  /** Get the full capability object by name */
  getCapability: (name: string) => Capability | undefined;
  /** Refresh capabilities from backend */
  mutate: () => void;
}

/**
 * Hook to fetch and query the platform Capability Registry.
 *
 * @example
 * ```tsx
 * const { isAvailable, isSimulated, isDisabled } = useCapabilities();
 *
 * if (isDisabled("platform_compute")) return null;
 * if (isSimulated("image_generation")) return <Badge>Simulated</Badge>;
 * ```
 */
export function useCapabilities(): UseCapabilitiesResult {
  const { data, error, isLoading, mutate } = useSWRFetch<CapabilityListResponse>(
    "/api/v1/capabilities"
  );

  const capabilities = data?.items ?? [];

  function getCapability(name: string): Capability | undefined {
    return capabilities.find((c) => c.name === name);
  }

  function isAvailable(name: string): boolean {
    const cap = getCapability(name);
    if (!cap) return true; // Unknown capabilities are treated as available (graceful)
    return (
      cap.classification !== "disabled" &&
      cap.classification !== "missing"
    );
  }

  function isSimulated(name: string): boolean {
    const cap = getCapability(name);
    return cap?.classification === "simulated";
  }

  function isDisabled(name: string): boolean {
    const cap = getCapability(name);
    if (!cap) return false; // Unknown capabilities are NOT disabled (graceful)
    return cap.classification === "disabled";
  }

  function isDegraded(name: string): boolean {
    const cap = getCapability(name);
    if (!cap) return false;
    return cap.health_status === "degraded" || cap.health_status === "unavailable";
  }

  return {
    capabilities,
    isLoading,
    error: error ?? null,
    isAvailable,
    isSimulated,
    isDisabled,
    isDegraded,
    getCapability,
    mutate,
  };
}
