"use client";

import {
  Activity,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Loader2,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";
import type { ProviderDefinition, ProviderConnection } from "./provider-config";

type HealthState = {
  healthy: boolean;
  message: string;
  checkedAt?: string;
};

type ProviderCardProps = {
  definition: ProviderDefinition;
  connection?: ProviderConnection;
  selected: boolean;
  health?: HealthState;
  capabilitiesFromApi?: string[];
  testing: boolean;
  revoking: boolean;
  onSelect: () => void;
  onTest: () => void;
  onRevoke: () => void;
};

function statusLabel(connection?: ProviderConnection, health?: HealthState): string {
  if (connection?.lifecycle_state === "revoked") return "Revoked";
  if (connection?.lifecycle_state === "reauth_required") return "Reauthorization needed";
  if (health && !health.healthy) return "Provider unavailable";
  if (connection?.health_status === "degraded") return "Degraded";
  if (connection) return "Connected · key stored";
  return "Not configured";
}

function statusClass(connection?: ProviderConnection, health?: HealthState): string {
  if (connection?.lifecycle_state === "revoked" || (health && !health.healthy)) {
    return "border-red-400/20 bg-red-400/10 text-red-200";
  }
  if (connection?.lifecycle_state === "reauth_required" || connection?.health_status === "degraded") {
    return "border-amber-400/20 bg-amber-400/10 text-amber-200";
  }
  if (connection) return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
  return "border-white/[0.08] bg-white/[0.03] text-slate-400";
}

export function ProviderCard({
  definition,
  connection,
  selected,
  health,
  capabilitiesFromApi,
  testing,
  revoking,
  onSelect,
  onTest,
  onRevoke,
}: ProviderCardProps) {
  const capabilities = connection?.capabilities?.length
    ? connection.capabilities
    : capabilitiesFromApi?.length
      ? capabilitiesFromApi
      : [definition.lane.split(" · ")[1] || "Provider workload"];

  return (
    <article className="rounded-2xl border border-white/[0.08] bg-[#111827] p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex gap-3">
          <div className="mt-0.5 rounded-lg border border-violet-400/20 bg-violet-400/10 p-2 text-violet-300">
            <KeyRound className="h-4 w-4" aria-hidden="true" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold text-white">{definition.name}</h3>
              <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusClass(connection, health)}`}>
                {statusLabel(connection, health)}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">{definition.lane}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {connection && (
            <button
              type="button"
              onClick={onSelect}
              aria-pressed={selected}
              className={`rounded-lg border px-3 py-2 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-violet-400/70 ${
                selected
                  ? "border-violet-400/50 bg-violet-400/15 text-violet-200"
                  : "border-white/[0.1] text-slate-300 hover:border-violet-400/40 hover:text-white"
              }`}
            >
              {selected ? "Selected for this session" : "Select for this session"}
            </button>
          )}
          <a
            href={definition.docsUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-lg border border-white/[0.1] px-3 py-2 text-xs text-slate-300 hover:text-white focus:outline-none focus:ring-2 focus:ring-violet-400/70"
          >
            Provider docs <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        </div>
      </div>

      <div className="mt-5 grid gap-3 text-xs text-slate-300 md:grid-cols-3">
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="flex items-center gap-2 text-slate-400">
            <Activity className="h-3.5 w-3.5" aria-hidden="true" /> Health
          </div>
          <p className="mt-2 text-slate-200">{health?.message || connection?.health_status || "Awaiting a health check"}</p>
          {health?.checkedAt && <p className="mt-1 text-[11px] text-slate-500">Checked {new Date(health.checkedAt).toLocaleString()}</p>}
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="flex items-center gap-2 text-slate-400">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Capabilities
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {capabilities.map((capability) => (
              <span key={capability} className="rounded-md bg-white/[0.06] px-2 py-1 text-[11px] text-slate-300">
                {capability}
              </span>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="flex items-center gap-2 text-slate-400">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Key lifecycle
          </div>
          <p className="mt-2 text-slate-200">{connection ? "•••••••• · never redisplayed" : "No key stored"}</p>
          <p className="mt-1 text-[11px] text-slate-500">
            {connection && connection.expires_at ? `Expires ${new Date(connection.expires_at).toLocaleDateString()}` : connection ? "Expiry: not reported by the connection contract" : "Expiry starts when the provider issues the key"}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-4">
        <p className="max-w-2xl text-xs leading-5 text-slate-400">{definition.costCopy}</p>
        {connection && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onTest}
              disabled={testing || revoking}
              className="inline-flex items-center gap-2 rounded-lg border border-white/[0.1] px-3 py-2 text-xs font-medium text-slate-200 hover:border-violet-400/40 hover:text-white disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-violet-400/70"
            >
              {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Activity className="h-3.5 w-3.5" aria-hidden="true" />}
              {testing ? "Testing…" : "Test provider health"}
            </button>
            <button
              type="button"
              onClick={onRevoke}
              disabled={testing || revoking}
              className="inline-flex items-center gap-2 rounded-lg border border-red-400/20 px-3 py-2 text-xs font-medium text-red-200 hover:bg-red-400/10 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-red-400/70"
            >
              {revoking ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
              {revoking ? "Revoking…" : "Revoke key"}
            </button>
          </div>
        )}
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500">{definition.ownershipCopy}</p>
      {health && !health.healthy && (
        <p className="mt-3 flex items-center gap-2 text-xs text-red-200" role="status">
          <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
          Health checks do not expose the stored key. Review the provider console before rotating it.
        </p>
      )}
    </article>
  );
}
