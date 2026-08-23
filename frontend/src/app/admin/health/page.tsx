"use client";

import { useEffect, useState, useCallback } from "react";
import { authFetch } from "@/lib/api";
import {
  Activity,
  Server,
  Cpu,
  DollarSign,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Loader2,
  Zap,
  Shield,
  TestTube,
  Image,
  Clock,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Types ---

interface ServiceHealth {
  status: "healthy" | "degraded" | "down" | "recovering" | "unknown";
  response_time_ms: number;
  consecutive_failures: number;
  error: string | null;
  last_success: number;
}

interface HealthReport {
  overall: string;
  services: Record<string, ServiceHealth>;
  alerts: Alert[];
  metrics: { total_services: number; healthy: number; down: number; avg_response_ms: number };
  timestamp: number;
}

interface Alert {
  severity: string;
  service: string;
  message: string;
  timestamp?: number;
  test_name?: string;
}

interface UATRun {
  run_id: string;
  started_at: string;
  completed_at: string | null;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  trigger: string;
  results: { name: string; status: string; error?: string }[];
}

interface CostData {
  current_session_cost: number;
  today_cost: number;
  this_month_cost: number;
  hourly_rate: number;
}

interface WorkerStatus {
  status: string;
  gpu_name: string | null;
  instance_id: string | null;
  uptime_seconds: number;
  jobs_completed: number;
  current_cost: number;
  hourly_rate: number;
}

// --- Helper Components ---

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { bg: string; text: string; label: string }> = {
    healthy: { bg: "bg-green-500/20", text: "text-green-400", label: "Healthy" },
    degraded: { bg: "bg-yellow-500/20", text: "text-yellow-400", label: "Degraded" },
    down: { bg: "bg-red-500/20", text: "text-red-400", label: "Down" },
    recovering: { bg: "bg-blue-500/20", text: "text-blue-400", label: "Recovering" },
    unknown: { bg: "bg-gray-500/20", text: "text-gray-400", label: "Unknown" },
  };
  const c = config[status] || config.unknown;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}

