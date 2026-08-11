"use client";

import { Brain, Film, Sparkles, Heart, Zap, Wand2, ArrowRight } from "lucide-react";

interface ContextSidebarProps {
  brainMemory: Record<string, unknown> | null;
  onShowMemory: () => void;
  onShowSuggestions: () => void;
}

/**
 * Right sidebar showing active project, brain memory, and suggestions.
 */
export function ContextSidebar({ brainMemory, onShowMemory, onShowSuggestions }: ContextSidebarProps) {
  return (
    <div className="border-l border-white/[0.06] p-4 overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Brain Context</h3>
        <button className="text-xs text-gray-400">Edit</button>
      </div>

      {/* Active Project */}
      <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 mb-4">
        <p className="text-[10px] text-gray-500 uppercase mb-1">Active Project</p>
        <p className="text-sm font-medium text-white">No active project</p>
        <p className="text-xs text-gray-500">Select a project from Production</p>
      </div>

      {/* Brain Memory */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-semibold text-white">Brain Memory</h4>
          <button onClick={onShowMemory} className="text-[10px] text-purple-400 hover:text-purple-300">View all</button>
        </div>
        <div className="space-y-2">
          {brainMemory ? (
            <MemoryEntries memory={brainMemory} />
          ) : (
            <DefaultMemoryPlaceholders />
          )}
        </div>
      </div>

      {/* Suggestions */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-semibold text-white">Suggestions</h4>
          <button onClick={onShowSuggestions} className="text-[10px] text-purple-400 hover:text-purple-300">View all</button>
        </div>
        <div className="space-y-2">
          {[
            { title: "Optimize this prompt for FLUX", desc: "Improve image generation results" },
            { title: "Try this camera movement", desc: "Dolly in + slight tilt for more impact" },
            { title: "Consider this color grade", desc: "Teal & Orange for luxury feel" },
          ].map((s) => (
            <button key={s.title} className="w-full flex items-center justify-between rounded-lg border border-white/[0.04] bg-white/[0.02] p-2.5 text-left hover:bg-white/[0.04]">
              <div>
                <p className="text-xs font-medium text-gray-200">{s.title}</p>
                <p className="text-[10px] text-gray-500">{s.desc}</p>
              </div>
              <ArrowRight className="h-3.5 w-3.5 text-gray-500" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function MemoryEntries({ memory }: { memory: Record<string, unknown> }) {
  const entries: { key: string; icon: typeof Zap; color: string; label: string }[] = [
    { key: "favorite_models", icon: Zap, color: "text-green-400", label: "Preferred models" },
    { key: "favorite_camera_moves", icon: Film, color: "text-blue-400", label: "Favorite camera" },
    { key: "favorite_lighting", icon: Sparkles, color: "text-amber-400", label: "Lighting style" },
    { key: "favorite_prompts", icon: Heart, color: "text-pink-400", label: "Favorite prompts" },
    { key: "favorite_workflows", icon: Brain, color: "text-purple-400", label: "Workflows" },
    { key: "favorite_editing_style", icon: Wand2, color: "text-cyan-400", label: "Editing style" },
  ];

  return (
    <>
      {entries.map(({ key, icon: Icon, color, label }) =>
        memory[key] ? (
          <div key={key} className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
            <Icon className={`h-3.5 w-3.5 mt-0.5 ${color}`} />
            <div>
              <p className="text-xs font-medium text-gray-200">{label}</p>
              <p className="text-[10px] text-gray-500">
                {Array.isArray(memory[key]) ? (memory[key] as string[]).slice(0, 3).join(", ") : String(memory[key])}
              </p>
            </div>
          </div>
        ) : null
      )}
    </>
  );
}

function DefaultMemoryPlaceholders() {
  return (
    <>
      {[
        { icon: Zap, title: "Knows your brand voice", desc: "Updated 2 days ago", color: "text-green-400" },
        { icon: Heart, title: "Remembered your preferences", desc: "You prefer cinematic visual style", color: "text-pink-400" },
        { icon: Brain, title: "Understands your workflow", desc: "You use FLUX for images", color: "text-blue-400" },
      ].map((mem) => (
        <div key={mem.title} className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
          <mem.icon className={`h-3.5 w-3.5 mt-0.5 ${mem.color}`} />
          <div>
            <p className="text-xs font-medium text-gray-200">{mem.title}</p>
            <p className="text-[10px] text-gray-500">{mem.desc}</p>
          </div>
        </div>
      ))}
    </>
  );
}
