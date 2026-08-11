"use client";

/**
 * Skeleton — Reusable skeleton placeholders for loading states.
 *
 * Provides animated placeholder elements matching final layout dimensions.
 * Used during first data load before content is available.
 *
 * Validates: Requirement R17.3
 */

import { cn } from "@/lib/utils";

// =============================================================================
// Base Skeleton
// =============================================================================

interface SkeletonProps {
  className?: string;
  /** Width (Tailwind class or inline). Default: "w-full" */
  width?: string;
  /** Height (Tailwind class or inline). Default: "h-4" */
  height?: string;
  /** Whether to show rounded corners. Default: true */
  rounded?: boolean;
}

/**
 * Base skeleton element — a shimmering placeholder block.
 * Respects reduced-motion preferences.
 */
export function Skeleton({ className, width, height, rounded = true }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "animate-pulse bg-white/[0.06]",
        rounded && "rounded-md",
        width ?? "w-full",
        height ?? "h-4",
        className
      )}
    />
  );
}

// =============================================================================
// Skeleton Variants
// =============================================================================

/**
 * Skeleton for a text line (single row).
 */
export function SkeletonLine({ className, width }: { className?: string; width?: string }) {
  return <Skeleton className={className} width={width} height="h-4" />;
}

/**
 * Skeleton for a heading/title.
 */
export function SkeletonHeading({ className, width }: { className?: string; width?: string }) {
  return <Skeleton className={className} width={width ?? "w-48"} height="h-6" />;
}

/**
 * Skeleton for a circular avatar.
 */
export function SkeletonAvatar({ className, size }: { className?: string; size?: string }) {
  return (
    <Skeleton
      className={cn("rounded-full", className)}
      width={size ?? "w-10"}
      height={size ?? "h-10"}
      rounded={false}
    />
  );
}

/**
 * Skeleton for a card block.
 */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 space-y-3",
        className
      )}
    >
      <Skeleton width="w-2/3" height="h-5" />
      <Skeleton width="w-full" height="h-3" />
      <Skeleton width="w-4/5" height="h-3" />
    </div>
  );
}

/**
 * Skeleton for a table row.
 */
export function SkeletonTableRow({ columns = 4, className }: { columns?: number; className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("flex items-center gap-4 py-3 px-4", className)}
    >
      {Array.from({ length: columns }).map((_, i) => (
        <Skeleton
          key={i}
          width={i === 0 ? "w-1/4" : "w-1/6"}
          height="h-4"
        />
      ))}
    </div>
  );
}

// =============================================================================
// Composite Skeletons (page-level placeholders)
// =============================================================================

/**
 * Skeleton for a page with a list of cards.
 */
export function SkeletonCardList({ count = 3, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("space-y-4", className)} aria-label="Loading content" role="status">
      <SkeletonHeading width="w-36" />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: count }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    </div>
  );
}

/**
 * Skeleton for a page with a data table.
 */
export function SkeletonTable({
  rows = 5,
  columns = 4,
  className,
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)} aria-label="Loading table" role="status">
      <SkeletonHeading width="w-36" />
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] divide-y divide-white/[0.04]">
        {/* Header */}
        <div className="flex items-center gap-4 py-3 px-4">
          {Array.from({ length: columns }).map((_, i) => (
            <Skeleton key={i} width="w-24" height="h-3" />
          ))}
        </div>
        {/* Rows */}
        {Array.from({ length: rows }).map((_, i) => (
          <SkeletonTableRow key={i} columns={columns} />
        ))}
      </div>
    </div>
  );
}

/**
 * Skeleton for a detail/form page.
 */
export function SkeletonDetail({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-6", className)} aria-label="Loading details" role="status">
      <div className="flex items-center gap-4">
        <SkeletonAvatar size="w-16 h-16" />
        <div className="space-y-2">
          <SkeletonHeading width="w-48" />
          <SkeletonLine width="w-32" />
        </div>
      </div>
      <div className="space-y-3">
        <SkeletonLine width="w-full" />
        <SkeletonLine width="w-full" />
        <SkeletonLine width="w-3/4" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Skeleton height="h-10" />
        <Skeleton height="h-10" />
      </div>
    </div>
  );
}
