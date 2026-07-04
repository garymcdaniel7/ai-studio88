"use client";

import { useEffect, useState } from "react";
import {
  Users,
  Search,
  Plus,
  Upload,
  Filter,
  Star,
  MoreHorizontal,
  Loader2,
} from "lucide-react";
import { getTalent } from "@/lib/api";

const tabs = ["All Talent", "Models", "Characters", "Voices", "Influencers", "Wardrobe"];

export default function TalentPage() {
  const [selectedTab, setSelectedTab] = useState("All Talent");
  const [selectedTalent, setSelectedTalent] = useState<any>(null);
  const [talentData, setTalentData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await getTalent();
        setTalentData(Array.isArray(data) ? data : []);
        if (data.length > 0) setSelectedTalent(data[0]);
      } catch {
        setTalentData([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filtered = talentData;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Talent</h1>
          <p className="text-sm text-gray-500">
            Manage your AI personas, models, voices, and characters.
          </p>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 hover:bg-white/[0.06]">
            <Upload className="h-4 w-4" /> Import
          </button>
          <button className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700">
            <Plus className="h-4 w-4" /> New Talent
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-white/[0.06] pb-px">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setSelectedTab(tab)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              selectedTab === tab
                ? "border-b-2 border-purple-500 text-purple-400"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-6 gap-3">
        {[
          { label: "Total Talent", value: "48", sub: "↑ 6 this month", color: "text-blue-400" },
          { label: "Models", value: "24", sub: "↑ 3 this month", color: "text-purple-400" },
          { label: "Characters", value: "12", sub: "↑ 2 this month", color: "text-amber-400" },
          { label: "Voices", value: "8", sub: "↑ 1 this month", color: "text-green-400" },
          { label: "Influencers", value: "4", sub: "↑ 1 this month", color: "text-pink-400" },
          { label: "Wardrobe Sets", value: "36", sub: "↑ 5 this month", color: "text-teal-400" },
        ].map((m) => (
          <div key={m.label} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-3 text-center">
            <p className="text-xs text-gray-500">{m.label}</p>
            <p className="text-xl font-bold text-white">{m.value}</p>
            <p className={`text-xs ${m.color}`}>{m.sub}</p>
          </div>
        ))}
      </div>

      {/* Main Content: Grid + Detail Panel */}
      <div className="grid grid-cols-[1fr_380px] gap-6">
        {/* Talent Grid */}
        <div>
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-gray-400">
              Talent Library · {filtered.length} results
            </p>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1">
                <Search className="h-3.5 w-3.5 text-gray-500" />
                <input className="w-32 bg-transparent text-xs text-gray-300 placeholder:text-gray-600 outline-none" placeholder="Search..." />
              </div>
              <button className="flex items-center gap-1 rounded-lg border border-white/[0.08] px-2 py-1 text-xs text-gray-400">
                <Filter className="h-3 w-3" /> Filters
              </button>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4">
            {filtered.map((talent: any) => (
              <button
                key={talent.id}
                onClick={() => setSelectedTalent(talent)}
                className={`group relative overflow-hidden rounded-xl border transition-all ${
                  selectedTalent?.id === talent.id
                    ? "border-purple-500/50 ring-1 ring-purple-500/30"
                    : "border-white/[0.06] hover:border-white/[0.12]"
                } bg-[#12122a]`}
              >
                {/* Avatar placeholder */}
                <div className="aspect-[3/4] w-full bg-gradient-to-br from-purple-900/30 to-blue-900/30" />
                <div className="p-3">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-white">{talent.name}</p>
                    <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-purple-600/20 text-purple-400">
                      {talent.default_style || "Model"}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">{talent.bio?.slice(0, 40) || "AI Talent"}</p>
                  <div className="mt-1 flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                    <span className="text-[10px] text-gray-500">Active</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Detail Panel */}
        {selectedTalent && (
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
            {/* Profile header */}
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-white">{selectedTalent.name}</h3>
                  <Star className="h-4 w-4 text-gray-600 cursor-pointer hover:text-amber-400" />
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <span className="rounded bg-purple-600/20 px-2 py-0.5 text-xs font-medium text-purple-400">
                    {selectedTalent.default_style || "Model"}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-green-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> Active
                  </span>
                </div>
              </div>
              <div className="flex gap-1">
                <button className="rounded-lg border border-white/[0.08] px-3 py-1.5 text-xs text-gray-300 hover:bg-white/[0.04]">Edit</button>
                <button className="rounded-lg border border-white/[0.08] p-1.5 text-gray-400 hover:bg-white/[0.04]">
                  <MoreHorizontal className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Avatar */}
            <div className="my-4 aspect-[4/5] w-full rounded-xl bg-gradient-to-br from-purple-900/40 to-blue-900/40" />

            <p className="text-sm text-gray-400">
              {selectedTalent.bio || "Fashion and commercial model with a versatile look suitable for luxury, lifestyle, and editorial campaigns."}
            </p>

            {/* Tabs */}
            <div className="mt-4 flex gap-1 border-b border-white/[0.06]">
              {["Overview", "Details", "Media", "Wardrobe", "Projects", "Stats"].map((t) => (
                <button key={t} className="px-3 py-2 text-xs text-gray-500 hover:text-gray-300 first:text-purple-400 first:border-b first:border-purple-500">
                  {t}
                </button>
              ))}
            </div>

            {/* Profile info */}
            <div className="mt-4 space-y-3">
              <h4 className="text-xs font-semibold text-gray-400 uppercase">Profile</h4>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><span className="text-gray-500">Full Name</span><p className="text-gray-200">Melissa Johnson</p></div>
                <div><span className="text-gray-500">Age</span><p className="text-gray-200">28</p></div>
                <div><span className="text-gray-500">Height</span><p className="text-gray-200">5'7" (170 cm)</p></div>
                <div><span className="text-gray-500">Ethnicity</span><p className="text-gray-200">Black / African American</p></div>
              </div>
            </div>

            {/* Creative DNA */}
            <div className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold text-white">Creative DNA</h4>
                <button className="text-[10px] text-purple-400">Edit</button>
              </div>
              <div className="mt-2 space-y-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-purple-500" />
                  <span className="text-gray-400">Visual Style:</span>
                  <span className="text-gray-200">Elegant, Confident, Sophisticated</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-pink-500" />
                  <span className="text-gray-400">Best For:</span>
                  <span className="text-gray-200">Luxury, Fashion, Beauty</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-blue-500" />
                  <span className="text-gray-400">Persona:</span>
                  <span className="text-gray-200">Confident, Modern, Empowered</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
