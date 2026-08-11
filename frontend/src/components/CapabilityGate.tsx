"use client";

/**
 * CapabilityGate — Conditionally renders children based on capability state.
 *
 * Wraps content that depends on a specific platform capability and controls
 * rendering behavior based on the capability's classification:
 *
 * - DISABLED: children are NOT rendered (null)
 * - SIMULATED: children rendered with a simulation badge overlay
 * - MISSING: children NOT rendered (feature not implemented)
 * - PRODUCTION/PARTIAL/UNVERIFIED: children rendered normally
 * - DEPRECATED: children rendered with a deprecated badge
 *
 * Validates: Requirements R77.1, R77.2, R77.3, R77.4, R77.5, R77.7
 */

import { type ReactNode } from "react";
import { useCapabilities, type CapabilityClassification } from "@/hooks/useCapabilities";

// =============================================================================
// SimulationBadge — visual indicator for simulated features
// =============================================================================

function SimulationBadge({ children }: { children: ReactNode }) {
  return (
    <div className="relative">
      <div className="absolute -top-1 -right-1 z-10 rounded-full bg-amber-500/90 px-2 py-0.5 text-[10px] font-semibold text-black shadow-sm">
        Simulated
      </div>
      {children}
    </div>
  );
}

function DeprecatedBadge({ children }: { children: ReactNode }) {
  return (
    <div className="relative opacity-75">
      <div className="absolute -top-1 -right-1 z-10 rounded-full bg-gray-500/90 px-2 py-0.5 text-[10px] font-semibold text-white shadow-sm">
        Deprecated
      </div>
      {children}
    </div>
  );
}

function DegradedBadge({ children }: { children: ReactNode }) {
  return (
    <div className="relative">
      <div className="absolute -top-1 -right-1 z-10 rounded-full bg-orange-500/90 px-2 py-0.5 text-[10px] font-semibold text-black shadow-sm">
        Degraded
      </div>
      {children}
    </div>
  );
}

// =============================================================================
// CapabilityGate
// =============================================================================

export interface CapabilityGateProps {
  /** The capability name to check against the registry */
  capability: string;
  /** Content to render when the capability is available */
  children: ReactNode;
  /** Optional fallback to render when capability is disabled/missing (default: null) */
  fallback?: ReactNode;
  /** If true, show the degraded badge when provider health is degraded */
  showDegradedBadge?: boolean;
}

/**
 * Conditionally renders children based on capability classification.
 *
 * @example
 * ```tsx
 * <CapabilityGate capability="image_generation">
 *   <GenerateButton />
 * </CapabilityGate>
 *
 * <CapabilityGate capability="platform_compute" fallback={<UpgradePrompt />}>
 *   <ComputePanel />
 * </CapabilityGate>
 * ```
 */
export function CapabilityGate({
  capability,
  children,
  fallback = null,
  showDegradedBadge = true,
}: CapabilityGateProps) {
  const { getCapability, isDisabled, isSimulated, isDegraded, isLoading } = useCapabilities();

  // While loading, render nothing to avoid flash of gated content
  if (isLoading) return null;

  // DISABLED or MISSING: do not render
  const cap = getCapability(capability);
  if (isDisabled(capability) || cap?.classification === "missing") {
    return <>{fallback}</>;
  }

  // SIMULATED: render with badge
  if (isSimulated(capability)) {
    return <SimulationBadge>{children}</SimulationBadge>;
  }

  // DEPRECATED: render with deprecated badge
  if (cap?.classification === "deprecated") {
    return <DeprecatedBadge>{children}</DeprecatedBadge>;
  }

  // DEGRADED health: optionally show badge
  if (showDegradedBadge && isDegraded(capability)) {
    return <DegradedBadge>{children}</DegradedBadge>;
  }

  // PRODUCTION / PARTIAL / UNVERIFIED: render normally
  return <>{children}</>;
}

// =============================================================================
// Utility: useCapabilityClassification (for inline usage)
// =============================================================================

/**
 * Returns the classification for a single capability.
 * Useful when you need fine-grained control in component logic
 * rather than wrapping with CapabilityGate.
 *
 * @example
 * ```tsx
 * const classification = useCapabilityClassification("video_generation");
 * if (classification === "disabled") return null;
 * ```
 */
export function useCapabilityClassification(
  capabilityName: string
): CapabilityClassification | null {
  const { getCapability, isLoading } = useCapabilities();
  if (isLoading) return null;
  return getCapability(capabilityName)?.classification ?? null;
}
