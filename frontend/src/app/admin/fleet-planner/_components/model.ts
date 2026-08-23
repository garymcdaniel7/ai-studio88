/**
 * Fleet demand planner economics model.
 *
 * Mirrors the reference model math exactly:
 *   jobs_per_min_per_worker = 60 / job_sec
 *   drain_min = users / (workers * jobs_per_min_per_worker)
 *   active_hr = drain_min / 60
 *   idle_hr = max(0, 5/60 - active_hr)
 *   gpu_cost = workers * (active_hr * gpu_hr + min(idle_hr, 5/60) * 0.10)
 *   base_per_job = gpu_hr * (job_sec / 3600)
 *   revenue = users * base_per_job * markup
 *   profit = revenue - gpu_cost
 *   warm_idle = workers * 0.10
 */

export interface PlannerInputs {
  /** Concurrent users submitting jobs in the burst window. */
  users: number;
  /** Warm (already provisioned) GPU workers. */
  workers: number;
  /** Credit markup multiplier applied to base per-job cost. */
  markup: number;
  /** Average job duration in seconds. */
  jobSec: number;
  /** GPU rental cost per hour in USD. */
  gpuHr: number;
}

export interface PlannerMetrics {
  jobsPerMinPerWorker: number;
  drainMin: number;
  activeHr: number;
  idleHr: number;
  gpuCost: number;
  basePerJob: number;
  revenue: number;
  profit: number;
  warmIdlePerHr: number;
  warmIdlePerDay: number;
}

/** The 5-minute warm window during which workers are kept alive. */
export const WARM_WINDOW_HOURS = 5 / 60;
/** Idle burn rate per warm worker per hour, in USD. */
export const WARM_IDLE_RATE = 0.1;

export function computePlannerMetrics(inputs: PlannerInputs): PlannerMetrics {
  const { users, workers, markup, jobSec, gpuHr } = inputs;

  const jobsPerMinPerWorker = 60 / jobSec;
  const drainMin = users / (workers * jobsPerMinPerWorker);
  const activeHr = drainMin / 60;
  const idleHr = Math.max(0, WARM_WINDOW_HOURS - activeHr);
  const gpuCost =
    workers * (activeHr * gpuHr + Math.min(idleHr, WARM_WINDOW_HOURS) * WARM_IDLE_RATE);
  const basePerJob = gpuHr * (jobSec / 3600);
  const revenue = users * basePerJob * markup;
  const profit = revenue - gpuCost;
  const warmIdlePerHr = workers * WARM_IDLE_RATE;
  const warmIdlePerDay = warmIdlePerHr * 24;

  return {
    jobsPerMinPerWorker,
    drainMin,
    activeHr,
    idleHr,
    gpuCost,
    basePerJob,
    revenue,
    profit,
    warmIdlePerHr,
    warmIdlePerDay,
  };
}

/** Drain time in minutes for a given worker count (used by the chart curve). */
export function drainMinFor(users: number, workers: number, jobSec: number): number {
  const jobsPerMinPerWorker = 60 / jobSec;
  return users / (workers * jobsPerMinPerWorker);
}

export function formatMinutes(min: number): string {
  if (!isFinite(min) || min <= 0) return "0 min";
  if (min < 1) return `${min.toFixed(1)} min`;
  if (min < 60) return `${Math.round(min)} min`;
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

export function formatCurrency(value: number): string {
  return `$${value.toFixed(2)}`;
}
