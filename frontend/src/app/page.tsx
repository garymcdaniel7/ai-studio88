"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  FolderOpen,
  Cpu,
  DollarSign,
  Image,
  Calendar,
  Server,
  ArrowUpRight,
  Brain,
  Zap,
  TrendingUp,
  AlertCircle,
  Loader2,
} from "lucide-react";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip";
import {
  getInfrastructureStatus,
  getServiceConnections,
  getTalent,
  getJobs,
  checkHealth,
} from "@/lib/api";

function MetricCard({
  icon: Icon,
  label,
  value,
  subtitle,
  color,
  tooltip,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  subtitle: string;
  color: string;
  tooltip?: string;
}) {
  const card = (
    <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 cursor-default">
      <div className="flex items-center gap-3">
        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${color}`}>
          <Icon className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className="text-2xl font-bold text-white">{value}</p>
          <p className="text-xs text-gray-500">{subtitle}</p>
        </div>
      </div>
    </div>
  );

  if (!tooltip) return card;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger render={<div />}>
          {card}
        </TooltipTrigger>
        <TooltipContent>{tooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export default function HomePage() {
  const [loading, setLoading] = useState(true);
  const [apiOnline, setApiOnline] = useState(false);
  const [infra, setInfra] = useState<any>(null);
  const [services, setServices] = useState<any>(null);
  const [talentCount, setTalentCount] = useState(0);
  const [jobsData, setJobsData] = useState<any[]>([]);

  useEffect(() => {
    let retries = 0;
    async function load() {
      try {
        await checkHealth();
        setApiOnline(true);

        const [infraData, svcData, talent, jobs] = await Promise.allSettled([
          getInfrastructureStatus(),
          getServiceConnections(),
          getTalent(),
          getJobs(),
        ]);

        if (infraData.status === "fulfilled") setInfra(infraData.value);
        if (svcData.status === "fulfilled") setServices(svcData.value);
        if (talent.status === "fulfilled") setTalentCount(Array.isArray(talent.value) ? talent.value.length : 0);
        if (jobs.status === "fulfilled") setJobsData(Array.isArray(jobs.value) ? jobs.value : []);
      } catch {
        if (retries < 3) {
          retries++;
          setTimeout(load, 2000 * retries);
          return;
        }
        setApiOnline(false);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const worker = infra?.worker || {};
  const cost = infra?.cost || {};
  const connectedServices = services?.summary?.connected || 0;

  // Job stats
  const completedJobs = jobsData.filter((j) => j.status === "completed").length;
  const runningJobs = jobsData.filter((j) => j.status === "running").length;
  const queuedJobs = jobsData.filter((j) => j.status === "queued").length;
  const failedJobs = jobsData.filter((j) => j.status === "failed").length;
  const totalJobs = jobsData.length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* API Status Warning */}
      {!apiOnline && (
        <div className="flex items-center gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-5 py-3">
          <AlertCircle className="h-5 w-5 text-amber-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-300">Backend not connected</p>
            <p className="text-xs text-amber-400/60 mt-0.5">
              Start the API: <code className="bg-black/30 px-1.5 py-0.5 rounded text-amber-300">uv run uvicorn backend.main:app --reload</code>
            </p>
          </div>
        </div>
      )}

      {/* Hero Greeting */}
      <div>
        <h1 className="text-2xl font-bold text-white">Good evening, Gary 👋</h1>
        <p className="text-gray-500">Your AI Studio is ready to create something amazing.</p>
      </div>

      {/* Quick Actions */}
      <div className="flex gap-3">
        <Link href="/create" className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 transition-colors">
          🆕 New Project
        </Link>
        <Link href="/brain" className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06] transition-colors">
          🧠 AI Brain Chat
        </Link>
        <Link href="/assets" className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06] transition-colors">
          📤 Upload Asset
        </Link>
        <Link href="/create" className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06] transition-colors">
          🎨 Create Image
        </Link>
      </div>

      {/* Metrics Row — LIVE DATA */}
      <div className="grid grid-cols-6 gap-4">
        <MetricCard icon={FolderOpen} label="Active Projects" value={String(jobsData.filter(j => j.status === "running").length || 0)} subtitle="In progress" color="bg-blue-600" tooltip={jobsData.filter(j => j.status === "running").map(j => j.name || j.type || "Job").join(", ") || "No active projects"} />
        <MetricCard icon={Cpu} label="Jobs" value={String(totalJobs)} subtitle={`${runningJobs} running`} color="bg-purple-600" tooltip={jobsData.length ? jobsData.slice(0, 5).map(j => `${j.name || j.type || "Job"} (${j.status})`).join(", ") : "No jobs"} />
        <MetricCard icon={DollarSign} label="GPU Spend (hr)" value={`$${cost?.current_session_cost?.toFixed(2) || "0.00"}`} subtitle={worker.status === "ready" ? `${worker.gpu_name}` : "No worker"} color="bg-green-600" tooltip={`Session cost: $${cost?.current_session_cost?.toFixed(2) || "0.00"}`} />
        <MetricCard icon={Image} label="Talent" value={String(talentCount)} subtitle="AI personas" color="bg-amber-600" tooltip={`${talentCount} AI talent personas available`} />
        <MetricCard icon={Calendar} label="Services Online" value={`${connectedServices}/7`} subtitle="All providers" color="bg-pink-600" tooltip={`${connectedServices} of 7 services connected`} />
        <MetricCard icon={Server} label="Worker" value={worker.status === "ready" ? "Online" : "Offline"} subtitle={worker.gpu_name || "Launch to connect"} color="bg-teal-600" tooltip={worker.status === "ready" ? `${worker.gpu_name} active` : "No GPU worker running"} />
      </div>

      {/* Three Column Grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Active Productions */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Active Productions</h3>
            <Link href="/production" className="text-xs text-purple-400 hover:text-purple-300">View all</Link>
          </div>
          {jobsData.filter((j) => j.status === "running" || j.status === "queued").length > 0 ? (
            <div className="space-y-3">
              {jobsData
                .filter((j) => j.status === "running" || j.status === "queued")
                .slice(0, 5)
                .map((p, idx) => (
                  <div key={p.id || idx} className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-purple-900/40 to-blue-900/40 flex items-center justify-center">
                      <Cpu className="h-4 w-4 text-purple-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">{p.name || p.type || "Untitled Job"}</p>
                      <p className="text-xs text-gray-500">{p.status}</p>
                    </div>
                    <span className={`text-xs ${p.status === "running" ? "text-green-400" : "text-amber-400"}`}>
                      {p.status === "running" ? "In progress" : "Queued"}
                    </span>
                  </div>
                ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <FolderOpen className="h-8 w-8 text-gray-600 mb-2" />
              <p className="text-sm text-gray-400">No active productions</p>
              <p className="text-xs text-gray-600 mt-1">Start a new project to see it here.</p>
            </div>
          )}
        </div>

        {/* Jobs Overview — LIVE */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Jobs Overview</h3>
          </div>
          <div className="flex items-center justify-center py-4">
            <div className="relative h-32 w-32">
              <div className="absolute inset-0 flex items-center justify-center">
                <div>
                  <p className="text-3xl font-bold text-white text-center">{totalJobs}</p>
                  <p className="text-xs text-gray-500 text-center">Total Jobs</p>
                </div>
              </div>
              <svg className="h-32 w-32 -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="14" fill="none" stroke="#1a1a3e" strokeWidth="4" />
                <circle cx="18" cy="18" r="14" fill="none" stroke="#10b981" strokeWidth="4" strokeDasharray={`${totalJobs ? (completedJobs/totalJobs)*88 : 0} 100`} />
                <circle cx="18" cy="18" r="14" fill="none" stroke="#6366f1" strokeWidth="4" strokeDasharray={`${totalJobs ? (runningJobs/totalJobs)*88 : 0} 100`} strokeDashoffset={`-${totalJobs ? (completedJobs/totalJobs)*88 : 0}`} />
              </svg>
            </div>
          </div>
          <div className="mt-2 space-y-1.5">
            {[
              { label: "Completed", value: completedJobs, color: "bg-green-500" },
              { label: "Running", value: runningJobs, color: "bg-indigo-500" },
              { label: "Queued", value: queuedJobs, color: "bg-amber-500" },
              { label: "Failed", value: failedJobs, color: "bg-red-500" },
            ].map((s) => (
              <div key={s.label} className="flex items-center gap-2 text-xs">
                <span className={`h-2 w-2 rounded-full ${s.color}`} />
                <span className="text-gray-400">{s.label}</span>
                <span className="ml-auto text-gray-300">{s.value}</span>
              </div>
            ))}
          </div>
          <Link href="/production" className="mt-3 w-full block text-center rounded-lg border border-white/[0.08] py-2 text-xs text-gray-400 hover:bg-white/[0.03]">
            Open Job Queue
          </Link>
        </div>

        {/* AI Brain Suggestions */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">AI Brain Suggestions</h3>
            <Link href="/brain" className="text-xs text-purple-400 hover:text-purple-300">View all</Link>
          </div>
          <div className="space-y-3">
            {[
              { icon: Zap, title: "Reuse FLUX workflow", desc: "You used this workflow in your last 3 image projects." },
              { icon: TrendingUp, title: "Optimize GPU costs", desc: "Switch to Spot instances to save up to 32%." },
              { icon: ArrowUpRight, title: "Upscale ready", desc: "12 assets can be upscaled to improve quality." },
            ].map((s) => (
              <div key={s.title} className="flex items-start gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] p-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-600/20">
                  <s.icon className="h-4 w-4 text-purple-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">{s.title}</p>
                  <p className="text-xs text-gray-500">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
          <Link href="/brain" className="mt-3 w-full block text-center rounded-lg bg-purple-600/10 py-2 text-xs text-purple-400 hover:bg-purple-600/20">
            Open Brain
          </Link>
        </div>
      </div>

      {/* System Status Bar — LIVE */}
      <div className="flex items-center gap-6 rounded-xl border border-white/[0.06] bg-[#12122a] px-5 py-3">
        <span className="text-xs font-medium text-gray-400">System Status</span>
        {services?.services ? (
          Object.entries(services.services).map(([name, info]: [string, any]) => (
            <div key={name} className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${info.connected ? "bg-green-500" : "bg-gray-600"}`} />
              <span className="text-xs text-gray-300">{name.replace("_", " ")}</span>
              <span className={`text-xs ${info.connected ? "text-green-400" : "text-gray-600"}`}>
                {info.connected ? "Online" : "Offline"}
              </span>
            </div>
          ))
        ) : (
          <span className="text-xs text-gray-600">Loading...</span>
        )}
        <Link href="/admin" className="ml-auto text-xs text-purple-400 hover:text-purple-300">
          View all systems →
        </Link>
      </div>
    </div>
  );
}
