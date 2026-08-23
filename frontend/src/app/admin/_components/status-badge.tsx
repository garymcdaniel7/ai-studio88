import type { ElementType } from "react";

/**
 * Pill-style status badge shared by admin pages.
 * `icon` accepts a Lucide component; `spinIcon` animates it while loading.
 */
const TONE_CLASSES = {
  success: "text-green-400 bg-green-400/10 border-green-400/20",
  warning: "text-amber-400 bg-amber-400/10 border-amber-400/20",
  error: "text-red-400 bg-red-400/10 border-red-400/20",
  danger: "text-red-500 bg-red-500/10 border-red-500/20",
  info: "text-blue-400 bg-blue-400/10 border-blue-400/20",
  muted: "text-gray-400 bg-gray-400/10 border-gray-400/20",
} as const;

export type StatusTone = keyof typeof TONE_CLASSES;

export function StatusBadge({
  label,
  tone = "muted",
  icon: Icon,
  spinIcon = false,
  className = "",
}: {
  label: string;
  tone?: StatusTone;
  icon?: ElementType;
  spinIcon?: boolean;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        TONE_CLASSES[tone]
      } ${className}`}
    >
      {Icon && <Icon className={`h-3 w-3 ${spinIcon ? "animate-spin" : ""}`} />}
      {label}
    </span>
  );
}
