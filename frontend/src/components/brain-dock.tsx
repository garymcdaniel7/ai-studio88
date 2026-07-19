"use client";

import { useState } from "react";
import { Brain, Send, X, Maximize2 } from "lucide-react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

/**
 * BrainDock — Persistent mini-chat bar visible on all pages except /brain.
 *
 * Click to expand inline quick-chat, or maximize to go to full Brain page.
 * Sends messages to /aios/v1/hermes/chat for quick responses.
 */
export function BrainDock() {
  const [expanded, setExpanded] = useState(false);
  const [input, setInput] = useState("");
  const [reply, setReply] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function sendQuickMessage() {
    if (!input.trim() || loading) return;
    setLoading(true);
    setReply("");

    try {
      const resp = await fetch(`${API_BASE}/aios/v1/hermes/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input, mode: "creative" }),
      });
      const data = await resp.json();
      setReply(data.response || data.message || "Brain is offline. Try the full Brain page.");
    } catch {
      setReply("Could not reach the Brain. Check if the backend is running.");
    } finally {
      setLoading(false);
      setInput("");
    }
  }

  if (!expanded) {
    return (
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 hidden md:flex">
        <button
          onClick={() => setExpanded(true)}
          className="flex items-center gap-2 rounded-full border border-purple-500/30 bg-[#12122a]/90 backdrop-blur-xl px-5 py-2.5 text-sm text-gray-300 hover:border-purple-500/60 hover:text-white transition-all shadow-lg shadow-purple-500/10"
        >
          <Brain className="h-4 w-4 text-purple-400" />
          <span>Ask Brain anything...</span>
          <kbd className="rounded border border-white/[0.1] bg-white/[0.04] px-1.5 py-0.5 text-[10px] text-gray-500 ml-2">⌘K</kbd>
        </button>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-full max-w-xl px-4">
      <div className="rounded-2xl border border-purple-500/30 bg-[#0d0d20]/95 backdrop-blur-xl shadow-2xl shadow-purple-500/10 overflow-hidden">
        {/* Reply area */}
        {reply && (
          <div className="px-4 py-3 border-b border-white/[0.06] max-h-32 overflow-y-auto">
            <p className="text-sm text-gray-300 whitespace-pre-wrap">{reply}</p>
          </div>
        )}

        {/* Thinking indicator */}
        {loading && (
          <div className="px-4 py-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <span className="text-sm text-purple-300">Thinking</span>
              <span className="flex gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "300ms" }} />
              </span>
            </div>
          </div>
        )}

        {/* Input area */}
        <div className="flex items-center gap-2 px-4 py-3">
          <Brain className="h-4 w-4 text-purple-400 shrink-0" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendQuickMessage()}
            placeholder="Ask Brain anything..."
            className="flex-1 bg-transparent text-sm text-white placeholder:text-gray-500 outline-none"
            autoFocus
          />
          <button
            onClick={sendQuickMessage}
            disabled={!input.trim() || loading}
            className="p-1.5 rounded-lg text-purple-400 hover:bg-purple-500/20 disabled:opacity-30 transition-colors"
          >
            <Send className="h-4 w-4" />
          </button>
          <button
            onClick={() => router.push("/brain")}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.06] transition-colors"
            title="Open full Brain"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
          <button
            onClick={() => { setExpanded(false); setReply(""); }}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.06] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
