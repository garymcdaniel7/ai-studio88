"use client";

import { useState, useCallback } from "react";
import { Send, ImageIcon, Code, Mic, Loader2 } from "lucide-react";
import type { BrainHealthStatus } from "../_hooks/use-brain-health";

interface ComposerProps {
  onSend: (input: string, attachedImage?: string | null, preview?: string | null) => void;
  loading: boolean;
  brainOnline: boolean;
  /** Tri-state engine health; falls back to a boolean derivation when omitted. */
  brainHealth?: BrainHealthStatus;
}

const STATUS_FOOTNOTES: Record<BrainHealthStatus, string> = {
  healthy: "🟢 Hermes online",
  degraded: "🟡 Degraded — answering via fallback provider",
  offline: "🔴 Brain offline — check Admin → Services",
};

/**
 * Chat input composer with attachments, voice, and code block support.
 * Replaces window globals for image attachment with React state.
 *
 * Disabled states:
 * - While a request is in flight the whole composer locks (textarea included)
 *   so drafts cannot be double-sent mid-turn.
 * - When the engine is offline, sending is blocked but drafting still works,
 *   with the status footnote explaining why Send is unavailable.
 */
export function Composer({ onSend, loading, brainOnline, brainHealth }: ComposerProps) {
  const [input, setInput] = useState("");
  const [attachedImage, setAttachedImage] = useState<string | null>(null);
  const [attachedPreview, setAttachedPreview] = useState<string | null>(null);

  const health: BrainHealthStatus = brainHealth ?? (brainOnline ? "healthy" : "offline");
  const offline = health === "offline";

  const handleSend = useCallback(() => {
    if (!input.trim() || loading || offline) return;
    onSend(input, attachedImage, attachedPreview);
    setInput("");
    setAttachedImage(null);
    setAttachedPreview(null);
  }, [input, loading, offline, onSend, attachedImage, attachedPreview]);

  const handleFileAttach = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      const base64 = dataUrl?.split(",")[1] || "";
      setAttachedPreview(dataUrl);
      setAttachedImage(base64);
    };
    reader.readAsDataURL(file);
  }, []);

  const handleVoiceInput = useCallback(() => {
    if (!("webkitSpeechRecognition" in window) && !("SpeechRecognition" in window)) {
      alert("Speech recognition not supported in this browser. Use Chrome.");
      return;
    }
    const SpeechRecognition = (window as unknown as Record<string, unknown>).SpeechRecognition ||
      (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
    const recognition = new (SpeechRecognition as new () => {
      lang: string;
      continuous: boolean;
      onresult: (e: { results: { transcript: string }[][] }) => void;
      onerror: () => void;
      start: () => void;
    })();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      setInput((prev) => prev + (prev ? " " : "") + transcript);
    };
    recognition.onerror = () => {};
    recognition.start();
  }, []);

  const canSend = Boolean(input.trim()) && !loading && !offline;
  const toolButtonClasses = loading
    ? "p-1.5 text-gray-600 cursor-not-allowed"
    : "p-1.5 text-gray-500 hover:text-gray-300";

  return (
    <div className="border-t border-white/[0.06] p-4">
      {/* Attached Image Preview */}
      {attachedPreview && (
        <div className="mb-2 flex items-center gap-2 rounded-lg border border-purple-500/20 bg-purple-500/5 px-3 py-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={attachedPreview} alt="Attached" className="h-10 w-10 rounded object-cover" />
          <span className="text-xs text-purple-300 flex-1">Image attached — will be analyzed on send</span>
          <button
            onClick={() => { setAttachedPreview(null); setAttachedImage(null); }}
            className="text-xs text-gray-500 hover:text-red-400"
            aria-label="Remove attached image"
          >
            &times;
          </button>
        </div>
      )}
      <div className={`flex items-end gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] p-3 ${loading ? "opacity-70" : ""}`}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          disabled={loading}
          aria-disabled={loading}
          aria-busy={loading}
          placeholder={offline
            ? "Brain is offline — you can keep drafting, sending is paused"
            : 'Ask anything... (e.g., "Create a prompt for a product commercial")'}
          className="flex-1 resize-none bg-transparent text-sm text-gray-200 placeholder:text-gray-600 outline-none disabled:cursor-not-allowed"
          rows={1}
        />
        <div className="flex items-center gap-1">
          <label className={toolButtonClasses} title="Attach image" aria-label="Attach image" aria-disabled={loading}>
            <ImageIcon className="h-4 w-4" />
            <input
              type="file"
              accept="image/*"
              className="hidden"
              disabled={loading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileAttach(file);
                e.target.value = "";
              }}
            />
          </label>
          <button
            className={toolButtonClasses}
            title="Code block"
            aria-label="Insert code block"
            disabled={loading}
            onClick={() => setInput((prev) => prev + "\n```\n\n```")}
          >
            <Code className="h-4 w-4" />
          </button>
          <button
            className={toolButtonClasses}
            title="Voice to text"
            aria-label="Voice to text"
            disabled={loading}
            onClick={handleVoiceInput}
          >
            <Mic className="h-4 w-4" />
          </button>
          <button
            onClick={handleSend}
            disabled={!canSend}
            aria-label="Send message"
            aria-busy={loading}
            className="ml-2 rounded-lg bg-purple-600 p-2 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
      <p className="mt-1 text-center text-[10px] text-gray-600" role="status">
        {STATUS_FOOTNOTES[health]}
      </p>
    </div>
  );
}

/** Quick action pills above the composer */
export function QuickActions({ onSelect }: { onSelect: (prompt: string) => void }) {
  const actions = [
    { label: "Create Storyboard", prompt: "Help me create a storyboard for a short video. Ask me about the concept, target audience, and mood." },
    { label: "Generate Prompt", prompt: "Help me write an optimized image generation prompt. Ask me what I want to create." },
    { label: "Brainstorm Ideas", prompt: "Let's brainstorm creative content ideas together. What's the project or campaign about?" },
    { label: "Suggest Music", prompt: "Suggest music tracks or instrumentals for my video project. What's the mood and genre?" },
  ];

  return (
    <div className="flex gap-2 px-6 py-2">
      {actions.map((action) => (
        <button
          key={action.label}
          onClick={() => onSelect(action.prompt)}
          className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-xs text-gray-400 hover:bg-white/[0.05] hover:text-gray-200"
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}
