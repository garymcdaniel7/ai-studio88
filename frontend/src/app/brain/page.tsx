"use client";

import { useState, useEffect } from "react";
import {
  Brain,
  MessageSquare,
  Wand2,
  BookOpen,
  Film,
  Search,
  ImageIcon,
  Plus,
  Settings,
  Send,
  Paperclip,
  Code,
  Mic,
  MoreHorizontal,
  Sparkles,
  Heart,
  Zap,
  ArrowRight,
} from "lucide-react";
import { getBrainSessions, getBrainHealth } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const modes = [
  { name: "Creative Chat", desc: "General conversations", icon: MessageSquare, key: "creative" },
  { name: "Prompt Engineer", desc: "Improve your prompts", icon: Wand2, key: "prompt_engineer" },
  { name: "Story Assistant", desc: "Develop stories & scripts", icon: BookOpen, key: "story_assistant" },
  { name: "Production Advisor", desc: "Plan & optimize workflows", icon: Film, key: "production_advisor" },
  { name: "Research", desc: "Search the web & docs", icon: Search, key: "research" },
  { name: "Image Analyzer", desc: "Analyze images & assets", icon: ImageIcon, key: "image_analyzer" },
];

interface ChatMessage {
  role: string;
  content: string;
  time: string;
}

interface Session {
  id: string;
  title: string;
  created_at: string;
  messages?: ChatMessage[];
}