function OverallStatusBanner({ status }: { status: string }) {
  const isHealthy = status === "healthy";
  const isDegraded = status === "degraded";
  return (
    <div
      className={`rounded-lg border px-6 py-4 flex items-center gap-4 ${
        isHealthy
          ? "border-green-500/30 bg-green-500/5"
          : isDegraded
          ? "border-yellow-500/30 bg-yellow-500/5"
          : "border-red-500/30 bg-red-500/5"
      }`}
    >
      {isHealthy ? (
        <CheckCircle className="w-8 h-8 text-green-400" />
      ) : isDegraded ? (
        <AlertTriangle className="w-8 h-8 text-yellow-400" />
      ) : (
        <XCircle className="w-8 h-8 text-red-400" />
      )}
      <div>
        <h2 className="text-lg font-semibold text-white">
          Platform is {status === "healthy" ? "Healthy" : status === "degraded" ? "Degraded" : "Down"}
        </h2>
        <p className="text-sm text-gray-400">
          {isHealthy
            ? "All services operational. No active alerts."
            : isDegraded
            ? "Some services are experiencing issues."
            : "Critical services are unavailable."}
        </p>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, color }: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-4 h-4 ${color || "text-purple-400"}`} />
        <span className="text-xs text-gray-400 uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

function ServiceCard({ name, health }: { name: string; health: ServiceHealth }) {
  const statusIcon = {
    healthy: <CheckCircle className="w-4 h-4 text-green-400" />,
    degraded: <AlertTriangle className="w-4 h-4 text-yellow-400" />,
    down: <XCircle className="w-4 h-4 text-red-400" />,
    recovering: <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />,
    unknown: <Activity className="w-4 h-4 text-gray-400" />,
  };
  const displayName: Record<string, string> = {
    comfyui: "ComfyUI",
    ollama: "Ollama (LLM)",
    supabase: "Supabase (DB)",
    backblaze_b2: "Backblaze B2",
    elevenlabs: "ElevenLabs",
    worker_api: "Worker API",
  };

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        {statusIcon[health.status] || statusIcon.unknown}
        <div>
          <p className="text-sm font-medium text-white">{displayName[name] || name}</p>
          {health.error && (
            <p className="text-xs text-red-400 mt-0.5 max-w-[200px] truncate">{health.error}</p>
          )}
        </div>
      </div>
      <div className="text-right">
        <StatusBadge status={health.status} />
        {health.response_time_ms > 0 && (
          <p className="text-xs text-gray-500 mt-1">{health.response_time_ms}ms</p>
        )}
      </div>
    </div>
  );
}

function AlertRow({ alert }: { alert: Alert }) {
  const severityColor: Record<string, string> = {
    critical: "text-red-400 bg-red-500/10 border-red-500/20",
    warning: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20",
    info: "text-blue-400 bg-blue-500/10 border-blue-500/20",
  };
  const color = severityColor[alert.severity] || severityColor.info;
  return (
    <div className={`rounded border px-3 py-2 text-sm ${color}`}>
      <div className="flex items-center justify-between">
        <span className="font-medium">{alert.service}</span>
        <span className="text-xs opacity-70">{alert.severity.toUpperCase()}</span>
      </div>
      <p className="text-xs opacity-80 mt-0.5">{alert.message}</p>
    </div>
  );
}

function UATSection({ latestRun, loading, onRunTests }: {
  latestRun: UATRun | null;
  loading: boolean;
  onRunTests: () => void;
}) {
  const passRate = latestRun && latestRun.total > 0
    ? Math.round((latestRun.passed / latestRun.total) * 100)
    : 0;
  const statusColor = passRate >= 95 ? "text-green-400" : passRate >= 80 ? "text-yellow-400" : "text-red-400";

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TestTube className="w-4 h-4 text-purple-400" />
          <h3 className="text-sm font-medium text-white">UAT Test Results</h3>
        </div>
        <button
          onClick={onRunTests}
          disabled={loading}
          className="px-3 py-1 rounded text-xs bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50 flex items-center gap-1"
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
          Run Tests
        </button>
      </div>
      {latestRun ? (
        <div>
          <div className="flex items-baseline gap-2 mb-2">
            <span className={`text-2xl font-bold ${statusColor}`}>{passRate}%</span>
            <span className="text-xs text-gray-400">
              {latestRun.passed}/{latestRun.total} passed
              {latestRun.failed > 0 && ` · ${latestRun.failed} failed`}
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Clock className="w-3 h-3" />
            <span>Last run: {latestRun.completed_at ? new Date(latestRun.completed_at).toLocaleString() : "In progress..."}</span>
            <span className="text-gray-600">({latestRun.trigger})</span>
          </div>
          {latestRun.failed > 0 && (
            <div className="mt-2 space-y-1">
              {latestRun.results
                .filter((r) => r.status === "failed")
                .slice(0, 5)
                .map((r, i) => (
                  <div key={i} className="text-xs text-red-400 bg-red-500/5 rounded px-2 py-1">
                    {r.name}: {r.error?.slice(0, 80) || "failed"}
                  </div>
                ))}
            </div>
          )}
        </div>
      ) : (
        <p className="text-sm text-gray-500">No test runs yet. Click Run Tests to start.</p>
      )}
    </div>
  );
}

function GPUSection({ worker }: { worker: WorkerStatus | null }) {
  if (!worker || worker.status === "no_session") {
    return (
      <div className="rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Cpu className="w-4 h-4 text-purple-400" />
          <h3 className="text-sm font-medium text-white">GPU Worker</h3>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-gray-500" />
          <span className="text-sm text-gray-400">No active GPU worker</span>
        </div>
        <p className="text-xs text-gray-500 mt-2">Launch a worker from Admin to enable generation.</p>
      </div>
    );
  }

  const isReady = worker.status === "ready" || worker.status === "generating";
  const uptimeHrs = (worker.uptime_seconds / 3600).toFixed(1);

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-purple-400" />
          <h3 className="text-sm font-medium text-white">GPU Worker</h3>
        </div>
        <StatusBadge status={isReady ? "healthy" : worker.status === "error" ? "down" : "degraded"} />
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-xs text-gray-500">GPU</p>
          <p className="text-white font-medium">{worker.gpu_name || "Unknown"}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Status</p>
          <p className="text-white font-medium capitalize">{worker.status}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Uptime</p>
          <p className="text-white font-medium">{uptimeHrs}h</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Jobs Done</p>
          <p className="text-white font-medium">{worker.jobs_completed}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Session Cost</p>
          <p className="text-white font-medium">${worker.current_cost.toFixed(4)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Rate</p>
          <p className="text-white font-medium">${worker.hourly_rate.toFixed(3)}/hr</p>
        </div>
      </div>
    </div>
  );
}

function CostSection({ cost }: { cost: CostData | null }) {
  if (!cost) {
    return (
      <div className="rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="flex items-center gap-2 mb-3">
          <DollarSign className="w-4 h-4 text-purple-400" />
          <h3 className="text-sm font-medium text-white">Cost Tracking</h3>
        </div>
        <p className="text-sm text-gray-500">No cost data available.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-4">
      <div className="flex items-center gap-2 mb-3">
        <DollarSign className="w-4 h-4 text-purple-400" />
        <h3 className="text-sm font-medium text-white">Cost Tracking</h3>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-xs text-gray-500">This Session</p>
          <p className="text-white font-medium">${cost.current_session_cost.toFixed(4)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Today</p>
          <p className="text-white font-medium">${cost.today_cost.toFixed(4)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">This Month</p>
          <p className="text-white font-medium">${cost.this_month_cost.toFixed(4)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Hourly Rate</p>
          <p className="text-white font-medium">${cost.hourly_rate.toFixed(3)}/hr</p>
        </div>
      </div>
    </div>
  );
}

// --- Governance Section (merged from Ise page) ---

function GovernanceSection() {
  const [stuckJobs, setStuckJobs] = useState<{ stuck_job_actions: Array<{ service: string; action: string; reason: string }>; budget_alerts: Array<{ reason: string }> } | null>(null);
  const [decisions, setDecisions] = useState<Array<{ decision_type: string; provider: string; model: string; latency_ms: number; input_summary: string; created_at: string }>>([]);
  const [loaded, setLoaded] = useState(false);

  async function loadGovernance() {
    setLoaded(true);
    const [stuck, decs] = await Promise.allSettled([
      authFetch(`${API_BASE}/aios/v1/health/check-stuck-jobs`, { method: "POST" }).then((r) => r.json()),
      authFetch(`${API_BASE}/aios/v1/decisions?limit=10`).then((r) => r.json()),
    ]);
    if (stuck.status === "fulfilled") setStuckJobs(stuck.value);
    if (decs.status === "fulfilled" && Array.isArray(decs.value)) setDecisions(decs.value);
  }

  if (!loaded) {
    return (
      <div className="rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-medium text-white">Governance & Diagnostics</h3>
            <span className="text-xs text-gray-500">Stuck jobs, budget, AI decisions</span>
          </div>
          <button
            onClick={loadGovernance}
            className="px-3 py-1 rounded text-xs bg-purple-600 hover:bg-purple-700 text-white flex items-center gap-1"
          >
            <Zap className="w-3 h-3" /> Load
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stuck Jobs + Budget */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-lg border border-white/10 bg-white/5 p-4">
          <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-yellow-400" /> Stuck Jobs
          </h3>
          {stuckJobs && stuckJobs.stuck_job_actions.length > 0 ? (
            <div className="space-y-2">
              {stuckJobs.stuck_job_actions.map((a, i) => (
                <p key={i} className="text-xs text-yellow-400 bg-yellow-500/5 rounded px-2 py-1">{a.reason}</p>
              ))}
            </div>
          ) : (
            <p className="text-xs text-green-400 flex items-center gap-1">
              <CheckCircle className="w-3 h-3" /> No stuck jobs
            </p>
          )}
        </div>
        <div className="rounded-lg border border-white/10 bg-white/5 p-4">
          <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-emerald-400" /> Budget Alerts
          </h3>
          {stuckJobs && stuckJobs.budget_alerts.length > 0 ? (
            <div className="space-y-2">
              {stuckJobs.budget_alerts.map((a, i) => (
                <p key={i} className="text-xs text-amber-400 bg-amber-500/5 rounded px-2 py-1">{a.reason}</p>
              ))}
            </div>
          ) : (
            <p className="text-xs text-green-400 flex items-center gap-1">
              <CheckCircle className="w-3 h-3" /> Budget within limits
            </p>
          )}
        </div>
      </div>

      {/* Recent AI Decisions */}
      {decisions.length > 0 && (
        <div className="rounded-lg border border-white/10 bg-white/5 p-4">
          <h3 className="text-sm font-medium text-white mb-3">Recent AI Decisions</h3>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {decisions.map((d, i) => (
              <div key={i} className="flex items-center justify-between rounded border border-white/5 bg-white/[0.02] px-3 py-2">
                <div className="min-w-0">
                  <p className="text-xs text-white truncate">{d.input_summary || d.decision_type}</p>
                  <p className="text-[10px] text-gray-500">{d.provider}/{d.model} · {d.latency_ms}ms</p>
                </div>
                <span className="text-[10px] text-gray-600 shrink-0">
                  {d.created_at ? new Date(d.created_at).toLocaleTimeString() : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// --- Main Page Component ---

export default function HealthDashboardPage() {
  const [healthReport, setHealthReport] = useState<HealthReport | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [latestUAT, setLatestUAT] = useState<UATRun | null>(null);
  const [worker, setWorker] = useState<WorkerStatus | null>(null);
  const [cost, setCost] = useState<CostData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [runningTests, setRunningTests] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const loadAll = useCallback(async () => {
    const results = await Promise.allSettled([
      authFetch(`${API_BASE}/aios/v1/health/full`).then((r) => r.json()),
      authFetch(`${API_BASE}/aios/v1/health/alerts`).then((r) => r.json()),
      authFetch(`${API_BASE}/aios/v1/ise/uat/latest`).then((r) => r.json()),
      authFetch(`${API_BASE}/api/v1/infrastructure/dashboard`).then((r) => r.json()),
    ]);

    if (results[0].status === "fulfilled") setHealthReport(results[0].value);
    if (results[1].status === "fulfilled") setAlerts(results[1].value?.alerts || []);
    if (results[2].status === "fulfilled" && results[2].value?.run_id) {
      setLatestUAT(results[2].value);
    }
    if (results[3].status === "fulfilled") {
      const dash = results[3].value;
      if (dash?.worker) setWorker(dash.worker);
      if (dash?.cost) setCost(dash.cost);
    }

    setLastRefresh(new Date());
  }, []);

  useEffect(() => {
    setLoading(true);
    loadAll().finally(() => setLoading(false));

    // Auto-refresh every 30 seconds
    const interval = setInterval(loadAll, 30000);
    return () => clearInterval(interval);
  }, [loadAll]);

  async function handleRefresh() {
    setRefreshing(true);
    await loadAll();
    setRefreshing(false);
  }

  async function handleRunTests() {
    setRunningTests(true);
    try {
      const resp = await authFetch(`${API_BASE}/aios/v1/ise/uat/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (resp.ok) {
        const result = await resp.json();
        if (result?.run_id) setLatestUAT(result);
      }
    } catch {}
    setRunningTests(false);
    // Refresh alerts after test run
    await loadAll();
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a1a] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a1a] p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              <Activity className="w-6 h-6 text-purple-400" />
              Application Health
            </h1>
            <p className="text-sm text-gray-400 mt-1">
              Real-time platform health monitored by Hermes + Obaluaye
            </p>
          </div>
          <div className="flex items-center gap-3">
            {lastRefresh && (
              <span className="text-xs text-gray-500">
                Updated {lastRefresh.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="p-2 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white disabled:opacity-50"
              aria-label="Refresh health data"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>

        {/* Overall Status Banner */}
        <OverallStatusBanner status={healthReport?.overall || "unknown"} />

        {/* Top Stats Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={Server}
            label="Services"
            value={`${healthReport?.metrics?.healthy || 0}/${healthReport?.metrics?.total_services || 0}`}
            sub="healthy"
            color="text-green-400"
          />
          <StatCard
            icon={AlertTriangle}
            label="Alerts"
            value={alerts.length}
            sub={alerts.filter((a) => a.severity === "critical").length > 0 ? "critical alerts active" : "none critical"}
            color={alerts.length > 0 ? "text-yellow-400" : "text-green-400"}
          />
          <StatCard
            icon={Image}
            label="Generations"
            value={worker?.jobs_completed || 0}
            sub="this session"
            color="text-purple-400"
          />
          <StatCard
            icon={DollarSign}
            label="Cost Today"
            value={`$${(cost?.today_cost || 0).toFixed(3)}`}
            sub={cost?.hourly_rate ? `$${cost.hourly_rate.toFixed(3)}/hr` : "idle"}
            color="text-emerald-400"
          />
        </div>

        {/* Main Grid: Services + GPU + Cost */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Services Column */}
          <div className="space-y-3">
            <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide flex items-center gap-2">
              <Server className="w-3.5 h-3.5" />
              Services
            </h3>
            {healthReport?.services ? (
              Object.entries(healthReport.services).map(([name, health]) => (
                <ServiceCard key={name} name={name} health={health} />
              ))
            ) : (
              <p className="text-sm text-gray-500">No health data available.</p>
            )}
          </div>

          {/* GPU + Cost Column */}
          <div className="space-y-4">
            <GPUSection worker={worker} />
            <CostSection cost={cost} />
          </div>

          {/* Tests + Alerts Column */}
          <div className="space-y-4">
            <UATSection latestRun={latestUAT} loading={runningTests} onRunTests={handleRunTests} />

            {/* Alert Feed */}
            <div className="rounded-lg border border-white/10 bg-white/5 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Shield className="w-4 h-4 text-purple-400" />
                <h3 className="text-sm font-medium text-white">Alert Feed</h3>
                <span className="text-xs text-gray-500">Ise + Red Team</span>
              </div>
              {alerts.length > 0 ? (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {alerts.map((alert, i) => (
                    <AlertRow key={i} alert={alert} />
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-2 text-sm text-green-400">
                  <CheckCircle className="w-4 h-4" />
                  <span>No active alerts</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Response Times */}
        {healthReport?.services && (
          <div className="rounded-lg border border-white/10 bg-white/5 p-4">
            <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2">
              <Zap className="w-3.5 h-3.5" />
              Response Times
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {Object.entries(healthReport.services).map(([name, svc]) => (
                <div key={name} className="text-center">
                  <p className="text-xs text-gray-500 mb-1 capitalize">{name.replace("_", " ")}</p>
                  <p className={`text-lg font-bold ${
                    svc.response_time_ms < 100 ? "text-green-400" :
                    svc.response_time_ms < 500 ? "text-yellow-400" : "text-red-400"
                  }`}>
                    {svc.response_time_ms > 0 ? `${svc.response_time_ms}ms` : "—"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Governance: Stuck Jobs + Budget Alerts */}
        <GovernanceSection />
      </div>
    </div>
  );
}
