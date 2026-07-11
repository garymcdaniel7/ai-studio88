"use client";

import { useState, useEffect } from "react";
import {
  DollarSign,
  Cpu,
  Image,
  Users,
  Film,
  Eye,
  Heart,
  MessageSquare,
  Share2,
} from "lucide-react";
import { getTalent } from "@/lib/api";

type AnalyticsView = "overview" | "generation" | "cost" | "talent" | "publishing";

interface TalentItem {
  id: number;
  name: string;
  [key: string]: unknown;
}

interface CostData {
  current_session_cost?: number;
  today_total?: number;
  month_total?: number;
  budget_daily?: number;
  budget_monthly?: number;
}

interface CostHistoryItem {
  date: string;
  cost: number;
  sessions?: number;
}

interface GenerationItem {
  id?: string;
  [key: string]: unknown;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

export default function AnalyticsPage() {
  const [view, setView] = useState<AnalyticsView>("overview");
  const [talentList, setTalentList] = useState<TalentItem[]>([]);
  const [selectedTalentId, setSelectedTalentId] = useState<string>("all");
  const [costData, setCostData] = useState<CostData | null>(null);
  const [costHistory, setCostHistory] = useState<CostHistoryItem[]>([]);
  const [generationHistory, setGenerationHistory] = useState<GenerationItem[]>([]);
  const [timeRange, setTimeRange] = useState<number>(30);

  useEffect(() => {
    async function loadTalent() {
      try {
        const data = await getTalent();
        setTalentList(Array.isArray(data) ? data as TalentItem[] : []);
      } catch {
        // Talent list unavailable — leave empty
      }
    }
    loadTalent();
  }, []);

  useEffect(() => {
    async function loadAnalyticsData() {
      try {
        const resp = await fetch(`${API_BASE}/api/v1/infrastructure/cost`);
        if (resp.ok) setCostData(await resp.json());
      } catch {}
      try {
        const resp = await fetch(`${API_BASE}/api/v1/infrastructure/cost/history?days=${timeRange}`);
        if (resp.ok) {
          const data = await resp.json();
          setCostHistory(Array.isArray(data.history) ? data.history : []);
        }
      } catch {}
      try {
        const resp = await fetch(`${API_BASE}/api/v1/generation/history?limit=${timeRange * 5}`);
        if (resp.ok) {
          const data = await resp.json();
          setGenerationHistory(Array.isArray(data) ? data : []);
        }
      } catch {}
    }
    loadAnalyticsData();
  }, [timeRange]);

  // Derived metrics
  const totalGenerations = generationHistory.length;
  const totalSpend = costData?.month_total != null ? `$${costData.month_total.toFixed(2)}` : costData?.today_total != null ? `$${costData.today_total.toFixed(2)}` : "—";
  const gpuHours = costData?.today_total != null ? `${(costData.today_total / 2.21).toFixed(1)}h` : "—";
  const assetsCreated = totalGenerations;

  function getBarHeights(data: CostHistoryItem[], count: number, key: "cost" | "sessions"): number[] {
    if (data.length === 0) return Array(count).fill(5);
    const padded = [...Array(Math.max(0, count - data.length)).fill({ cost: 0, sessions: 0 }), ...data].slice(-count);
    const maxVal = Math.max(...padded.map((d: CostHistoryItem) => d[key as keyof CostHistoryItem] as number || 0), 0.01);
    return padded.map((d: CostHistoryItem) => Math.max(5, (((d[key as keyof CostHistoryItem] as number) || 0) / maxVal) * 90));
  }

  const costBarHeights = getBarHeights(costHistory, timeRange, "cost");
  const generationBarHeights = getBarHeights(costHistory, timeRange, "sessions");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Analytics</h1>
          <p className="text-sm text-gray-500">Track performance, costs, and engagement across the platform.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-white/[0.08] overflow-hidden">
            {[
              { label: "7d", value: 7 },
              { label: "30d", value: 30 },
              { label: "90d", value: 90 },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => setTimeRange(opt.value)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  timeRange === opt.value
                    ? "bg-purple-600 text-white"
                    : "bg-white/[0.02] text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <select
            value={view}
            onChange={(e) => setView(e.target.value as AnalyticsView)}
            className="rounded-lg border border-white/[0.08] bg-[#12122a] px-4 py-2 text-sm text-gray-300 outline-none"
          >
            <option value="overview">Overview</option>
            <option value="generation">Generation Performance</option>
            <option value="cost">GPU & Cost</option>
            <option value="talent">Talent / Social</option>
            <option value="publishing">Publishing</option>
          </select>

        </div>
      </div>

      {/* Overview */}
      {view === "overview" && (
        <>
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: "Total Generations", value: String(totalGenerations), change: "All time", icon: Image, color: "bg-purple-600" },
              { label: "GPU Hours Used", value: gpuHours, change: "Today", icon: Cpu, color: "bg-blue-600" },
              { label: "Total Spend", value: totalSpend, change: "This month", icon: DollarSign, color: "bg-green-600" },
              { label: "Assets Created", value: String(assetsCreated), change: "Images", icon: Film, color: "bg-amber-600" },
            ].map((m) => (
              <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
                <div className="flex items-center justify-between">
                  <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${m.color}`}>
                    <m.icon className="h-4 w-4 text-white" />
                  </div>
                  <span className="text-[10px] text-gray-500">{m.change}</span>
                </div>
                <p className="mt-3 text-2xl font-bold text-white">{m.value}</p>
                <p className="text-xs text-gray-500">{m.label}</p>
              </div>
            ))}
          </div>

          {/* Charts placeholder */}
          <div className="grid grid-cols-2 gap-6">
            <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
              <h3 className="text-sm font-semibold text-white mb-4">Generation History</h3>
              <div className="h-48 flex items-end gap-1">
                {generationBarHeights.map((h, i) => (
                  <div
                    key={i}
                    className="flex-1 rounded-t bg-purple-600/40 hover:bg-purple-600/60 transition-colors"
                    style={{ height: `${h}%` }}
                  />
                ))}
              </div>
              <p className="mt-2 text-[10px] text-gray-600 text-center">Last {timeRange} days</p>
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
              <h3 className="text-sm font-semibold text-white mb-4">Cost Over Time</h3>
              <div className="h-48 flex items-end gap-1">
                {costBarHeights.map((h, i) => (
                  <div
                    key={i}
                    className="flex-1 rounded-t bg-green-600/40 hover:bg-green-600/60 transition-colors"
                    style={{ height: `${h}%` }}
                  />
                ))}
              </div>
              <p className="mt-2 text-[10px] text-gray-600 text-center">Daily GPU spend ({timeRange}d)</p>
            </div>
          </div>
        </>
      )}

      {/* Generation Performance */}
      {view === "generation" && (
        <div className="space-y-6">
          <div className="grid grid-cols-3 gap-4">
            {(() => {
              const withTime = generationHistory.filter((item) => item.generation_time != null);
              const avgTime = withTime.length > 0
                ? (withTime.reduce((sum, item) => sum + Number(item.generation_time), 0) / withTime.length).toFixed(1) + "s"
                : "—";
              const successRate = generationHistory.length > 0
                ? Math.round((generationHistory.filter((item) => item.status === "completed" || item.status === "success" || !item.status).length / generationHistory.length) * 100) + "%"
                : "—";
              const uniqueModels = new Set(generationHistory.map((item) => item.model || item.model_id).filter(Boolean));
              const modelsUsed = uniqueModels.size > 0 ? String(uniqueModels.size) : "—";
              const modelsDesc = uniqueModels.size > 0 ? Array.from(uniqueModels).slice(0, 3).join(", ") : "No data";

              return [
                { label: "Avg Generation Time", value: avgTime, desc: withTime.length > 0 ? `${withTime.length} jobs measured` : "No data" },
                { label: "Success Rate", value: successRate, desc: generationHistory.length > 0 ? `Last ${generationHistory.length} jobs` : "No data" },
                { label: "Models Used", value: modelsUsed, desc: modelsDesc },
              ].map((m) => (
                <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
                  <p className="text-xs text-gray-500">{m.label}</p>
                  <p className="text-2xl font-bold text-white mt-1">{m.value}</p>
                  <p className="text-xs text-gray-500">{m.desc}</p>
                </div>
              ));
            })()}
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Model Performance Comparison</h3>
            <div className="space-y-3">
              {[
                { model: "Flux Dev", time: "45s", quality: "Excellent", uses: 1 },
                { model: "SDXL Turbo", time: "3s", quality: "Good", uses: 2 },
                { model: "SD 1.5", time: "12s", quality: "Fair", uses: 0 },
              ].map((m) => (
                <div key={m.model} className="flex items-center gap-4 text-sm">
                  <span className="w-32 text-gray-300 font-medium">{m.model}</span>
                  <span className="w-20 text-gray-500">{m.time}</span>
                  <span className="w-20 text-gray-500">{m.quality}</span>
                  <div className="flex-1 h-2 rounded-full bg-white/[0.05]">
                    <div className="h-2 rounded-full bg-purple-500" style={{ width: `${m.uses * 33}%` }} />
                  </div>
                  <span className="w-16 text-right text-gray-400">{m.uses} uses</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* GPU & Cost Analytics */}
      {view === "cost" && (
        <div className="space-y-6">
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: "Today", value: `$${((costData as Record<string, unknown>)?.today as number || 0).toFixed(2)}` },
              { label: "This Week", value: `$${((costData as Record<string, unknown>)?.this_month as number || 0).toFixed(2)}` },
              { label: "This Month", value: `$${((costData as Record<string, unknown>)?.this_month as number || 0).toFixed(2)}` },
              { label: "Per Image (avg)", value: `$${((costData as Record<string, unknown>)?.per_image_avg as number || 0).toFixed(5)}` },
            ].map((m) => (
              <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
                <p className="text-xs text-gray-500">{m.label}</p>
                <p className="text-2xl font-bold text-white mt-1">{m.value}</p>
              </div>
            ))}
          </div>

          {/* Job Cost Breakdown */}
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Cost by Job Type</h3>
            <div className="space-y-2">
              {Object.entries(((costData as Record<string, unknown>)?.job_costs as Record<string, unknown>)?.by_type as Record<string, number> || {}).map(([type, cost]) => (
                <div key={type} className="flex items-center gap-3">
                  <span className="w-32 text-sm text-gray-300 capitalize">{type}</span>
                  <div className="flex-1 h-3 rounded-full bg-white/[0.05]">
                    <div className="h-3 rounded-full bg-purple-500/60" style={{ width: `${Math.min(100, (cost / Math.max(0.01, (costData as Record<string, unknown>)?.today as number || 0.01)) * 100)}%` }} />
                  </div>
                  <span className="text-sm text-gray-400 w-20 text-right">${cost.toFixed(4)}</span>
                </div>
              ))}
              {Object.keys(((costData as Record<string, unknown>)?.job_costs as Record<string, unknown>)?.by_type || {}).length === 0 && (
                <p className="text-xs text-gray-500">No jobs recorded this session. Generate an image to see costs.</p>
              )}
            </div>
          </div>

          {/* Connected Service Costs */}
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Service Costs</h3>
            <div className="space-y-2">
              {[
                { service: "Vast.ai (GPU)", plan: "Pay-per-hour", rate: "$0.076/hr (RTX 3090)", active: true },
                { service: "ElevenLabs (Voice)", plan: "Paid Plan", rate: "~$0.30/1000 chars", active: true },
                { service: "Backblaze B2 (Storage)", plan: "Pay-per-GB", rate: "$0.005/GB/month", active: true },
                { service: "Supabase (Database)", plan: "Free Tier", rate: "$0/month", active: true },
                { service: "Suno (Music)", plan: "Not connected", rate: "—", active: false },
              ].map((s) => (
                <div key={s.service} className="flex items-center gap-3 rounded-lg border border-white/[0.04] bg-white/[0.01] px-3 py-2">
                  <span className={`h-2 w-2 rounded-full ${s.active ? "bg-green-400" : "bg-gray-600"}`} />
                  <span className="flex-1 text-sm text-gray-300">{s.service}</span>
                  <span className="text-xs text-gray-500">{s.plan}</span>
                  <span className="text-xs text-gray-400 w-32 text-right">{s.rate}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Platform Comparison */}
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Cost Comparison with Other Platforms</h3>
            <p className="text-xs text-gray-500 mb-4">AI Studio vs typical subscription services (based on your usage).</p>
            <div className="space-y-3">
              {[
                { platform: "AI Studio (You)", cost: `$${((costData as Record<string, unknown>)?.this_month as number || 0).toFixed(2)}/mo`, images: `${(costData as Record<string, unknown>)?.generation_count || 0}`, perImage: `$${((costData as Record<string, unknown>)?.per_image_avg as number || 0.0001).toFixed(4)}`, highlight: true },
                { platform: "Midjourney (Standard)", cost: "$30/mo", images: "~200 (limited)", perImage: "$0.15", highlight: false },
                { platform: "Midjourney (Pro)", cost: "$60/mo", images: "~600", perImage: "$0.10", highlight: false },
                { platform: "DALL-E 3 (ChatGPT Plus)", cost: "$20/mo", images: "~50", perImage: "$0.40", highlight: false },
                { platform: "Runway (Standard)", cost: "$12/mo", images: "125 credits", perImage: "$0.10", highlight: false },
                { platform: "Leonardo AI (Pro)", cost: "$24/mo", images: "~2500", perImage: "$0.01", highlight: false },
              ].map((p) => (
                <div key={p.platform} className={`flex items-center gap-4 rounded-lg px-4 py-2.5 ${p.highlight ? "border border-purple-500/30 bg-purple-500/5" : "border border-white/[0.04] bg-white/[0.01]"}`}>
                  <span className={`flex-1 text-sm ${p.highlight ? "text-purple-300 font-medium" : "text-gray-300"}`}>{p.platform}</span>
                  <span className="w-24 text-xs text-gray-400 text-right">{p.cost}</span>
                  <span className="w-24 text-xs text-gray-500 text-right">{p.images} imgs</span>
                  <span className={`w-20 text-xs text-right ${p.highlight ? "text-green-400 font-medium" : "text-gray-500"}`}>{p.perImage}/img</span>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-gray-600 mt-3">
              AI Studio uses pay-per-use GPU time. No subscription limits — generate unlimited images. Cost decreases with faster models (SDXL Turbo: ~$0.0001/image).
            </p>
          </div>
        </div>
      )}

      {/* Talent / Social Analytics */}
      {view === "talent" && (
        <div className="space-y-6">
          {/* Talent Selector Dropdown */}
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-400">Talent:</label>
            <select
              value={selectedTalentId}
              onChange={(e) => setSelectedTalentId(e.target.value)}
              className="rounded-lg border border-white/[0.08] bg-[#12122a] px-4 py-2 text-sm text-gray-300 outline-none"
            >
              <option value="all">All Talent</option>
              {talentList.map((t) => (
                <option key={t.id} value={String(t.id)}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-5">
            <p className="text-sm text-purple-300">
              {selectedTalentId === "all"
                ? "Connect AI Talent to social accounts to see engagement analytics. Go to Talent → select a talent → connect social handles."
                : `Showing analytics for ${talentList.find((t) => String(t.id) === selectedTalentId)?.name || "selected talent"}. Social data will appear once this talent is connected to social accounts.`}
            </p>
          </div>
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: "Total Followers", value: "—", icon: Users },
              { label: "Impressions", value: "—", icon: Eye },
              { label: "Engagement Rate", value: "—", icon: Heart },
              { label: "Posts Published", value: "—", icon: Share2 },
            ].map((m) => (
              <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
                <m.icon className="h-5 w-5 text-gray-600 mb-2" />
                <p className="text-2xl font-bold text-white">{m.value}</p>
                <p className="text-xs text-gray-500">{m.label}</p>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Platform Breakdown</h3>
            <div className="space-y-3">
              {["Instagram", "TikTok", "YouTube", "Twitter/X", "LinkedIn"].map((p) => (
                <div key={p} className="flex items-center justify-between text-sm">
                  <span className="text-gray-300">{p}</span>
                  <span className="text-xs text-gray-600">Not connected</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Publishing Analytics */}
      {view === "publishing" && (
        <div className="space-y-6">
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "Posts Scheduled", value: "—" },
              { label: "Posts Published", value: "—" },
              { label: "Best Posting Time", value: "—" },
            ].map((m) => (
              <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
                <p className="text-xs text-gray-500">{m.label}</p>
                <p className="text-2xl font-bold text-white mt-1">{m.value}</p>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
            <MessageSquare className="h-10 w-10 text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-400">No publishing data yet</p>
            <p className="text-xs text-gray-600 mt-1">Schedule and publish content to see engagement analytics here.</p>
          </div>
        </div>
      )}
    </div>
  );
}
