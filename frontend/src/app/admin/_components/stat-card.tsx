import type { ReactNode } from "react";

/**
 * Metric card used in dashboard summary rows: label on top,
 * large value, optional sub-line. Center-aligned by default.
 */
export function StatCard({
  label,
  value,
  valueClassName = "text-content-primary",
  sub,
  align = "center",
}: {
  label: string;
  value: ReactNode;
  valueClassName?: string;
  sub?: ReactNode;
  align?: "center" | "left";
}) {
  return (
    <div
      className={`rounded-xl border border-border-subtle bg-surface-raised p-4 ${
        align === "center" ? "text-center" : ""
      }`}
    >
      <p className="text-xs text-content-muted">{label}</p>
      <p className={`text-2xl font-bold ${valueClassName}`}>{value}</p>
      {sub !== undefined && sub !== null && (
        <div className="text-[10px] text-content-muted mt-0.5">{sub}</div>
      )}
    </div>
  );
}
