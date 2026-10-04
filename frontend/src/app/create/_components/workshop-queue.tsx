"use client";

export type QueueStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface WorkshopQueueJob {
  id: string;
  batchId?: string;
  status: QueueStatus;
  progress: number;
  estimatedCost: number;
  model: string;
  error?: string;
  errorKind?: "oom" | "provider-down" | "timeout" | "generic";
  outputs: { id: string; status: "pending" | "approved" | "rejected"; assetId?: string }[];
}

interface WorkshopQueueProps {
  jobs: WorkshopQueueJob[];
  onCancel: (job: WorkshopQueueJob) => void;
  onRetry: (job: WorkshopQueueJob, lowerResolution: boolean) => void;
  onReview: (jobId: string, outputId: string, decision: "approved" | "rejected") => void;
}

const statusLabel: Record<QueueStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function WorkshopQueue({ jobs, onCancel, onRetry, onReview }: WorkshopQueueProps) {
  if (jobs.length === 0) {
    return <section aria-labelledby="queue-heading" className="rounded-xl border border-dashed border-border-default bg-surface-raised p-6 text-center"><h2 id="queue-heading" className="text-sm font-semibold text-content-primary">Generation Queue</h2><p className="mt-1 text-xs text-content-muted">Your cost-gated renders will appear here.</p></section>;
  }

  return (
    <section aria-labelledby="queue-heading" className="space-y-3">
      <div><h2 id="queue-heading" className="text-sm font-semibold text-content-primary">Generation Queue</h2><p className="text-xs text-content-muted">Queued → Running → Completed/Failed. Jobs remain scoped to your authenticated workspace.</p></div>
      {jobs.map((job) => (
        <article key={job.id} className="rounded-xl border border-border-subtle bg-surface-raised p-4" data-testid={`queue-job-${job.id}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><div className="flex items-center gap-2"><span className="text-sm font-medium text-content-primary">{statusLabel[job.status]}</span><span className="rounded-full border border-border-default px-2 py-0.5 text-[10px] text-content-muted">{job.model}</span></div><p className="mt-1 text-[11px] text-content-muted">Estimated reservation: ${job.estimatedCost.toFixed(4)} · Provenance retained by backend job</p></div>
            <div className="flex gap-2">{(job.status === "queued" || job.status === "running") && <button type="button" onClick={() => onCancel(job)} className="rounded-lg border border-border-default px-3 py-1.5 text-xs text-content-secondary hover:border-red-400 hover:text-red-300">Cancel</button>}{(job.status === "failed" || job.status === "cancelled") && <button type="button" onClick={() => onRetry(job, job.errorKind === "oom")} className="rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-500">{job.errorKind === "oom" ? "Retry lower resolution" : "Retry"}</button>}</div>
          </div>
          {(job.status === "queued" || job.status === "running") && <div className="mt-3"><div className="flex justify-between text-[10px] text-content-muted"><span>{job.status === "queued" ? "Waiting for an available provider" : "Provider is rendering"}</span><span>{Math.round(job.progress)}%</span></div><div className="mt-1 h-2 overflow-hidden rounded-full bg-surface-hover"><div className="h-full rounded-full bg-purple-600 transition-all" style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} /></div></div>}
          {job.status === "failed" && <div role="alert" className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">{job.error || "Generation failed."}{job.errorKind === "provider-down" && <p className="mt-1">The provider is unreachable. Retry is safe and remains cost-gated.</p>}{job.errorKind === "timeout" && <p className="mt-1">The provider timed out. Reduce complexity or retry.</p>}{job.errorKind === "oom" && <p className="mt-1">Try the lower-resolution retry or reduce LoRAs.</p>}</div>}
          {job.status === "completed" && <div className="mt-4 grid gap-2 sm:grid-cols-2">{job.outputs.map((output) => <div key={output.id} className="rounded-lg border border-border-default bg-surface-hover p-3"><div className="flex items-center justify-between"><span className="text-xs text-content-secondary">Render {output.id}</span><span className="text-[10px] text-content-muted">{output.status}</span></div><div className="mt-3 flex gap-2"><button type="button" onClick={() => onReview(job.id, output.id, "approved")} className="rounded-md border border-emerald-500/30 px-2 py-1 text-[11px] text-emerald-300">Approve</button><button type="button" onClick={() => onReview(job.id, output.id, "rejected")} className="rounded-md border border-red-500/30 px-2 py-1 text-[11px] text-red-300">Reject</button><button type="button" onClick={() => onRetry(job, false)} className="rounded-md border border-border-default px-2 py-1 text-[11px] text-content-secondary">Retake</button></div></div>)}</div>}
        </article>
      ))}
    </section>
  );
}
