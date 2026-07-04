"use client";

import { useState, useEffect } from "react";
import { BookOpen, Plus, Users, Film, ArrowLeft, Loader2 } from "lucide-react";

interface Universe {
  id: string;
  name: string;
  description?: string;
  genre?: string;
  target_platform?: string;
}

interface Character {
  id: string;
  name: string;
  description?: string;
  traits?: string[];
  role?: string;
  universe_id: string;
}

interface Episode {
  id: string;
  title: string;
  synopsis?: string;
  season?: number;
  episode_number?: number;
  universe_id: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function StoryPage() {
  const [universes, setUniverses] = useState<Universe[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewForm, setShowNewForm] = useState(false);
  const [selectedUniverse, setSelectedUniverse] = useState<Universe | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [showCharForm, setShowCharForm] = useState(false);
  const [showEpForm, setShowEpForm] = useState(false);

  // New story form
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newGenre, setNewGenre] = useState("");
  const [newPlatform, setNewPlatform] = useState("");

  // New character form
  const [charName, setCharName] = useState("");
  const [charDesc, setCharDesc] = useState("");
  const [charTraits, setCharTraits] = useState("");
  const [charRole, setCharRole] = useState("");

  // New episode form
  const [epTitle, setEpTitle] = useState("");
  const [epSynopsis, setEpSynopsis] = useState("");
  const [epSeason, setEpSeason] = useState("1");
  const [epNumber, setEpNumber] = useState("1");

  useEffect(() => {
    fetchUniverses();
  }, []);

