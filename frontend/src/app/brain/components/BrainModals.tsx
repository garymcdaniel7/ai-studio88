"use client";

import type { ChatMessage, BrainMemory } from "../types";

// =============================================================================
// Memory Modal
// =============================================================================

interface MemoryModalProps {
  brainMemory: BrainMemory | null;
  onClose: () => void;
}

export function MemoryModal({ brainMemory, onClose }: MemoryModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white">Brain Memory</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">&times;</button>
        </div>
        <p className="text-xs text-gray-500 mb-4">Everything the AI Brain remembers about your preferences, workflows, and creative style.</p>
        {brainMemory ? (
          <div className="space-y-3">
            {Object.entries(brainMemory).map(([key, value]) => (
              <div key={key} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                <p className="text-xs font-medium text-gray-300 capitalize">{key.replace(/_/g, " ")}</p>
                <p className="text-[11px] text-gray-500 mt-1">{Array.isArray(value) ? (value as string[]).join(", ") : String(value)}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500 text-center py-8">No memory data yet. Chat with the Brain to build preferences.</p>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// Suggestions Modal
// =============================================================================

interface SuggestionsModalProps {
  onSelect: (prompt: string) => void;
  onClose: () => void;
}

export function SuggestionsModal({ onSelect, onClose }: SuggestionsModalProps) {
  const suggestions = [
    { title: "Continue this creative direction", desc: "Build on what we discussed — refine the concept further" },
    { title: "Generate a prompt from our chat", desc: "Turn our conversation into a production-ready image/video prompt" },
    { title: "Create a storyboard outline", desc: "Map out the visual sequence for this concept" },
    { title: "Suggest music/audio direction", desc: "Recommend genres, mood, and tempo for this project" },
    { title: "Write a TikTok/Reel script", desc: "Short-form hook + content + CTA based on our ideas" },
    { title: "Train a LoRA for this style", desc: "Capture the visual direction as a reusable AI model" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white">AI Suggestions</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">&times;</button>
        </div>
        <p className="text-xs text-gray-500 mb-4">Contextual suggestions based on your current project and workflow.</p>
        <div className="space-y-2">
          {suggestions.map((s) => (
            <button
              key={s.title}
              onClick={() => { onSelect(s.title); onClose(); }}
              className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-left hover:bg-white/[0.04]"
            >
              <p className="text-sm font-medium text-gray-200">{s.title}</p>
              <p className="text-xs text-gray-500 mt-0.5">{s.desc}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Share Modal
// =============================================================================

interface ShareModalProps {
  messages: ChatMessage[];
  sessionTitle: string;
  onClose: () => void;
}

export function ShareModal({ messages, sessionTitle, onClose }: ShareModalProps) {
  const toText = () =>
    messages.map((m) => `${m.role === "user" ? "You" : "Brain"}: ${m.content}`).join("\n\n");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white">Share Conversation</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">&times;</button>
        </div>
        <div className="space-y-3">
          <ShareOption
            emoji="📋"
            title="Copy to Clipboard"
            desc="Copy full conversation text"
            onClick={() => { navigator.clipboard.writeText(toText()); onClose(); }}
          />
          <ShareOption
            emoji="📧"
            title="Share via Email"
            desc="Open email client with conversation"
            onClick={() => {
              const subject = `AI Studio Brain Chat — ${sessionTitle}`;
              window.open(`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(toText())}`);
              onClose();
            }}
          />
          <ShareOption
            emoji="💬"
            title="Share via SMS / iMessage"
            desc="Send conversation summary"
            onClick={() => {
              window.open(`sms:&body=${encodeURIComponent(toText().slice(0, 1000))}`);
              onClose();
            }}
          />
          <ShareOption
            emoji="📄"
            title="Download as Text"
            desc="Save .txt file to your device"
            onClick={() => {
              const blob = new Blob([toText()], { type: "text/plain" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `brain-chat-${new Date().toISOString().slice(0, 10)}.txt`;
              a.click();
              URL.revokeObjectURL(url);
              onClose();
            }}
          />
        </div>
      </div>
    </div>
  );
}

function ShareOption({ emoji, title, desc, onClick }: { emoji: string; title: string; desc: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 hover:bg-white/[0.04]"
    >
      <span className="text-lg">{emoji}</span>
      <div className="text-left">
        <p className="text-sm font-medium text-white">{title}</p>
        <p className="text-[10px] text-gray-500">{desc}</p>
      </div>
    </button>
  );
}
