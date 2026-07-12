"use client";

import { useState } from "react";
import { Shield, Play, CheckCircle, XCircle, AlertTriangle, Loader2, RefreshCw } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

interface HealthCheck {
  name: string;
  status: "healthy" | "degraded" | "down" | "unknown";
  response_time_ms: number;
  error: string | null;
}

interface Alert {
  severity: string;
  service: string;
  message: string;
}

export default function IsePage() {
  const [loading, setLoading] = useState(false);
  const [healthReport, setHealthReport] = useState<{
    overall: string;
    services: Record<string, HealthCheck>;
    alerts: Alert[];
    metrics: Record<string, number>;
  } | null>(null);
  const [stuckJobs, setStuckJobs] = useState<{ stuck_job_actions: unknown[]; budget_alerts: unknown[] } | null>(null);
  const [decisions, setDecisions] = useState<unknown[]>([]);
  const [approvals, setApprovals] = useState<{ pending: number } | null>(null);
  const [diagnosis, setDiagnosis] = useState<{ service: string; diagnosis: string; fix: string; fix_action?: string; auto_fixable: boolean; source: string; prevention?: string } | null>(null);

  async function runHealthScan() {
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/aios/v1/health/full`);
      if (resp.ok) setHealthReport(await resp.json());
    } catch {}
    setLoading(false);
  }

  async function checkStuckJobs() {
    try {
      const resp = await fetch(`${API_BASE}/aios/v1/health/check-stuck-jobs`, { method: "POST" });
      if (resp.ok) setStuckJobs(await resp.json());
    } catch {}
  }

  async function loadDecisions() {
    try {
      const resp = await fetch(`${API_BASE}/aios/v1/decisions?limit=10`);
      if (resp.ok) setDecisions(await resp.json());
    } catch {}
  }

  async function loadApprovals() {
    try {
      const resp = await fetch(`${API_BASE}/aios/v1/approvals/count`);
      if (resp.ok) setApprovals(await resp.json());
    } catch {}
  }

  async function runAll() {
    setLoading(true);
    await Promise.all([runHealthScan(), checkStuckJobs(), loadDecisions(), loadApprovals()]);
    setLoading(false);
  }

  const statusIcon = (status: string) => {
    switch (status) {
      case "healthy": return <CheckCircle className="h-4 w-4 text-green-400" />;
      case "degraded": return <AlertTriangle className="h-4 w-4 text-amber-400" />;
      case "down": return <XCircle className="h-4 w-4 text-red-400" />;
      default: return <div className="h-4 w-4 rounded-full bg-gray-600" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <Shield className="h-6 w-6 text-purple-400" />
            Ise — Quality & Reliability Agent
          </h1>
          <p className="text-sm text-gray-500">
            Platform diagnostics, health monitoring, UAT scanning, and decision audit.
          </p>
        </div>
        <button
          onClick={runAll}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {loading ? "Scanning..." : "Run Full Scan"}
        </button>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
          <p className="text-xs text-gray-500">Overall Status</p>
          <p className={`text-xl font-bold mt-1 ${
            healthReport?.overall === "healthy" ? "text-green-400" :
            healthReport?.overall === "degraded" ? "text-amber-400" :
            healthReport?.overall === "down" ? "text-red-400" : "text-gray-400"
          }`}>
            {healthReport?.overall?.toUpperCase() || "—"}
          </p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
          <p className="text-xs text-gray-500">Services Healthy</p>
          <p className="text-xl font-bold text-green-400 mt-1">
            {healthReport?.metrics?.healthy ?? "—"}/{healthReport?.metrics?.total_services ?? "—"}
          </p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
          <p className="text-xs text-gray-500">Active Alerts</p>
          <p className="text-xl font-bold text-amber-400 mt-1">
            {healthReport?.alerts?.length ?? "—"}
          </p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
          <p className="text-xs text-gray-500">Pending Approvals</p>
          <p className="text-xl font-bold text-purple-400 mt-1">
            {approvals?.pending ?? "—"}
          </p>
        </div>
      </div>

      {/* Service Health */}
      {healthReport && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-white">Service Health</h2>
            <button onClick={runHealthScan} className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1">
              <RefreshCw className="h-3 w-3" /> Refresh
            </button>
          </div>
          <div className="space-y-2">
            {Object.entries(healthReport.services).map(([name, svc]) => (
              <div key={name} className="flex items-center justify-between rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3">
                <div className="flex items-center gap-3">
                  {statusIcon(svc.status)}
                  <div>
                    <p className="text-sm font-medium text-white capitalize">{name.replace(/_/g, " ")}</p>
                    {svc.error && <p className="text-[10px] text-red-400">{svc.error}</p>}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-500">{svc.response_time_ms}ms</span>
                  <span className={`rounded px-2 py-0.5 text-[10px] font-medium ${
                    svc.status === "healthy" ? "bg-green-500/10 text-green-400" :
                    svc.status === "degraded" ? "bg-amber-500/10 text-amber-400" :
                    svc.status === "down" ? "bg-red-500/10 text-red-400" : "bg-gray-500/10 text-gray-400"
                  }`}>
                    {svc.status}
                  </span>
                  {(svc.status === "degraded" || svc.status === "down") && (
                    <button
                      onClick={async () => {
                        try {
                          const resp = await fetch(`${API_BASE}/aios/v1/health/diagnose`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ service: name, error: svc.error || "unreachable" }),
                          });
                          if (resp.ok) {
                            const diag = await resp.json();
                            setDiagnosis({ service: name, ...diag });
                          } else {
                            setDiagnosis({ service: name, diagnosis: svc.error || "Service unreachable", fix: "Check service logs and restart manually.", auto_fixable: false, source: "error" });
                          }
                        } catch {
                          setDiagnosis({ service: name, diagnosis: "Could not reach AIOS backend for diagnosis.", fix: "Ensure backend is running on port 8000.", auto_fixable: false, source: "error" });
                        }
                      }}
                      className="rounded px-2 py-0.5 text-[10px] font-medium bg-purple-600/20 text-purple-400 hover:bg-purple-600/40"
                    >
                      Diagnose & Fix
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Alerts */}
      {healthReport?.alerts && healthReport.alerts.length > 0 && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-5">
          <h2 className="text-sm font-semibold text-red-300 mb-3">Active Alerts</h2>
          <div className="space-y-2">
            {healthReport.alerts.map((alert, i) => (
              <div key={i} className="flex items-start gap-2 text-sm">
                <AlertTriangle className="h-4 w-4 text-red-400 mt-0.5 shrink-0" />
                <div>
                  <span className="text-red-300 font-medium">{alert.service}:</span>{" "}
                  <span className="text-gray-300">{alert.message}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Diagnosis Panel */}
      {diagnosis && (
        <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-purple-300">Diagnosis: {diagnosis.service}</h2>
            <button onClick={() => setDiagnosis(null)} className="text-xs text-gray-500 hover:text-white">&times; Close</button>
          </div>
          <div className="space-y-3">
            <div>
              <p className="text-[10px] text-gray-500 uppercase">Root Cause ({diagnosis.source})</p>
              <p className="text-sm text-white mt-1">{diagnosis.diagnosis}</p>
            </div>
            <div>
              <p className="text-[10px] text-gray-500 uppercase">Suggested Fix</p>
              <p className="text-sm text-gray-300 mt-1 font-mono bg-white/[0.03] rounded-lg px-3 py-2">{diagnosis.fix}</p>
            </div>
            {diagnosis.prevention && (
              <div>
                <p className="text-[10px] text-gray-500 uppercase">Prevention</p>
                <p className="text-xs text-gray-400 mt-1">{diagnosis.prevention}</p>
              </div>
            )}
            {diagnosis.auto_fixable && diagnosis.fix_action && (
              <button
                onClick={async () => {
                  const resp = await fetch(`${API_BASE}/aios/v1/health/auto-fix`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ fix_action: diagnosis.fix_action, service: diagnosis.service }),
                  });
                  const result = await resp.json();
                  if (result.success) {
                    setDiagnosis(null);
                    runHealthScan();
                  } else {
                    setDiagnosis({ ...diagnosis, diagnosis: `Fix attempted but failed: ${result.message}`, auto_fixable: false });
                  }
                }}
                className="w-full rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
              >
                Apply Fix Automatically
              </button>
            )}
          </div>
        </div>
      )}

      {/* Budget & Stuck Jobs */}
      {stuckJobs && (
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Stuck Jobs</h3>
            {stuckJobs.stuck_job_actions.length > 0 ? (
              <div className="space-y-2">
                {(stuckJobs.stuck_job_actions as Array<{service: string; action: string; reason: string}>).map((a, i) => (
                  <p key={i} className="text-xs text-gray-400">{a.reason}</p>
                ))}
              </div>
            ) : (
              <p className="text-xs text-green-400">No stuck jobs</p>
            )}
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Budget Alerts</h3>
            {stuckJobs.budget_alerts.length > 0 ? (
              <div className="space-y-2">
                {(stuckJobs.budget_alerts as Array<{reason: string}>).map((a, i) => (
                  <p key={i} className="text-xs text-amber-400">{a.reason}</p>
                ))}
              </div>
            ) : (
              <p className="text-xs text-green-400">Budget within limits</p>
            )}
          </div>
        </div>
      )}

      {/* Recent AI Decisions */}
      {Array.isArray(decisions) && decisions.length > 0 && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <h2 className="text-sm font-semibold text-white mb-3">Recent AI Decisions</h2>
          <div className="space-y-2">
            {(decisions as Array<{decision_type: string; provider: string; model: string; latency_ms: number; input_summary: string; created_at: string}>).map((d, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-2">
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

      {/* No scan yet */}
      {!healthReport && !loading && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-12 text-center">
          <Shield className="h-12 w-12 text-gray-600 mx-auto mb-4" />
          <p className="text-sm text-gray-400">Click "Run Full Scan" to check platform health</p>
          <p className="text-xs text-gray-600 mt-1">
            Ise checks: ComfyUI, Ollama, Supabase, B2, ElevenLabs, Worker API, stuck jobs, and budget
          </p>
        </div>
      )}
    </div>
  );
}
