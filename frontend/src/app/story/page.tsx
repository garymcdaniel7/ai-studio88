"use client";

import { useState, useEffect, useCallback } from "react";
import {
  BookOpen,
  Plus,
  Users,
  Film,
  Layers,
  Camera,
  Sparkles,
  Clock,
  AlertTriangle,
  CheckCircle,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// =============================================================================
// Types
// =============================================================================

interface Universe {
  id: string;
  name: string;
  description?: string;
  genre?: string;
  created_at: string;
}

interface Character {
  id: string;
  name: string;
  role?: string;
  description?: string;
  universe_id: string;
}

interface Episode {
  id: string;
  title: string;
  episode_number?: number;
  synopsis?: string;
  universe_id: string;
}

interface Scene {
  id: string;
  scene_number?: number;
  location?: string;
  time_of_day?: string;
  mood?: string;
  purpose?: string;
  episode_id: string;
}

interface Shot {
  id: string;
  shot_number?: number;
  description?: string;
  shot_size?: string;
  camera_motion?: string;
  duration_seconds?: number;
  status?: string;
  asset_id?: string;
  scene_id: string;
}

// =============================================================================
// Component
// =============================================================================

export default function StoryPage() {
  const [universes, setUniverses] = useState<Universe[]>([]);
  const [selectedUniverse, setSelectedUniverse] = useState<Universe | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [selectedEpisode, setSelectedEpisode] = useState<Episode | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [selectedScene, setSelectedScene] = useState<Scene | null>(null);
  const [shots, setShots] = useState<Shot[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  // Load universes on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/v1/universes`)
      .then((r) => r.json())
      .then((data) => setUniverses(Array.isArray(data) ? data : []))
      .catch(() => setUniverses([]));
  }, []);

  // Load universe details
  const selectUniverse = useCallback(async (u: Universe) => {
    setSelectedUniverse(u);
    setSelectedEpisode(null);
    setSelectedScene(null);
    setShots([]);
    setLoading(true);
    try {
      const [charsResp, epsResp] = await Promise.all([
        fetch(`${API_BASE}/api/v1/universes/${u.id}/characters`),
        fetch(`${API_BASE}/api/v1/universes/${u.id}/episodes`),
      ]);
      setCharacters(await charsResp.json());
      setEpisodes(await epsResp.json());
    } catch {
      setCharacters([]);
      setEpisodes([]);
    }
    setLoading(false);
  }, []);

  // Load scenes for episode
  const selectEpisode = useCallback(async (ep: Episode) => {
    setSelectedEpisode(ep);
    setSelectedScene(null);
    setShots([]);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/episodes/${ep.id}/scenes`);
      setScenes(await resp.json());
    } catch {
      setScenes([]);
    }
  }, []);

  // Load shots for scene
  const selectScene = useCallback(async (sc: Scene) => {
    setSelectedScene(sc);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/scenes/${sc.id}/shots`);
      setShots(await resp.json());
    } catch {
      setShots([]);
    }
  }, []);

  // Create universe
  async function createUniverse(name: string, description: string) {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/universes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setUniverses((prev) => [data, ...prev]);
        setShowCreate(false);
      }
    } catch {}
  }

  // Plan shots for scene
  async function planShots(sceneId: string) {
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/scenes/${sceneId}/plan-shots`, {
        method: "POST",
      });
      if (resp.ok) {
        const data = await resp.json();
        setShots(data.shots || []);
      }
    } catch {}
    setLoading(false);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            Story Engine <BookOpen className="h-5 w-5 text-purple-400" />
          </h1>
          <p className="text-sm text-gray-500">
            Build narrative universes, characters, episodes, scenes, and shots.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-xs font-medium text-white hover:bg-purple-700"
        >
          <Plus className="h-3.5 w-3.5" /> New Universe
        </button>
      </div>

      {/* Create Universe Modal */}
      {showCreate && <CreateUniverseModal onCreate={createUniverse} onClose={() => setShowCreate(false)} />}

      {/* Main Layout: Universe List + Detail */}
      <div className="grid grid-cols-[300px_1fr] gap-6" style={{ minHeight: "calc(100vh - 180px)" }}>
        {/* Universe List */}
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 overflow-y-auto">
          <h3 className="text-xs font-semibold text-gray-400 uppercase mb-3">Universes</h3>
          {universes.length === 0 ? (
            <p className="text-xs text-gray-600 text-center py-8">No universes yet. Create one to get started.</p>
          ) : (
            <div className="space-y-2">
              {universes.map((u) => (
                <button
                  key={u.id}
                  onClick={() => selectUniverse(u)}
                  className={`w-full rounded-lg px-3 py-2.5 text-left transition-colors ${
                    selectedUniverse?.id === u.id
                      ? "bg-purple-600/20 border border-purple-500/30"
                      : "hover:bg-white/[0.03] border border-transparent"
                  }`}
                >
                  <p className={`text-sm font-medium ${selectedUniverse?.id === u.id ? "text-purple-300" : "text-gray-200"}`}>
                    {u.name}
                  </p>
                  {u.genre && <p className="text-[10px] text-gray-500">{u.genre}</p>}
                  <p className="text-[10px] text-gray-600">{new Date(u.created_at).toLocaleDateString()}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Detail Panel */}
        <div className="space-y-4">
          {!selectedUniverse ? (
            <div className="flex items-center justify-center h-full rounded-xl border border-white/[0.06] bg-[#12122a]">
              <div className="text-center py-16">
                <BookOpen className="h-12 w-12 text-purple-400/20 mx-auto mb-3" />
                <p className="text-sm text-gray-500">Select a universe to explore its story</p>
              </div>
            </div>
          ) : (
            <>
              {/* Universe Header */}
              <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5">
                <h2 className="text-lg font-bold text-white">{selectedUniverse.name}</h2>
                {selectedUniverse.description && (
                  <p className="text-xs text-gray-400 mt-1">{selectedUniverse.description}</p>
                )}
                <div className="flex gap-4 mt-3 text-[10px] text-gray-500">
                  <span className="flex items-center gap-1"><Users className="h-3 w-3" /> {characters.length} characters</span>
                  <span className="flex items-center gap-1"><Film className="h-3 w-3" /> {episodes.length} episodes</span>
                </div>
              </div>

              {/* Characters */}
              <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
                <h3 className="flex items-center gap-2 text-xs font-semibold text-gray-300 mb-3">
                  <Users className="h-3.5 w-3.5 text-blue-400" /> Characters
                </h3>
                {characters.length === 0 ? (
                  <p className="text-xs text-gray-600">No characters yet.</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {characters.map((c) => (
                      <div key={c.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-1.5">
                        <p className="text-xs font-medium text-gray-200">{c.name}</p>
                        {c.role && <p className="text-[10px] text-gray-500">{c.role}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Episodes → Scenes → Shots */}
              <div className="grid grid-cols-3 gap-4">
                {/* Episodes */}
                <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 overflow-y-auto max-h-[400px]">
                  <h3 className="flex items-center gap-2 text-xs font-semibold text-gray-300 mb-3">
                    <Film className="h-3.5 w-3.5 text-amber-400" /> Episodes
                  </h3>
                  <div className="space-y-1.5">
                    {episodes.map((ep) => (
                      <button
                        key={ep.id}
                        onClick={() => selectEpisode(ep)}
                        className={`w-full rounded-lg px-3 py-2 text-left text-xs transition-colors ${
                          selectedEpisode?.id === ep.id
                            ? "bg-amber-500/10 border border-amber-500/30 text-amber-300"
                            : "hover:bg-white/[0.03] text-gray-300 border border-transparent"
                        }`}
                      >
                        <span className="font-medium">
                          {ep.episode_number ? `E${ep.episode_number}: ` : ""}{ep.title}
                        </span>
                      </button>
                    ))}
                    {episodes.length === 0 && <p className="text-[10px] text-gray-600">No episodes yet.</p>}
                  </div>
                </div>

                {/* Scenes */}
                <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 overflow-y-auto max-h-[400px]">
                  <h3 className="flex items-center gap-2 text-xs font-semibold text-gray-300 mb-3">
                    <Layers className="h-3.5 w-3.5 text-green-400" /> Scenes
                  </h3>
                  {selectedEpisode ? (
                    <div className="space-y-1.5">
                      {scenes.map((sc) => (
                        <button
                          key={sc.id}
                          onClick={() => selectScene(sc)}
                          className={`w-full rounded-lg px-3 py-2 text-left text-xs transition-colors ${
                            selectedScene?.id === sc.id
                              ? "bg-green-500/10 border border-green-500/30 text-green-300"
                              : "hover:bg-white/[0.03] text-gray-300 border border-transparent"
                          }`}
                        >
                          <span className="font-medium">Scene {sc.scene_number || "?"}</span>
                          {sc.location && <span className="text-gray-500 ml-1">— {sc.location}</span>}
                        </button>
                      ))}
                      {scenes.length === 0 && <p className="text-[10px] text-gray-600">No scenes yet.</p>}
                    </div>
                  ) : (
                    <p className="text-[10px] text-gray-600">Select an episode</p>
                  )}
                </div>

                {/* Shots */}
                <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 overflow-y-auto max-h-[400px]">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="flex items-center gap-2 text-xs font-semibold text-gray-300">
                      <Camera className="h-3.5 w-3.5 text-purple-400" /> Shots
                    </h3>
                    {selectedScene && (
                      <button
                        onClick={() => planShots(selectedScene.id)}
                        disabled={loading}
                        className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-purple-400 hover:bg-purple-600/10 disabled:opacity-50"
                      >
                        <Sparkles className="h-3 w-3" /> Auto-Plan
                      </button>
                    )}
                  </div>
                  {selectedScene ? (
                    <div className="space-y-2">
                      {shots.map((shot) => (
                        <div key={shot.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-medium text-gray-200">
                              Shot {shot.shot_number || "?"}
                            </span>
                            <ShotStatus status={shot.status} />
                          </div>
                          {shot.description && (
                            <p className="text-[10px] text-gray-400 mt-1 line-clamp-2">{shot.description}</p>
                          )}
                          <div className="flex gap-2 mt-1 text-[10px] text-gray-600">
                            {shot.shot_size && <span>{shot.shot_size}</span>}
                            {shot.camera_motion && <span>{shot.camera_motion}</span>}
                            {shot.duration_seconds && (
                              <span className="flex items-center gap-0.5">
                                <Clock className="h-2.5 w-2.5" /> {shot.duration_seconds}s
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                      {shots.length === 0 && (
                        <p className="text-[10px] text-gray-600">No shots. Use Auto-Plan to generate.</p>
                      )}
                    </div>
                  ) : (
                    <p className="text-[10px] text-gray-600">Select a scene</p>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

function ShotStatus({ status }: { status?: string }) {
  if (!status || status === "draft") return null;
  if (status === "completed") return <CheckCircle className="h-3 w-3 text-green-400" />;
  if (status === "failed") return <AlertTriangle className="h-3 w-3 text-red-400" />;
  return <Clock className="h-3 w-3 text-amber-400 animate-pulse" />;
}

function CreateUniverseModal({ onCreate, onClose }: { onCreate: (name: string, desc: string) => void; onClose: () => void }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-white mb-4">Create Universe</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Story Universe"
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none focus:border-purple-500/40"
              autoFocus
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Description</label>
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="A brief description of the story world..."
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none focus:border-purple-500/40 resize-none"
              rows={3}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={onClose} className="rounded-lg border border-white/[0.08] px-4 py-2 text-xs text-gray-400 hover:text-white">Cancel</button>
            <button
              onClick={() => name.trim() && onCreate(name.trim(), desc.trim())}
              disabled={!name.trim()}
              className="rounded-lg bg-purple-600 px-4 py-2 text-xs font-medium text-white hover:bg-purple-700 disabled:opacity-50"
            >
              Create
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
