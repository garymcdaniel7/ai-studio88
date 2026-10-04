import { StatCard } from "./stat-card";
import type { RunPodStatus, VastStatus } from "./types";

/**
 * Top-of-page summary grid: service counts, GPU balance split across
 * providers, and overall GPU state.
 */
export function SummaryCards({
  summary,
  vastStatus,
  runpodStatus,
  gpuActive,
  gpuPaused,
  activeProvider,
}: {
  summary: Record<string, number>;
  vastStatus: VastStatus | null;
  runpodStatus: RunPodStatus | null;
  gpuActive: boolean;
  gpuPaused: boolean;
  activeProvider: string | null;
}) {
  const totalBalance = (vastStatus?.balance || 0) + (runpodStatus?.balance || 0);

  return (
    <div className="grid grid-cols-4 gap-3">
      <StatCard label="Total Services" value={summary.total_services || 0} />
      <StatCard
        label="Connected"
        value={summary.connected || 0}
        valueClassName="text-status-success"
      />
      <StatCard
        label="GPU Balance"
        value={`$${totalBalance.toFixed(2)}`}
        valueClassName="text-status-warning"
        sub={
          <>
            {vastStatus?.api_connected && `V: $${(vastStatus.balance || 0).toFixed(2)}`}
            {vastStatus?.api_connected && runpodStatus?.api_connected && " · "}
            {runpodStatus?.api_connected && `R: $${(runpodStatus.balance || 0).toFixed(2)}`}
          </>
        }
      />
      <StatCard
        label="GPU Status"
        value={gpuActive ? "Active" : gpuPaused ? "Paused" : "Off"}
        valueClassName={`${
          gpuActive ? "text-status-success" : gpuPaused ? "text-status-warning" : "text-content-muted"
        }`}
        sub={activeProvider}
      />
    </div>
  );
}