export default function BrainPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [brainOnline, setBrainOnline] = useState(false);
  const [currentMode, setCurrentMode] = useState("creative");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);

  // Load sessions and check brain health on mount
  useEffect(() => {
    getBrainHealth()
      .then((d) => setBrainOnline(d.connected))
      .catch(() => setBrainOnline(false));

    getBrainSessions()
      .then((data) => {
        if (Array.isArray(data)) {
          setSessions(data);
        }
      })
      .catch(() => {});
  }, []);

  function startNewChat() {
    setSessionId(null);
    setMessages([]);
  }

  function loadSession(session: Session) {
    setSessionId(session.id);
    if (session.messages && Array.isArray(session.messages)) {
      setMessages(session.messages);
    } else {
      setMessages([]);
    }
  }

  async function sendMessage() {
    if (!input.trim() || loading) return;
    const userMsg: ChatMessage = {
      role: "user",
      content: input,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const resp = await fetch(`${API_BASE}/api/v1/brain/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: input,
          session_id: sessionId,
          mode: currentMode,
          messages: [...messages, userMsg].map((m) => ({
            role: m.role === "brain" ? "assistant" : m.role,
            content: m.content,
          })),
        }),
      });
      const data = await resp.json();

      // Store session_id from first response
      if (data.session_id && !sessionId) {
        setSessionId(data.session_id);
        // Add to session list
        const newSession: Session = {
          id: data.session_id,
          title: input.slice(0, 40) || "New Chat",
          created_at: new Date().toISOString(),
        };
        setSessions((prev) => [newSession, ...prev]);
      }

      const brainMsg: ChatMessage = {
        role: "brain",
        content: data.response || data.detail || "No response",
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, brainMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "brain",
          content: "Brain is offline. Start Ollama: `ollama serve`",
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4 -m-6">
      {/* Header */}
      <div className="flex items-center justify-between px-6 pt-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            AI Brain <Sparkles className="h-5 w-5 text-purple-400" />
          </h1>
          <p className="text-sm text-gray-500">
            Your creative co-pilot for ideas, strategy, and production.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-lg border border-white/[0.08] px-3 py-1.5">
            <span className="text-xs text-gray-400">Model:</span>
            <span className="text-xs font-medium text-white">Claude 3.5 Sonnet</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${brainOnline ? "bg-green-500" : "bg-red-500"}`} />
            <span className={`text-xs ${brainOnline ? "text-green-400" : "text-red-400"}`}>
              {brainOnline ? "Online" : "Offline"}
            </span>
          </div>
          <button
            onClick={startNewChat}
            className="flex items-center gap-2 rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700"
          >
            <Plus className="h-3.5 w-3.5" /> New Chat
          </button>
          <button className="rounded-lg border border-white/[0.08] p-1.5 text-gray-400 hover:bg-white/[0.04]">
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Mode Cards */}
      <div className="grid grid-cols-6 gap-3 px-6">
        {modes.map((mode) => (
          <button
            key={mode.name}
            onClick={() => setCurrentMode(mode.key)}
            className={`rounded-xl border p-3 text-left transition-all ${
              currentMode === mode.key
                ? "border-purple-500/50 bg-purple-600/10"
                : "border-white/[0.06] bg-[#12122a] hover:border-purple-500/30 hover:bg-purple-600/5"
            }`}
          >
            <mode.icon className={`h-5 w-5 mb-2 ${currentMode === mode.key ? "text-purple-300" : "text-purple-400"}`} />
            <p className={`text-xs font-medium ${currentMode === mode.key ? "text-purple-300" : "text-white"}`}>{mode.name}</p>
            <p className="text-[10px] text-gray-500">{mode.desc}</p>
          </button>
        ))}
      </div>

      {/* Three-panel layout */}
      <div className="grid grid-cols-[280px_1fr_300px] gap-0 border-t border-white/[0.06]" style={{ height: "calc(100vh - 240px)" }}>
        {/* Conversations List */}
        <div className="border-r border-white/[0.06] p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white">Conversations</h3>
          </div>
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5">
            <Search className="h-3.5 w-3.5 text-gray-500" />
            <input className="flex-1 bg-transparent text-xs text-gray-300 placeholder:text-gray-600 outline-none" placeholder="Search conversations..." />
          </div>
          <div className="space-y-1">
            <p className="text-[10px] font-medium text-gray-600 uppercase px-2 mt-3">Recent</p>
            {/* Current unsaved session */}
            {!sessionId && messages.length === 0 && (
              <button
                className="w-full flex items-center justify-between rounded-lg px-3 py-2.5 text-left bg-purple-600/20 border border-purple-500/30"
              >
                <div>
                  <p className="text-sm text-purple-300 font-medium">New Chat</p>
                  <p className="text-[10px] text-gray-500">Now</p>
                </div>
                <MoreHorizontal className="h-3.5 w-3.5 text-gray-600" />
              </button>
            )}
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => loadSession(session)}
                className={`w-full flex items-center justify-between rounded-lg px-3 py-2.5 text-left transition-colors ${
                  sessionId === session.id
                    ? "bg-purple-600/20 border border-purple-500/30"
                    : "hover:bg-white/[0.03]"
                }`}
              >
                <div>
                  <p className={`text-sm ${sessionId === session.id ? "text-purple-300 font-medium" : "text-gray-300"}`}>
                    {session.title || "Untitled"}
                  </p>
                  <p className="text-[10px] text-gray-500">
                    {new Date(session.created_at).toLocaleDateString()}
                  </p>
                </div>
                <MoreHorizontal className="h-3.5 w-3.5 text-gray-600" />
              </button>
            ))}
            {sessions.length === 0 && sessionId === null && messages.length > 0 && (
              <p className="px-2 text-xs text-gray-600">No saved conversations yet</p>
            )}
          </div>
        </div>

        {/* Chat Area */}
        <div className="flex flex-col">
          {/* Chat header */}
          <div className="flex items-center justify-between border-b border-white/[0.06] px-6 py-3">
            <h3 className="text-sm font-semibold text-white">
              {sessionId ? sessions.find((s) => s.id === sessionId)?.title || "Chat" : "New Conversation"}
            </h3>
            <button className="text-xs text-gray-400 hover:text-gray-200">Share</button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {messages.length === 0 && (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <Brain className="h-12 w-12 text-purple-400/30 mx-auto mb-3" />
                  <p className="text-sm text-gray-500">Start a conversation with your AI Brain</p>
                  <p className="text-xs text-gray-600 mt-1">
                    {brainOnline ? "🟢 Ollama connected — ready to chat" : "🔴 Brain offline — start Ollama"}
                  </p>
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
                {msg.role !== "user" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-600/20">
                    <Brain className="h-4 w-4 text-purple-400" />
                  </div>
                )}
                <div className={`max-w-[600px] rounded-2xl px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-purple-600/20 border border-purple-500/20"
                    : "bg-white/[0.03] border border-white/[0.06]"
                }`}>
                  <p className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                  <p className="mt-1 text-[10px] text-gray-500">{msg.time}</p>
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-600/20">
                  <Brain className="h-4 w-4 text-purple-400 animate-pulse" />
                </div>
                <div className="rounded-2xl bg-white/[0.03] border border-white/[0.06] px-4 py-3">
                  <p className="text-sm text-gray-400">Thinking...</p>
                </div>
              </div>
            )}
          </div>

          {/* Quick Actions */}
          <div className="flex gap-2 px-6 py-2">
            {["Create Storyboard", "Generate Prompt", "Find Stock Footage", "Suggest Music"].map((action) => (
              <button key={action} className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-xs text-gray-400 hover:bg-white/[0.05] hover:text-gray-200">
                {action}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="border-t border-white/[0.06] p-4">
            <div className="flex items-end gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] p-3">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                placeholder='Ask anything... (e.g., "Create a prompt for a product commercial")'
                className="flex-1 resize-none bg-transparent text-sm text-gray-200 placeholder:text-gray-600 outline-none"
                rows={1}
              />
              <div className="flex items-center gap-1">
                <button className="p-1.5 text-gray-500 hover:text-gray-300"><Paperclip className="h-4 w-4" /></button>
                <button className="p-1.5 text-gray-500 hover:text-gray-300"><ImageIcon className="h-4 w-4" /></button>
                <button className="p-1.5 text-gray-500 hover:text-gray-300"><Code className="h-4 w-4" /></button>
                <button className="p-1.5 text-gray-500 hover:text-gray-300"><Mic className="h-4 w-4" /></button>
                <button
                  onClick={sendMessage}
                  disabled={loading || !input.trim()}
                  className="ml-2 rounded-lg bg-purple-600 p-2 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
            </div>
            <p className="mt-1 text-center text-[10px] text-gray-600">
              {brainOnline ? "🟢 Connected to Ollama (llama3.1:8b)" : "🔴 Brain offline — start Ollama"}
            </p>
          </div>
        </div>

        {/* Context Sidebar */}
        <div className="border-l border-white/[0.06] p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Brain Context</h3>
            <button className="text-xs text-gray-400">Edit</button>
          </div>

          {/* Active Project */}
          <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 mb-4">
            <p className="text-[10px] text-gray-500 uppercase mb-1">Active Project</p>
            <p className="text-sm font-medium text-white">Dubai Luxury Campaign</p>
            <p className="text-xs text-gray-500">Video Commercial</p>
          </div>

          {/* Brain Memory */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-semibold text-white">Brain Memory</h4>
              <button className="text-[10px] text-purple-400">View all</button>
            </div>
            <div className="space-y-2">
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
            </div>
          </div>

          {/* Brain Suggestions */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-semibold text-white">Suggestions</h4>
              <button className="text-[10px] text-purple-400">View all</button>
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
      </div>
    </div>
  );
}
