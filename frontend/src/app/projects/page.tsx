"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, FolderOpen, Loader2, Archive, MoreHorizontal } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

interface Project {
  id: string;
  name: string;
  description: string;
  status: string;
  category: string;
  color: string;
  asset_count: number;
  generation_count: number;
  total_cost: number;
  talent_ids: string[];
  tags: string[];
  created_at: string;
  updated_at: string;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newCategory, setNewCategory] = useState("campaign");

  useEffect(() => {
    loadProjects();
  }, []);

  async function loadProjects() {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/projects`);
      const data = await resp.json();
      setProjects(data.projects || []);
    } catch {} finally {
      setLoading(false);
    }
  }

  async function createProject() {
    if (!newName.trim()) return;
    try {
      await fetch(`${API_BASE}/api/v1/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName, description: newDesc, category: newCategory }),
      });
      setNewName("");
      setNewDesc("");
      setShowCreate(false);
      await loadProjects();
    } catch {}
  }

  async function archiveProject(id: string) {
    await fetch(`${API_BASE}/api/v1/projects/${id}`, { method: "DELETE" });
    await loadProjects();
  }

  const activeProjects = projects.filter((p) => p.status === "active");
  const archivedProjects = projects.filter((p) => p.status === "archived");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Projects</h1>
          <p className="text-sm text-gray-500">Organize your campaigns, collections, and creative work.</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 transition-colors"
        >
          <Plus className="h-4 w-4" /> New Project
        </button>
      </div>

      {/* Create Project Modal */}
      {showCreate && (
        <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-6 space-y-4">
          <h3 className="text-sm font-semibold text-purple-300">Create New Project</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-medium text-gray-400 mb-1">Project Name</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Summer Campaign 2026"
                className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-gray-600 outline-none focus:border-purple-500"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-[10px] font-medium text-gray-400 mb-1">Category</label>
              <select
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white outline-none"
              >
                <option value="campaign">Campaign</option>
                <option value="collection">Collection</option>
                <option value="story">Story / Series</option>
                <option value="product">Product Shoot</option>
                <option value="personal">Personal</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-[10px] font-medium text-gray-400 mb-1">Description (optional)</label>
            <input
              type="text"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Brief description of the project..."
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-gray-600 outline-none"
            />
          </div>
          <div className="flex gap-2">
            <button onClick={createProject} disabled={!newName.trim()} className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50">
              Create Project
            </button>
            <button onClick={() => setShowCreate(false)} className="rounded-lg border border-white/[0.08] px-4 py-2 text-sm text-gray-400 hover:text-white">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
        </div>
      )}

      {/* Projects Grid */}
      {!loading && activeProjects.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {activeProjects.map((project) => (
            <div
              key={project.id}
              className="rounded-xl border border-white/[0.06] bg-[#12122a] p-5 hover:border-purple-500/30 transition-colors group"
            >
              {/* Color bar */}
              <div className="h-1 w-12 rounded-full mb-4" style={{ backgroundColor: project.color }} />

              <div className="flex items-start justify-between">
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-semibold text-white truncate">{project.name}</h3>
                  <p className="text-xs text-gray-500 mt-0.5 truncate">{project.description || project.category}</p>
                </div>
                <button
                  onClick={() => archiveProject(project.id)}
                  className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-gray-500 hover:text-amber-400 hover:bg-amber-400/10 transition-all"
                  title="Archive project"
                >
                  <Archive className="h-3.5 w-3.5" />
                </button>
              </div>

              {/* Stats */}
              <div className="flex items-center gap-4 mt-4 text-[11px] text-gray-500">
                <span>{project.asset_count} assets</span>
                <span>{project.generation_count} generated</span>
                <span>${project.total_cost.toFixed(2)} spent</span>
              </div>

              {/* Tags */}
              {project.tags.length > 0 && (
                <div className="flex gap-1.5 mt-3 flex-wrap">
                  {project.tags.slice(0, 3).map((tag) => (
                    <span key={tag} className="rounded-full bg-white/[0.04] px-2 py-0.5 text-[10px] text-gray-400">
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              {/* Footer */}
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-white/[0.04]">
                <span className="text-[10px] text-gray-600">
                  {new Date(project.created_at).toLocaleDateString()}
                </span>
                <Link
                  href={`/brain?prompt=Continue working on ${project.name}`}
                  className="text-[10px] text-purple-400 hover:text-purple-300 font-medium"
                >
                  Open in Brain →
                </Link>
              </div>
            </div>
          ))}

          {/* New Project Card */}
          <button
            onClick={() => setShowCreate(true)}
            className="rounded-xl border-2 border-dashed border-white/[0.08] p-5 hover:border-purple-500/30 transition-colors flex flex-col items-center justify-center min-h-[180px] text-center"
          >
            <Plus className="h-8 w-8 text-gray-600 mb-2" />
            <p className="text-sm text-gray-400">New Project</p>
            <p className="text-[10px] text-gray-600 mt-1">Campaign, collection, or story</p>
          </button>
        </div>
      )}

      {/* Empty State */}
      {!loading && activeProjects.length === 0 && !showCreate && (
        <div className="rounded-xl border border-white/[0.06] bg-[#12122a] p-12 text-center">
          <FolderOpen className="h-12 w-12 text-gray-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white mb-1">No projects yet</h3>
          <p className="text-sm text-gray-500 mb-4">Projects help you organize campaigns, collections, and creative work.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="rounded-lg bg-purple-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-purple-700"
          >
            Create Your First Project
          </button>
        </div>
      )}

      {/* Archived */}
      {archivedProjects.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-gray-500 mb-3">Archived ({archivedProjects.length})</h3>
          <div className="space-y-2">
            {archivedProjects.map((p) => (
              <div key={p.id} className="flex items-center gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-2 opacity-60">
                <Archive className="h-3.5 w-3.5 text-gray-500" />
                <span className="text-sm text-gray-400">{p.name}</span>
                <span className="text-[10px] text-gray-600 ml-auto">{p.category}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
