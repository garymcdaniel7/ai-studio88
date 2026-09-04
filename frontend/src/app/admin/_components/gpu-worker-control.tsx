import { Server, Loader2, Square, Play, Pause } from "lucide-react";
import type { GpuWorkerAction, ThunderStatus } from "./types";

/**
 * GPU Worker control card: launch/stop button plus pause/resume,
 * with a live connection indicator and inline worker errors.
 */
export function GpuWorkerControl({
  thunderStatus,
  gpuActive,
  gpuPaused,
  activeProvider,
  workerAction,
  bootProgress,
  workerError,
  onToggleWorker,
  onPause,
  onResume,
}: {
  thunderStatus: ThunderStatus | null;
  gpuActive: boolean;
  gpuPaused: boolean;
  activeProvider: string | null;
  workerAction: GpuWorkerAction;
  bootProgress: string;
  workerError: string | null;
  onToggleWorker: () => void;
  onPause: () => void;
  onResume: () => void;
}) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-raised p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Server className="h-6 w-6 text-status-info" />
          <div>
            <h3 className="text-sm font-semibold text-content-primary">GPU Worker</h3>
            <p className="text-xs text-content-muted">
              {gpuActive
                ? `${activeProvider}: ${
                    thunderStatus?.instance_info?.gpu_name
                      ? `${thunderStatus?.instance_info?.gpu_name} @ $${thunderStatus?.instance_info?.price_per_hour?.toFixed(2)}/hr`
                      : "Active"
                  }`
                : gpuPaused
                  ? "Instance paused (no billing)"
                  : "No instance running"}
            </p>
          </div>
        </div>
        {/* Thunder Compute connection indicator */}
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${
            gpuActive ? "bg-green-500" : thunderStatus?.api_connected ? "bg-amber-400" : "bg-gray-600"
          }`} />
          <span className={`text-xs ${
            gpuActive ? "text-status-success" : thunderStatus?.api_connected ? "text-status-warning" : "text-content-muted"
          }`}>
            {gpuActive ? "GPU Active" : thunderStatus?.api_connected ? "Thunder Connected" : "Not Connected"}
          </span>
        </div>
      </div>

      {workerError && (
        <div className="mb-3 rounded-lg border border-status-error/30 bg-status-error-muted px-3 py-2">
          <p className="text-xs text-status-error">{workerError}</p>
        </div>
      )}

      <div className="flex items-center gap-3">
        {/* Main Launch/Stop Button */}
        <button
          onClick={onToggleWorker}
          disabled={workerAction !== "idle"}
          className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors disabled:opacity-50 ${
            gpuActive
              ? "bg-red-600 text-white hover:bg-red-700"
              : "bg-purple-600 text-white hover:bg-purple-700"
          }`}
        >
          {workerAction === "launching" ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> {bootProgress || "Launching..."}</>
          ) : workerAction === "stopping" ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Stopping...</>
          ) : gpuActive ? (
            <><Square className="h-4 w-4" /> Stop Worker</>
          ) : (
            <><Play className="h-4 w-4" /> Launch Worker</>
          )}
        </button>

        {/* Pause/Resume Button */}
        {gpuActive && (
          <button
            onClick={onPause}
            disabled={workerAction !== "idle"}
            className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm font-medium text-amber-400 hover:bg-amber-500/20 disabled:opacity-50"
          >
            {workerAction === "pausing" ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Pausing...</>
            ) : (
              <><Pause className="h-4 w-4" /> Pause (Save $)</>
            )}
          </button>
        )}
        {gpuPaused && (
          <button
            onClick={onResume}
            disabled={workerAction !== "idle"}
            className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-2.5 text-sm font-medium text-green-400 hover:bg-green-500/20 disabled:opacity-50"
          >
            {workerAction === "resuming" ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Resuming...</>
            ) : (
              <><Play className="h-4 w-4" /> Resume Instance</>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
