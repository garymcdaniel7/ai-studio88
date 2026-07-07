"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

import { useState, useRef, useEffect } from "react";
import { X, Send, Brain, Loader2 } from "lucide-react";

interface Message {
  role: "user" | "brain";
  content: string;
  time: string;
}

export function BrainChatPanel({ onClose }: { onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([
    { role: "brain", content: "Hey! I'm your AI Brain. Ask me anything — brainstorm ideas, write prompts, plan content, or just chat.", time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    if (!input.trim() || loading) return;
    const userMsg: Message = { role: "user", content: input.trim(), time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const resp = await fetch(`${API_BASE}/api/v1/brain/llm/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [...messages, userMsg].map((m) => ({
            role: m.role === "brain" ? "assistant" : m.role,
            content: m.content,
          })),
        }),
      });
      const data = await resp.json();
      const reply = data.response || data.detail || "Sorry, I couldn't process that.";
      setMessages((prev) => [...prev, {
        role: "brain",
        content: reply,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      }]);
    } catch {
      setMessages((prev) => [...prev, {
        role: "brain",
        content: "Connection issue. Make sure Ollama is running (Admin → Services).",
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-96 h-[500px] rounded-2xl border border-white/[0.1] bg-[#0f0f24] shadow-2xl flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-[#12122a]">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-purple-600/30">
            <Brain className="h-4 w-4 text-purple-400" />
          </div>
          <div>
            <p className="text-xs font-semibold text-white">AI Brain</p>
            <p className="text-[10px] text-gray-500">Always here to help</p>
          </div>
        </div>
        <button onClick={onClose} className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[280px] rounded-2xl px-3 py-2 ${
              msg.role === "user"
                ? "bg-purple-600/20 border border-purple-500/20"
                : "bg-white/[0.03] border border-white/[0.06]"
            }`}>
              <p className="text-xs text-gray-200 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
              <p className="mt-0.5 text-[9px] text-gray-600">{msg.time}</p>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-white/[0.03] border border-white/[0.06] px-3 py-2">
              <Loader2 className="h-4 w-4 animate-spin text-purple-400" />
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-white/[0.06] p-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="Ask anything..."
            className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-gray-200 placeholder:text-gray-600 outline-none focus:border-purple-500/50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="rounded-lg bg-purple-600 p-2 text-white hover:bg-purple-700 disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
