"use client";

import { useState, useEffect } from "react";
import {
  BarChart3,
  TrendingUp,
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
  [key: string]: any;
}

export default function AnalyticsPage() {
  const [view, setView] = useState<AnalyticsView>("overview");
  const [talentList, setTalentList] = useState<TalentItem[]>([]);
  const [selectedTalentId, setSelectedTalentId] = useState<string>("all");

  useEffect(() => {
    async function loadTalent() {
      try {
        const data = await getTalent();
        setTalentList(Array.isArray(data) ? data : []);
      } catch {
        // Talent list unavailable — leave empty
      }
    }
    loadTalent();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Analytics</h1>
          <p className="text-sm text-gray-500">Track performance, costs, and engagement across the platform.</p>
        </div>
        <div className="flex items-center gap-3">
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
          <select className="rounded-lg border border-white/[0.08] bg-[#12122a] px-3 py-2 text-sm text-gray-300 outline-none">
            <option>Last 7 days</option>
            <option>Last 30 days</option>
            <option>Last 90 days</option>
            <option>This year</option>
          </select>
        </div>
      </div>

      {/* Overview */}
      {view === "overview" && (
        <>
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: "Total Generations", value: "0", change: "—", icon: Image, color: "bg-purple-600" },
              { label: "GPU Hours Used", value: "0.2h", change: "Today", icon: Cpu, color: "bg-blue-600" },
              { label: "Total Spend", value: "$0.93", change: "This session", icon: DollarSign, color: "bg-green-600" },
              { label: "Assets Created", value: "2", change: "Images", icon: Film, color: "bg-amber-600" },
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
                {Array.from({ length: 30 }, (_, i) => (
                  <div
                    key={i}
                    className="flex-1 rounded-t bg-purple-600/40 hover:bg-purple-600/60 transition-colors"
                    style={{ height: `${Math.random() * 80 + 10}%` }}
                  />
                ))}
              </div>
              <p className="mt-2 text-[10px] text-gray-600 text-center">Last 30 days</p>
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
              <h3 className="text-sm font-semibold text-white mb-4">Cost Over Time</h3>
              <div className="h-48 flex items-end gap-1">
                {Array.from({ length: 30 }, (_, i) => (
                  <div
                    key={i}
                    className="flex-1 rounded-t bg-green-600/40 hover:bg-green-600/60 transition-colors"
                    style={{ height: `${Math.random() * 60 + 5}%` }}
                  />
                ))}
              </div>
              <p className="mt-2 text-[10px] text-gray-600 text-center">Daily GPU spend</p>
            </div>
          </div>
        </>
      )}

      {/* Generation Performance */}
      {view === "generation" && (
        <div className="space-y-6">
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "Avg Generation Time", value: "3.2s", desc: "SDXL Turbo" },
              { label: "Success Rate", value: "92%", desc: "Last 50 jobs" },
              { label: "Models Used", value: "3", desc: "Flux, SDXL, SD1.5" },
            ].map((m) => (
              <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
                <p className="text-xs text-gray-500">{m.label}</p>
                <p className="text-2xl font-bold text-white mt-1">{m.value}</p>
                <p className="text-xs text-gray-500">{m.desc}</p>
              </div>
            ))}
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
              { label: "Today", value: "$0.93" },
              { label: "This Week", value: "$2.41" },
              { label: "This Month", value: "$2.41" },
              { label: "Budget Remaining", value: "$7.59" },
            ].map((m) => (
              <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 text-center">
                <p className="text-xs text-gray-500">{m.label}</p>
                <p className="text-2xl font-bold text-white mt-1">{m.value}</p>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Cost Breakdown by GPU</h3>
            <div className="space-y-2">
              {[
                { gpu: "A100 SXM4", cost: "$0.93", time: "1h", pct: 100 },
              ].map((g) => (
                <div key={g.gpu} className="flex items-center gap-3">
                  <span className="w-32 text-sm text-gray-300">{g.gpu}</span>
                  <div className="flex-1 h-3 rounded-full bg-white/[0.05]">
                    <div className="h-3 rounded-full bg-green-500/60" style={{ width: `${g.pct}%` }} />
                  </div>
                  <span className="text-sm text-gray-400 w-16 text-right">{g.cost}</span>
                  <span className="text-xs text-gray-600 w-12 text-right">{g.time}</span>
                </div>
              ))}
            </div>
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
                ? "Showing aggregate analytics for all talent. Social data will appear once talent accounts are connected to Instagram, TikTok, and YouTube."
                : `Showing analytics for ${talentList.find((t) => String(t.id) === selectedTalentId)?.name || "selected talent"}. Social data will appear once this talent is connected to social accounts.`}
            </p>
          </div>
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: "Total Followers", value: "—", icon: Users },
              { label: "Impressions", value: "—", icon: Eye },
              { label: "Engagement Rate", value: "—", icon: Heart },
              { label: "Posts Published", value: "0", icon: Share2 },
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
              { label: "Posts Scheduled", value: "0" },
              { label: "Posts Published", value: "0" },
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
