"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Film, FolderOpen, Sparkles, Plus, Play, Loader2 } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

interface Shot {
  id: string;
  position: number;
  description: string;
  prompt: string;
  status: string;
  image_url: string | null;
  duration_seconds: number;
  transition: string;
}

interface Storyboard {
  id: string;
  concept: string;
  shots: Shot[];
  total_shots: number;
  completed_shots: number;
  status: string;
  total_duration_seconds: number;
}

export default function ProjectWorkspace() {
  const params = useParams();
  const projectId = params.id as string;
  const [project, setProject] = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "storyboard" | "assets">("overview");
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null);
  const [concept, setConcept] = useState("");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProject();
  }, [projectId]);

  async function loadProject() {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/projects/${projectId}`);
      if (resp.ok) {
        const data = await resp.json();
        setProject(data);
      }
    } catch {} finally {
      setLoading(false);
    }
  }

  async function createStoryboard() {
    if (!concept.trim() || creating) return;
    setCreating(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/storyboard/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          concept,
          project_id: projectId,
          num_shots: 5,
        }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setStoryboard(data);
        setConcept("");
      }
    } catch {} finally {
      setCreating(false);
    }
  }

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
      <div className="flex items-center gap-4">
        <Link href="/projects" className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.04]">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-white">{(project?.name as string) || "Project"}</h1>
          <p className="text-sm text-gray-500">{(project?.description as string) || (project?.category as string) || ""}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/[0.06]">
        {[
          { key: "overview", label: "Overview", icon: FolderOpen },
          { key: "storyboard", label: "Storyboard", icon: Film },
          { key: "assets", label: "Assets", icon: Sparkles },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as "overview" | "storyboard" | "assets")}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 ${
              activeTab === tab.key
                ? "border-purple-500 text-purple-400"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === "overview" && (
        <div className="grid grid-cols-2 gap-6">
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <h3 className="text-sm font-semibold text-white mb-4">Project Details</h3>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Category</span>
                <span className="text-white">{(project?.category as string) || "campaign"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Assets</span>
                <span className="text-white">{(project?.asset_count as number) || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Generations</span>
                <span className="text-white">{(project?.generation_count as number) || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Total Cost</span>
                <span className="text-white">${((project?.total_cost as number) || 0).toFixed(2)}</span>
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6">
            <h3 className="text-sm font-semibold text-white mb-4">Quick Actions</h3>
            <div className="space-y-2">
              <Link
                href={`/brain?prompt=Continue working on ${(project?.name as string) || "this project"}`}
                className="flex items-center gap-3 rounded-lg border border-white/[0.06] px-4 py-3 text-sm text-gray-300 hover:bg-white/[0.04] transition-colors"
              >
                <Sparkles className="h-4 w-4 text-purple-400" />
                Open in Brain
              </Link>
              <button
                onClick={() => setActiveTab("storyboard")}
                className="w-full flex items-center gap-3 rounded-lg border border-white/[0.06] px-4 py-3 text-sm text-gray-300 hover:bg-white/[0.04] transition-colors text-left"
              >
                <Film className="h-4 w-4 text-blue-400" />
                Create Storyboard
              </button>
              <Link
                href="/create"
                className="flex items-center gap-3 rounded-lg border border-white/[0.06] px-4 py-3 text-sm text-gray-300 hover:bg-white/[0.04] transition-colors"
              >
                <Plus className="h-4 w-4 text-green-400" />
                Generate Content
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Storyboard Tab */}
      {activeTab === "storyboard" && (
        <div className="space-y-6">
          {/* Create Storyboard */}
          {!storyboard && (
            <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-6">
              <h3 className="text-sm font-semibold text-purple-300 mb-2">Create a Storyboard</h3>
              <p className="text-xs text-gray-500 mb-4">Describe your concept and the AI will plan the shots.</p>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={concept}
                  onChange={(e) => setConcept(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && createStoryboard()}
                  placeholder="e.g. Melissa walking through Tokyo at night, neon lights reflecting..."
                  className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder:text-gray-600 outline-none focus:border-purple-500/50"
                  autoFocus
                />
                <button
                  onClick={createStoryboard}
                  disabled={!concept.trim() || creating}
                  className="rounded-lg bg-purple-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2"
                >
                  {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Film className="h-4 w-4" />}
                  Plan Shots
                </button>
              </div>
            </div>
          )}

          {/* Storyboard Filmstrip */}
          {storyboard && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-white">{storyboard.concept}</h3>
                  <p className="text-xs text-gray-500">{storyboard.total_shots} shots • {storyboard.total_duration_seconds}s total</p>
                </div>
                <div className="flex gap-2">
                  <button className="rounded-lg bg-purple-600 px-4 py-2 text-xs font-medium text-white hover:bg-purple-700 flex items-center gap-1.5">
                    <Play className="h-3.5 w-3.5" /> Generate All
                  </button>
                  <button
                    onClick={() => setStoryboard(null)}
                    className="rounded-lg border border-white/[0.08] px-4 py-2 text-xs text-gray-400 hover:text-white"
                  >
                    New Storyboard
                  </button>
                </div>
              </div>

              {/* Filmstrip */}
              <div className="flex gap-3 overflow-x-auto pb-4">
                {storyboard.shots.map((shot) => (
                  <div
                    key={shot.id}
                    className="shrink-0 w-52 rounded-xl border border-white/[0.06] bg-[#12122a] overflow-hidden"
                  >
                    {/* Shot Preview */}
                    <div className="h-32 bg-gradient-to-br from-purple-900/20 to-blue-900/20 flex items-center justify-center relative">
                      {shot.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={shot.image_url} alt={shot.description} className="w-full h-full object-cover" />
                      ) : (
                        <div className="text-center">
                          <Film className="h-6 w-6 text-gray-600 mx-auto mb-1" />
                          <p className="text-[9px] text-gray-600">Not generated</p>
                        </div>
                      )}
                      <span className="absolute top-2 left-2 bg-black/60 rounded px-1.5 py-0.5 text-[9px] text-white font-medium">
                        Shot {shot.position}
                      </span>
                      <span className="absolute bottom-2 right-2 bg-black/60 rounded px-1.5 py-0.5 text-[9px] text-gray-300">
                        {shot.duration_seconds}s
                      </span>
                    </div>

                    {/* Shot Details */}
                    <div className="p-3">
                      <p className="text-xs text-white font-medium truncate">{shot.description}</p>
                      <p className="text-[10px] text-gray-500 mt-1 line-clamp-2">{shot.prompt.slice(0, 80)}...</p>
                      <div className="flex items-center justify-between mt-2">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded ${
                          shot.status === "completed" ? "bg-green-600/20 text-green-400" :
                          shot.status === "generating" ? "bg-amber-600/20 text-amber-400" :
                          "bg-gray-600/20 text-gray-400"
                        }`}>
                          {shot.status}
                        </span>
                        <span className="text-[9px] text-gray-600">{shot.transition}</span>
                      </div>
                    </div>
                  </div>
                ))}

                {/* Add Shot */}
                <div className="shrink-0 w-52 rounded-xl border-2 border-dashed border-white/[0.08] flex items-center justify-center min-h-[200px]">
                  <div className="text-center">
                    <Plus className="h-6 w-6 text-gray-600 mx-auto mb-1" />
                    <p className="text-[10px] text-gray-500">Add Shot</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Empty State */}
          {!storyboard && !concept && (
            <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
              <Film className="h-10 w-10 text-gray-600 mx-auto mb-3" />
              <p className="text-sm text-gray-400">No storyboard yet</p>
              <p className="text-xs text-gray-600 mt-1">Describe a concept above and the AI will plan your shots.</p>
            </div>
          )}
        </div>
      )}

      {/* Assets Tab */}
      {activeTab === "assets" && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
          <Sparkles className="h-10 w-10 text-gray-600 mx-auto mb-3" />
          <p className="text-sm text-gray-400">No assets yet</p>
          <p className="text-xs text-gray-600 mt-1">Generate content from the Storyboard or Studio to see it here.</p>
          <Link href="/create" className="mt-3 inline-block rounded-lg bg-purple-600 px-4 py-2 text-xs font-medium text-white hover:bg-purple-700">
            Generate Content
          </Link>
        </div>
      )}
    </div>
  );
}
