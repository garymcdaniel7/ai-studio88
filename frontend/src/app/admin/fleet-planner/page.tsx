"use client";

import { useMemo, useState } from "react";
import { AdminTabs } from "../_components/admin-tabs";
import { StatCard } from "../_components/stat-card";
import { PlannerSlider } from "./_components/planner-slider";
import { DrainChart } from "./_components/drain-chart";
import { PriorityLegend, RuleOfThumb } from "./_components/priority-legend";
import {
  computePlannerMetrics,
  formatCurrency,
  formatMinutes,
} from "./_components/model";

export default function FleetPlannerPage() {
  const [users, setUsers] = useState(50);
  const [workers, setWorkers] = useState(4);
  const [markup, setMarkup] = useState(4);
  const [jobSec, setJobSec] = useState(120);
  const [gpuHr, setGpuHr] = useState(0.35);

  const metrics = useMemo(
    () => computePlannerMetrics({ users, workers, markup, jobSec, gpuHr }),
    [users, workers, markup, jobSec, gpuHr]
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Fleet Demand Planner</h1>
        <p className="text-sm text-gray-500">
          Burst economics simulator — how many warm workers does the queue actually need?
        </p>
      </div>

      {/* Tab Navigation */}
      <AdminTabs active="planner" />

      {/* Controls + Chart */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {/* Controls */}
        <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
          <h3 className="mb-4 text-sm font-semibold text-white">Scenario</h3>
          <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
            <PlannerSlider
              label="Concurrent users"
              value={users}
              min={1}
              max={300}
              step={1}
              onChange={setUsers}
            />
            <PlannerSlider
              label="Warm workers"
              value={workers}
              min={1}
              max={60}
              step={1}
              onChange={setWorkers}
            />
            <PlannerSlider
              label="Markup multiplier"
              value={markup}
              min={2}
              max={10}
              step={1}
              onChange={setMarkup}
              formatValue={(v) => `${v}x`}
            />
            <PlannerSlider
              label="Job duration"
              value={jobSec}
              min={15}
              max={300}
              step={5}
              onChange={setJobSec}
              formatValue={(v) => `${v}s`}
            />
            <PlannerSlider
              label="GPU cost / hr"
              value={gpuHr}
              min={0.15}
              max={1.5}
              step={0.05}
              onChange={setGpuHr}
              formatValue={(v) => `$${v.toFixed(2)}`}
            />
          </div>
        </div>

        {/* Chart */}
        <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
          <div className="mb-2 flex items-baseline justify-between">
            <h3 className="text-sm font-semibold text-white">Drain Time vs Warm Workers</h3>
            <span className="text-[10px] text-gray-500">
              {users} users · {jobSec}s jobs
            </span>
          </div>
          <DrainChart users={users} workers={workers} jobSec={jobSec} />
          <p className="mt-2 text-[10px] text-gray-600">
            Log-scale drain time for 1–60 workers. Marker shows your current setting.
          </p>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard
          align="left"
          label="Queue Drain Time"
          value={<span className="text-xl">{formatMinutes(metrics.drainMin)}</span>}
          sub={`${metrics.jobsPerMinPerWorker.toFixed(1)} jobs/min/worker`}
        />
        <StatCard
          align="left"
          label="Burst GPU Cost"
          valueClassName="text-amber-400"
          value={formatCurrency(metrics.gpuCost)}
          sub={`active ${metrics.activeHr.toFixed(2)}h · idle ${metrics.idleHr.toFixed(2)}h`}
        />
        <StatCard
          align="left"
          label="Revenue (credits)"
          valueClassName="text-green-400"
          value={formatCurrency(metrics.revenue)}
          sub={`at ${markup}x markup · ${formatCurrency(metrics.basePerJob)}/job base`}
        />
        <StatCard
          align="left"
          label="Profit"
          valueClassName={metrics.profit >= 0 ? "text-green-400" : "text-red-400"}
          value={formatCurrency(metrics.profit)}
          sub={`margin ${metrics.revenue > 0 ? (((metrics.profit) / metrics.revenue) * 100).toFixed(0) : "0"}%`}
        />
        <StatCard
          align="left"
          label="Warm Idle Cost"
          valueClassName="text-purple-300"
          value={
            <>
              {formatCurrency(metrics.warmIdlePerHr)}
              <span className="text-sm text-gray-500">/hr</span>
            </>
          }
          sub={`${formatCurrency(metrics.warmIdlePerDay)}/day · ${workers} workers @ $0.10/hr`}
        />
      </div>

      {/* Legend + Rule of thumb */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-border-subtle bg-surface-raised p-5 lg:col-span-2">
          <h3 className="mb-3 text-sm font-semibold text-white">Priority Tiers</h3>
          <PriorityLegend />
        </div>
        <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
          <RuleOfThumb />
        </div>
      </div>
    </div>
  );
}