  async function fetchUniverses() {
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/universes`);
      const data = await resp.json();
      setUniverses(Array.isArray(data) ? data : []);
    } catch {
      setUniverses([]);
    } finally {
      setLoading(false);
    }
  }

  async function createUniverse() {
    if (!newTitle.trim()) return;
    try {
      const resp = await fetch(`${API_BASE}/api/v1/universes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newTitle,
          description: newDesc,
          genre: newGenre,
          target_platform: newPlatform,
        }),
      });
      if (resp.ok) {
        setShowNewForm(false);
        setNewTitle("");
        setNewDesc("");
        setNewGenre("");
        setNewPlatform("");
        fetchUniverses();
      }
    } catch {}
  }

  async function selectUniverse(u: Universe) {
    setSelectedUniverse(u);
    try {
      const [charResp, epResp] = await Promise.all([
        fetch(`${API_BASE}/api/v1/universes/${u.id}/characters`),
        fetch(`${API_BASE}/api/v1/universes/${u.id}/episodes`),
      ]);
      const charData = await charResp.json();
      const epData = await epResp.json();
      setCharacters(Array.isArray(charData) ? charData : []);
      setEpisodes(Array.isArray(epData) ? epData : []);
    } catch {
      setCharacters([]);
      setEpisodes([]);
    }
  }

  async function createCharacter() {
    if (!charName.trim() || !selectedUniverse) return;
    try {
      const resp = await fetch(`${API_BASE}/api/v1/characters`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: charName,
          description: charDesc,
          traits: charTraits.split(",").map((t) => t.trim()).filter(Boolean),
          role: charRole,
          universe_id: selectedUniverse.id,
        }),
      });
      if (resp.ok) {
        setShowCharForm(false);
        setCharName("");
        setCharDesc("");
        setCharTraits("");
        setCharRole("");
        selectUniverse(selectedUniverse);
      }
    } catch {}
  }

  async function createEpisode() {
    if (!epTitle.trim() || !selectedUniverse) return;
    try {
      const resp = await fetch(`${API_BASE}/api/v1/episodes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: epTitle,
          synopsis: epSynopsis,
          season: parseInt(epSeason) || 1,
          episode_number: parseInt(epNumber) || 1,
          universe_id: selectedUniverse.id,
        }),
      });
      if (resp.ok) {
        setShowEpForm(false);
        setEpTitle("");
        setEpSynopsis("");
        setEpSeason("1");
        setEpNumber("1");
        selectUniverse(selectedUniverse);
      }
    } catch {}
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
      </div>
    );
  }

  // Detail view for a selected universe
  if (selectedUniverse) {
    return (
      <div className="space-y-6">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1">
          <button onClick={() => setSelectedUniverse(null)} className="hover:text-gray-300">Stories</button>
          <span>/</span>
          <span className="text-gray-300">{selectedUniverse.name}</span>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setSelectedUniverse(null)}
            className="rounded-lg border border-white/[0.08] p-2 text-gray-400 hover:bg-white/[0.04]"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-white">{selectedUniverse.name}</h1>
            <p className="text-sm text-gray-500">{selectedUniverse.description || "No description"}</p>
          </div>
        </div>

        {/* Characters */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Users className="h-4 w-4 text-purple-400" /> Characters
            </h3>
            <button
              onClick={() => setShowCharForm(true)}
              className="flex items-center gap-1 rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700"
            >
              <Plus className="h-3 w-3" /> Add Character
            </button>
          </div>
          {showCharForm && (
            <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 mb-4 space-y-3">
              <input value={charName} onChange={(e) => setCharName(e.target.value)} placeholder="Character name" className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none" />
              <input value={charDesc} onChange={(e) => setCharDesc(e.target.value)} placeholder="Description" className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none" />
              <input value={charTraits} onChange={(e) => setCharTraits(e.target.value)} placeholder="Traits (comma-separated)" className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none" />
              <input value={charRole} onChange={(e) => setCharRole(e.target.value)} placeholder="Role (protagonist, antagonist...)" className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none" />
              <div className="flex gap-2">
                <button onClick={createCharacter} className="rounded-lg bg-purple-600 px-4 py-2 text-xs text-white hover:bg-purple-700">Create</button>
                <button onClick={() => setShowCharForm(false)} className="rounded-lg border border-white/[0.08] px-4 py-2 text-xs text-gray-400 hover:bg-white/[0.04]">Cancel</button>
              </div>
            </div>
          )}
          <div className="grid grid-cols-3 gap-3">
            {characters.map((c) => (
              <div key={c.id} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4">
                <p className="text-sm font-semibold text-white">{c.name}</p>
                {c.role && <p className="text-[10px] text-purple-400 uppercase mt-0.5">{c.role}</p>}
                {c.description && <p className="text-xs text-gray-500 mt-1">{c.description}</p>}
                {c.traits && c.traits.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {c.traits.map((t, i) => (
                      <span key={i} className="rounded bg-purple-600/20 px-1.5 py-0.5 text-[10px] text-purple-300">{t}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {characters.length === 0 && <p className="text-xs text-gray-600 col-span-3">No characters yet</p>}
          </div>
        </div>

        {/* Episodes */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Film className="h-4 w-4 text-blue-400" /> Episodes
            </h3>
            <button
              onClick={() => setShowEpForm(true)}
              className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
            >
              <Plus className="h-3 w-3" /> Add Episode
            </button>
          </div>
          {showEpForm && (
            <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 mb-4 space-y-3">
              <input value={epTitle} onChange={(e) => setEpTitle(e.target.value)} placeholder="Episode title" className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none" />
              <textarea value={epSynopsis} onChange={(e) => setEpSynopsis(e.target.value)} placeholder="Synopsis" rows={2} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none resize-none" />
              <div className="flex gap-3">
                <input value={epSeason} onChange={(e) => setEpSeason(e.target.value)} placeholder="Season" type="number" className="w-24 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none" />
                <input value={epNumber} onChange={(e) => setEpNumber(e.target.value)} placeholder="Episode #" type="number" className="w-24 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none" />
              </div>
              <div className="flex gap-2">
                <button onClick={createEpisode} className="rounded-lg bg-blue-600 px-4 py-2 text-xs text-white hover:bg-blue-700">Create</button>
                <button onClick={() => setShowEpForm(false)} className="rounded-lg border border-white/[0.08] px-4 py-2 text-xs text-gray-400 hover:bg-white/[0.04]">Cancel</button>
              </div>
            </div>
          )}
          <div className="space-y-2">
            {episodes.map((ep) => (
              <div key={ep.id} className="rounded-xl border border-white/[0.06] bg-[#12122a] p-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-white">{ep.title}</p>
                  <p className="text-xs text-gray-500">S{ep.season || 1}E{ep.episode_number || 1}{ep.synopsis ? ` — ${ep.synopsis}` : ""}</p>
                </div>
              </div>
            ))}
            {episodes.length === 0 && <p className="text-xs text-gray-600">No episodes yet</p>}
          </div>
        </div>
      </div>
    );
  }

  // Universe list view
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Story</h1>
          <p className="text-sm text-gray-500">Story engine — series, episodes, scenes, scripts, and continuity.</p>
        </div>
        <button
          onClick={() => setShowNewForm(true)}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700"
        >
          <Plus className="h-4 w-4" /> New Story
        </button>
      </div>

      {showNewForm && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-6 space-y-4">
          <h3 className="text-sm font-semibold text-white">Create Story Universe</h3>
          <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Title" className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 outline-none" />
          <textarea value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Description" rows={2} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 outline-none resize-none" />
          <div className="flex gap-3">
            <input value={newGenre} onChange={(e) => setNewGenre(e.target.value)} placeholder="Genre (e.g. Sci-Fi)" className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 outline-none" />
            <input value={newPlatform} onChange={(e) => setNewPlatform(e.target.value)} placeholder="Target platform" className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 outline-none" />
          </div>
          <div className="flex gap-2">
            <button onClick={createUniverse} className="rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700">Create</button>
            <button onClick={() => setShowNewForm(false)} className="rounded-lg border border-white/[0.08] px-6 py-2 text-sm text-gray-400 hover:bg-white/[0.04]">Cancel</button>
          </div>
        </div>
      )}

      {universes.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {universes.map((u) => (
            <button
              key={u.id}
              onClick={() => selectUniverse(u)}
              className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5 text-left hover:border-purple-500/30 transition-all"
            >
              <div className="flex items-center gap-2 mb-2">
                <BookOpen className="h-5 w-5 text-purple-400" />
                <h4 className="text-sm font-semibold text-white">{u.name}</h4>
              </div>
              {u.description && <p className="text-xs text-gray-500">{u.description}</p>}
              <div className="flex gap-2 mt-3">
                {u.genre && <span className="rounded bg-purple-600/20 px-1.5 py-0.5 text-[10px] text-purple-300">{u.genre}</span>}
                {u.target_platform && <span className="rounded bg-blue-600/20 px-1.5 py-0.5 text-[10px] text-blue-300">{u.target_platform}</span>}
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-8 text-center">
          <BookOpen className="h-12 w-12 text-gray-600 mx-auto mb-3" />
          <p className="text-sm text-gray-400">Create your first story universe</p>
          <p className="text-xs text-gray-600 mt-1">Stories contain series, episodes, scenes, and shots with full continuity tracking.</p>
        </div>
      )}
    </div>
  );
}
