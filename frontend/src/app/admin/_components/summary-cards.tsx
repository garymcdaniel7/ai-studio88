import { StatCard } from "./stat-card";
import type { ThunderStatus } from "./types";

/**
 * Top-of-page summary grid: service counts, GPU balance, and overall GPU state.
 */
export function SummaryCards({
  summary,
  thunderStatus,
  gpuActive,
  gpuPaused,
  activeProvider,
}: {
  summary: Record<string, number>;
  thunderStatus: ThunderStatus | null;
  gpuActive: boolean;
  gpuPaused: boolean;
  activeProvider: string | null;
}) {
  const totalBalance = thunderStatus?.balance || 0;

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
            {thunderStatus?.api_connected && `TC: $${(thunderStatus.balance || 0).toFixed(2)}`}
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
