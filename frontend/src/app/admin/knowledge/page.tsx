"use client";

import { useState } from "react";
import { Search, Brain, Database, Sparkles, Loader2, Tag } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

interface KnowledgeResult {
  source: string;
  entity_id: string;
  name: string;
  relevance: number;
  summary: string;
  data: Record<string, unknown>;
}

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KnowledgeResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [talentId, setTalentId] = useState("");
  const [talentKnowledge, setTalentKnowledge] = useState<Record<string, unknown> | null>(null);
  const [workflowStats, setWorkflowStats] = useState<Record<string, unknown> | null>(null);
  const [insights, setInsights] = useState<Record<string, unknown> | null>(null);

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/aios/v1/knowledge/search?q=${encodeURIComponent(query)}&limit=20`);
      if (resp.ok) {
        const data = await resp.json();
        setResults(data.results || []);
      }
    } catch {}
    setLoading(false);
  }

  async function loadTalentKnowledge(id: string) {
    try {
      const resp = await fetch(`${API_BASE}/aios/v1/knowledge/talent/${id}`);
      if (resp.ok) setTalentKnowledge(await resp.json());
    } catch {}
  }

  async function loadWorkflowStats() {
    try {
      const resp = await fetch(`${API_BASE}/aios/v1/knowledge/workflow-dna/stats`);
      if (resp.ok) setWorkflowStats(await resp.json());
    } catch {}
  }

  async function loadInsights() {
    try {
      const resp = await fetch(`${API_BASE}/aios/v1/session/insights`);
      if (resp.ok) setInsights(await resp.json());
    } catch {}
  }

  const sourceColors: Record<string, string> = {
    talent: "bg-purple-500/20 text-purple-400",
    creative_dna: "bg-pink-500/20 text-pink-400",
    model: "bg-blue-500/20 text-blue-400",
    generation: "bg-green-500/20 text-green-400",
    workflow_dna: "bg-amber-500/20 text-amber-400",
    object_dna: "bg-cyan-500/20 text-cyan-400",
    memory: "bg-indigo-500/20 text-indigo-400",
    story: "bg-rose-500/20 text-rose-400",
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
          <Database className="h-6 w-6 text-purple-400" />
          Knowledge Graph (Yemoja)
        </h1>
        <p className="text-sm text-gray-500">
          Search across all platform intelligence: talent, models, DNA, stories, workflows, generations.
        </p>
      </div>

      {/* Search */}
      <div className="flex gap-2">
        <div className="flex-1 flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2.5">
          <Search className="h-4 w-4 text-gray-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
            placeholder="Search anything: talent names, styles, models, prompts, stories..."
            className="flex-1 bg-transparent text-sm text-gray-200 placeholder:text-gray-600 outline-none"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          className="rounded-lg bg-purple-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Search"}
        </button>
      </div>

      {/* Quick Actions */}
      <div className="flex gap-2">
        <button onClick={loadWorkflowStats} className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-400 hover:text-white hover:bg-white/[0.06]">
          Workflow DNA Stats
        </button>
        <button onClick={loadInsights} className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-400 hover:text-white hover:bg-white/[0.06]">
          Usage Insights
        </button>
        <button onClick={() => { setQuery("portrait"); handleSearch(); }} className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-400 hover:text-white hover:bg-white/[0.06]">
          Find Portraits
        </button>
        <button onClick={() => { setQuery("luxury"); handleSearch(); }} className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-gray-400 hover:text-white hover:bg-white/[0.06]">
          Find Luxury
        </button>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
          <h3 className="text-sm font-semibold text-white mb-3">Results ({results.length})</h3>
          <div className="space-y-2">
            {results.map((r, i) => (
              <div
                key={i}
                className="flex items-start justify-between rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-3 hover:bg-white/[0.04] cursor-pointer"
                onClick={() => { if (r.source === "talent") loadTalentKnowledge(r.entity_id); }}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-1.5 py-0.5 text-[9px] font-medium uppercase ${sourceColors[r.source] || "bg-gray-500/20 text-gray-400"}`}>
                      {r.source}
                    </span>
                    <p className="text-sm font-medium text-white truncate">{r.name}</p>
                  </div>
                  {r.summary && <p className="text-xs text-gray-500 mt-1 truncate">{r.summary}</p>}
                </div>
                <span className="text-[10px] text-gray-600 shrink-0 ml-2">{Math.round(r.relevance * 100)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Talent Knowledge Detail */}
      {talentKnowledge && (
        <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-purple-300">
              Talent Knowledge: {(talentKnowledge.profile as Record<string, unknown>)?.name as string || "Unknown"}
            </h3>
            <button onClick={() => setTalentKnowledge(null)} className="text-xs text-gray-500 hover:text-white">&times;</button>
          </div>
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Creative DNA</p>
              <p className="text-white mt-1">{talentKnowledge.creative_dna ? "Configured" : "Not set"}</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">LoRAs</p>
              <p className="text-white mt-1">{((talentKnowledge.loras as Record<string, unknown[]>)?.assigned?.length || 0) + ((talentKnowledge.loras as Record<string, unknown[]>)?.trained?.length || 0)} total</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Voices</p>
              <p className="text-white mt-1">{(talentKnowledge.voices as unknown[])?.length || 0} assigned</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Relationships</p>
              <p className="text-white mt-1">{(talentKnowledge.relationships as unknown[])?.length || 0} linked</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Recent Generations</p>
              <p className="text-white mt-1">{(talentKnowledge.recent_generations as unknown[])?.length || 0}</p>
            </div>
          </div>
        </div>
      )}

      {/* Workflow DNA Stats */}
      {workflowStats && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-amber-300">Workflow DNA (Learned Configs)</h3>
            <button onClick={() => setWorkflowStats(null)} className="text-xs text-gray-500 hover:text-white">&times;</button>
          </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Total Recipes</p>
              <p className="text-xl font-bold text-white">{String((workflowStats as Record<string, unknown>).total_recipes || 0)}</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Avg Quality</p>
              <p className="text-xl font-bold text-amber-400">{Number((workflowStats as Record<string, unknown>).avg_quality_score || 0).toFixed(1)}/5</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Total Usage</p>
              <p className="text-xl font-bold text-white">{String((workflowStats as Record<string, unknown>).total_usage || 0)}</p>
            </div>
          </div>
          {Boolean((workflowStats as Record<string, unknown>).by_model) && (
            <div className="mt-3">
              <p className="text-[10px] text-gray-500 uppercase mb-1">By Model</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries((workflowStats as Record<string, Record<string, number>>).by_model || {}).map(([model, count]) => (
                  <span key={model} className="rounded-full bg-white/[0.04] px-2.5 py-1 text-[10px] text-gray-300">{model}: {String(count)}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Usage Insights */}
      {insights && (
        <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-green-300">Usage Insights (What AIOS Has Learned)</h3>
            <button onClick={() => setInsights(null)} className="text-xs text-gray-500 hover:text-white">&times;</button>
          </div>
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Total Requests Tracked</p>
              <p className="text-xl font-bold text-white">{String((insights as Record<string, unknown>).total_requests || 0)}</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Burst Mode</p>
              <p className="text-xl font-bold text-white">{(insights as Record<string, unknown>).burst_mode ? "🔥 Active" : "Normal"}</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] p-3">
              <p className="text-gray-500">Predicted Next</p>
              <p className="text-sm font-bold text-purple-400 mt-1">{String((insights as Record<string, unknown>).predicted_next || "—")}</p>
            </div>
          </div>
          {Boolean((insights as Record<string, unknown>).task_breakdown) && (
            <div className="mt-3">
              <p className="text-[10px] text-gray-500 uppercase mb-1">Task Breakdown</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries((insights as Record<string, Record<string, number>>).task_breakdown || {}).map(([task, count]) => (
                  <span key={task} className="rounded-full bg-white/[0.04] px-2.5 py-1 text-[10px] text-gray-300">{task}: {String(count)}</span>
                ))}
              </div>
            </div>
          )}
          {Boolean((insights as Record<string, unknown>).peak_hours) && (
            <div className="mt-2">
              <p className="text-[10px] text-gray-500">Peak Hours: {((insights as Record<string, number[]>).peak_hours || []).map(h => `${h}:00`).join(", ")}</p>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {results.length === 0 && !talentKnowledge && !workflowStats && !insights && !loading && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-12 text-center">
          <Brain className="h-12 w-12 text-gray-600 mx-auto mb-4" />
          <p className="text-sm text-gray-400">Search the Knowledge Graph</p>
          <p className="text-xs text-gray-600 mt-1">
            Find anything: talent profiles, creative DNA, models, generation history, workflow recipes, stories
          </p>
          <div className="mt-4 flex justify-center gap-2">
            <Tag className="h-3 w-3 text-gray-600" />
            <span className="text-[10px] text-gray-600">Sources: talent, creative_dna, object_dna, visual_dna, model, generation, workflow_dna, story, memory</span>
          </div>
        </div>
      )}
    </div>
  );
}
