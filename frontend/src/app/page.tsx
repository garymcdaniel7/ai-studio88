"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Onboarding } from "@/components/onboarding";
import {
  FolderOpen,
  Cpu,
  DollarSign,
  Image as ImageIcon,
  Calendar,
  Server,
  ArrowUpRight,
  Zap,
  TrendingUp,
  AlertCircle,
  Loader2,
  X,
  Check,
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
  getVastStatus,
  getRunPodStatus,
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
  const [infra, setInfra] = useState<Record<string, Record<string, unknown>> | null>(null);
  const [services, setServices] = useState<Record<string, Record<string, unknown>> | null>(null);
  const [talentCount, setTalentCount] = useState(0);
  const [jobsData, setJobsData] = useState<Record<string, unknown>[]>([]);
  const [recentAssets, setRecentAssets] = useState<{id: string; filename: string; public_url?: string; metadata?: Record<string, unknown>; created_at?: string}[]>([]);
  const [showSuggestionsModal, setShowSuggestionsModal] = useState(false);
  const [vastStatus, setVastStatus] = useState<Record<string, unknown> | null>(null);
  const [runpodStatus, setRunpodStatus] = useState<Record<string, unknown> | null>(null);
  const [dismissedSuggestions, setDismissedSuggestions] = useState<string[]>(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("dismissed_suggestions");
      return stored ? JSON.parse(stored) : [];
    }
    return [];
  });

  const allSuggestions = [
    { id: "try-model", icon: Zap, title: "Try a new model", desc: "Explore Flux 2 Klein for fast, high-quality 4-step generation." },
    { id: "optimize-gpu", icon: TrendingUp, title: "Optimize GPU costs", desc: "Use Spot instances or smaller models to reduce spend." },
    { id: "create-talent", icon: ArrowUpRight, title: "Create your first talent", desc: "Set up an AI persona to generate consistent content." },
    { id: "batch-render", icon: Cpu, title: "Batch render overnight", desc: "Queue multiple jobs to run while you sleep." },
    { id: "explore-presets", icon: ImageIcon, title: "Explore creative recipes", desc: "Use built-in presets for portrait, product, or cinematic styles." },
    { id: "schedule-posts", icon: Calendar, title: "Plan your calendar", desc: "Draft and schedule posts from the Publish page." },
  ];

  const visibleSuggestions = allSuggestions.filter((s) => !dismissedSuggestions.includes(s.id));

  function toggleDismiss(id: string) {
    setDismissedSuggestions((prev) => {
      const next = prev.includes(id) ? prev.filter((d) => d !== id) : [...prev, id];
      localStorage.setItem("dismissed_suggestions", JSON.stringify(next));
      return next;
    });
  }

  useEffect(() => {
    let retries = 0;
    async function load() {
      try {
        await checkHealth();
        setApiOnline(true);

        const [infraData, svcData, talent, jobs, vastData, runpodData] = await Promise.allSettled([
          getInfrastructureStatus(),
          getServiceConnections(),
          getTalent(),
          getJobs(),
          getVastStatus(),
          getRunPodStatus(),
        ]);

        if (infraData.status === "fulfilled") setInfra(infraData.value as Record<string, Record<string, unknown>>);
        if (svcData.status === "fulfilled") setServices(svcData.value as Record<string, Record<string, unknown>>);
        if (talent.status === "fulfilled") setTalentCount(Array.isArray(talent.value) ? talent.value.length : 0);
        if (jobs.status === "fulfilled") setJobsData(Array.isArray(jobs.value) ? jobs.value : []);
        if (vastData.status === "fulfilled") setVastStatus(vastData.value);
        if (runpodData.status === "fulfilled") setRunpodStatus(runpodData.value);

        // Fetch recent generated assets for the gallery
        try {
          const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
          const assetsResp = await fetch(`${apiBase}/api/v1/assets`);
          if (assetsResp.ok) {
            const assetsData = await assetsResp.json();
            const items = Array.isArray(assetsData) ? assetsData : assetsData.assets || [];
            // Only show generated images (have metadata.source === "ai_generation" or type === "generation")
            const generated = items.filter((a: Record<string, unknown>) =>
              a.type === "generation" || (a.metadata as Record<string, unknown>)?.source === "ai_generation"
            ).slice(0, 6);
            setRecentAssets(generated);
          }
        } catch {}
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
  const svcSummary = services?.summary;
  const connectedServices = (svcSummary?.connected as number) || 0;

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

      {/* Hero Greeting — always renders first */}
      <div>
        <h1 className="text-2xl font-bold text-white">
          {(() => {
            const hour = new Date().getHours();
            if (hour < 12) return "Good morning";
            if (hour < 17) return "Good afternoon";
            return "Good evening";
          })()}  👋
        </h1>
        <p className="text-gray-500">What would you like to create today?</p>
      </div>

      {/* Onboarding — shows for new users (no talent, no jobs) */}
      <Onboarding talentCount={talentCount} jobCount={totalJobs} />

      {/* Brain Quick Start — the primary CTA */}
      <div className="rounded-2xl border border-purple-500/20 bg-gradient-to-r from-purple-900/10 to-blue-900/10 p-6">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-purple-600/20">
            <span className="text-2xl">🧠</span>
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-white">Ask your AI Creative Director</h2>
            <p className="text-sm text-gray-400">Describe what you want to create. The Brain handles the rest.</p>
          </div>
          <Link href="/brain" className="rounded-lg bg-purple-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-purple-700 transition-colors">
            Open Brain
          </Link>
        </div>
        <div className="mt-4 flex gap-2 flex-wrap">
          {["Create a luxury campaign", "Generate product photos", "Train a new talent", "Animate these images", "Write a script"].map((suggestion) => (
            <Link
              key={suggestion}
              href={`/brain?prompt=${encodeURIComponent(suggestion)}`}
              className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-400 hover:text-white hover:border-purple-500/30 transition-colors"
            >
              {suggestion}
            </Link>
          ))}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="flex gap-3">
        <Link href="/create" className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 transition-colors">
          Create Image
        </Link>
        <Link href="/talent" className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06] transition-colors">
          Manage Talent
        </Link>
        <Link href="/training" className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06] transition-colors">
          Train LoRA
        </Link>
        <Link href="/publish" className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-300 hover:bg-white/[0.06] transition-colors">
          Publish Content
        </Link>
      </div>

      {/* Metrics Row — LIVE DATA */}
      <div className="grid grid-cols-6 gap-4">
        <MetricCard icon={FolderOpen} label="Active Projects" value={String(jobsData.filter(j => j.status === "running").length || 0)} subtitle="In progress" color="bg-blue-600" tooltip={jobsData.filter(j => j.status === "running").map(j => (j.name as string) || (j.type as string) || "Job").join(", ") || "No active projects"} />
        <MetricCard icon={Cpu} label="Jobs" value={String(totalJobs)} subtitle={`${runningJobs} running`} color="bg-purple-600" tooltip={jobsData.length ? jobsData.slice(0, 5).map(j => `${(j.name as string) || (j.type as string) || "Job"} (${j.status})`).join(", ") : "No jobs"} />
        <MetricCard icon={DollarSign} label="GPU Spend (today)" value={`$${((cost?.today as number) || (cost?.current_session_cost as number) || 0).toFixed(2)}`} subtitle={`Month: $${((cost?.this_month as number) || 0).toFixed(2)}`} color="bg-green-600" tooltip={`Today: $${((cost?.today as number) || 0).toFixed(2)} | This month: $${((cost?.this_month as number) || 0).toFixed(2)} | ${(cost?.generation_count as number) || 0} jobs`} />
        <MetricCard icon={ImageIcon} label="Talent" value={String(talentCount)} subtitle="AI personas" color="bg-amber-600" tooltip={`${talentCount} AI talent personas available`} />
        <MetricCard icon={Calendar} label="Services Online" value={`${connectedServices}/${(svcSummary?.total_services as number) || 9}`} subtitle="All providers" color="bg-pink-600" tooltip={`${connectedServices} of ${(svcSummary?.total_services as number) || 9} services connected`} />
        <MetricCard icon={Server} label="Worker" value={worker.status === "ready" ? "Online" : "Offline"} subtitle={(worker.gpu_name as string) || "Launch to connect"} color="bg-teal-600" tooltip={worker.status === "ready" ? `${worker.gpu_name} active` : "No GPU worker running"} />
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
                  <div key={(p.id as string) || idx} className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-purple-900/40 to-blue-900/40 flex items-center justify-center">
                      <Cpu className="h-4 w-4 text-purple-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">{(p.name as string) || (p.type as string) || "Untitled Job"}</p>
                      <p className="text-xs text-gray-500">{p.status as string}</p>
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
            <button onClick={() => setShowSuggestionsModal(true)} className="text-xs text-purple-400 hover:text-purple-300">View all</button>
          </div>
          <div className="space-y-3">
            {visibleSuggestions.slice(0, 3).map((s) => (
              <div key={s.id} className="flex items-start gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] p-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-600/20">
                  <s.icon className="h-4 w-4 text-purple-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">{s.title}</p>
                  <p className="text-xs text-gray-500">{s.desc}</p>
                </div>
              </div>
            ))}
            {visibleSuggestions.length === 0 && (
              <p className="text-xs text-gray-500 text-center py-4">All suggestions dismissed</p>
            )}
          </div>
          <Link href="/brain" className="mt-3 w-full block text-center rounded-lg bg-purple-600/10 py-2 text-xs text-purple-400 hover:bg-purple-600/20">
            Open Brain
          </Link>
        </div>
      </div>

      {/* Recent Generations Gallery */}
      {recentAssets.length > 0 && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Recent Generations</h3>
            <Link href="/assets" className="text-xs text-purple-400 hover:text-purple-300">View all in Library</Link>
          </div>
          <div className="grid grid-cols-6 gap-3">
            {recentAssets.map((asset) => (
              <Link key={asset.id} href="/assets" className="group">
                <div className="aspect-square rounded-lg bg-gradient-to-br from-purple-900/30 to-blue-900/30 border border-white/[0.06] overflow-hidden group-hover:border-purple-500/40 transition-colors">
                  {asset.public_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={asset.public_url} alt={asset.filename} className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <ImageIcon className="h-6 w-6 text-gray-600" />
                    </div>
                  )}
                </div>
                <p className="text-[10px] text-gray-500 mt-1 truncate">{(asset.metadata?.prompt as string)?.slice(0, 30) || asset.filename}</p>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* System Status Bar — LIVE */}
      <div className="flex items-center gap-6 rounded-xl border border-white/[0.06] bg-[#12122a] px-5 py-3">
        <span className="text-xs font-medium text-gray-400">System Status</span>
        {services?.services ? (
          Object.entries(services.services).map(([name, info]: [string, unknown]) => {
            const svcInfo = info as Record<string, unknown>;
            // GPU providers get special treatment
            let dotColor = svcInfo.connected ? "bg-green-500" : "bg-gray-600";
            let statusText = svcInfo.connected ? "Online" : "Offline";
            let statusColor = svcInfo.connected ? "text-green-400" : "text-gray-600";

            if (name === "vast_ai" || name === "vast") {
              if (vastStatus?.instance_active) {
                dotColor = "bg-green-500";
                statusText = "GPU Active";
                statusColor = "text-green-400";
              } else if (vastStatus?.api_connected) {
                dotColor = "bg-amber-400";
                statusText = "Connected";
                statusColor = "text-amber-400";
              }
            }

            if (name === "runpod") {
              if (runpodStatus?.instance_active) {
                dotColor = "bg-green-500";
                statusText = "GPU Active";
                statusColor = "text-green-400";
              } else if (runpodStatus?.api_connected) {
                dotColor = "bg-amber-400";
                statusText = "Connected";
                statusColor = "text-amber-400";
              }
            }

            return (
              <div key={name} className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${dotColor}`} />
                <span className="text-xs text-gray-300">{name.replace("_", " ")}</span>
                <span className={`text-xs ${statusColor}`}>{statusText}</span>
              </div>
            );
          })
        ) : (
          <span className="text-xs text-gray-600">Loading...</span>
        )}
        {/* Show RunPod even if not in services list */}
        {Boolean(runpodStatus?.api_connected) && !services?.services?.runpod && (
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${runpodStatus?.instance_active ? "bg-green-500" : "bg-amber-400"}`} />
            <span className="text-xs text-gray-300">RunPod</span>
            <span className={`text-xs ${runpodStatus?.instance_active ? "text-green-400" : "text-amber-400"}`}>
              {runpodStatus?.instance_active ? "GPU Active" : "Connected"}
            </span>
          </div>
        )}
        <Link href="/admin" className="ml-auto text-xs text-purple-400 hover:text-purple-300">
          View all systems →
        </Link>
      </div>

      {/* Suggestions Modal */}
      {showSuggestionsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowSuggestionsModal(false)}>
          <div className="w-full max-w-lg rounded-xl border border-white/[0.08] bg-[#12122a] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold text-white">AI Brain Suggestions</h2>
              <button onClick={() => setShowSuggestionsModal(false)} className="p-1 text-gray-400 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="text-xs text-gray-500 mb-4">Dismiss suggestions you don&apos;t need. They won&apos;t appear on the dashboard.</p>
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {allSuggestions.map((s) => {
                const isDismissed = dismissedSuggestions.includes(s.id);
                return (
                  <div key={s.id} className={`flex items-center gap-3 rounded-lg border p-3 ${isDismissed ? "border-white/[0.04] opacity-50" : "border-white/[0.08] bg-white/[0.02]"}`}>
                    <button onClick={() => toggleDismiss(s.id)} className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border ${isDismissed ? "border-gray-600 bg-gray-700" : "border-purple-500 bg-purple-600/20"}`}>
                      {isDismissed && <Check className="h-3 w-3 text-gray-400" />}
                    </button>
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-purple-600/20">
                      <s.icon className="h-4 w-4 text-purple-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium ${isDismissed ? "text-gray-500 line-through" : "text-white"}`}>{s.title}</p>
                      <p className="text-xs text-gray-500">{s.desc}</p>
                    </div>
                  </div>
                );
              })}
            </div>
            <button onClick={() => setShowSuggestionsModal(false)} className="mt-4 w-full rounded-lg bg-purple-600 py-2 text-sm font-medium text-white hover:bg-purple-700">
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
