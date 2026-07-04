"use client";

import { useState, useEffect, useRef } from "react";
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
  FolderPlus,
  Tag,
  Filter,
} from "lucide-react";
import { getBrainSessions, getBrainHealth } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const WELCOME_MESSAGES: Record<string, string> = {
  creative: "Hey! 👋 Welcome to AI Studio. I'm your Creative Director AI. I can help you brainstorm ideas, explore concepts, develop campaigns, and push creative boundaries. What are you working on today?",
  prompt_engineer: "Let's build the perfect prompt. 🎯 Tell me what you want to create — describe the subject, mood, or concept — and I'll guide you toward a production-ready prompt optimized for Flux, SDXL, or WAN 2.1. Start simple, I'll refine it with you.",
  story_assistant: "I'm your Story Assistant. 📖 I help develop narratives for commercials, series, social content, and films. Whether it's a 15-second reel or a 10-episode series, let's build a compelling story. What's the concept?",
  production_advisor: "Production Advisor here. 📊 I help optimize your workflows, estimate GPU costs, plan pipelines, and schedule batch renders. What production challenge are you facing?",
  research: "Research mode active. 🔍 I'll help you find visual references, trending styles, competitor content, and best practices for AI content creation. What topic or style are you researching?",
  image_analyzer: "Image Analyzer ready. 🖼️ Describe an image or paste a reference, and I'll break down the composition, lighting, color palette, and suggest how to recreate or improve it with AI generation.",
};

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

interface Collection {
  id: string;
  name: string;
  color: string;
  conversationIds: string[];
}

const COLLECTION_COLORS = ["#8b5cf6", "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#ec4899"];

export default function BrainPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [brainOnline, setBrainOnline] = useState(false);
  const [currentMode, setCurrentMode] = useState("creative");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [showNewCollection, setShowNewCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [filterCollection, setFilterCollection] = useState<string | null>(null);
  const [contextMenuSession, setContextMenuSession] = useState<string | null>(null);
  const [brainMemory, setBrainMemory] = useState<Record<string, any> | null>(null);

  // Load sessions and check brain health on mount
  useEffect(() => {
    getBrainHealth()
      .then((d) => setBrainOnline(d.connected))
      .catch(() => setBrainOnline(false));

    // Load sessions from localStorage first, then try backend
    try {
      const savedSessions = localStorage.getItem("brain_sessions");
      if (savedSessions) setSessions(JSON.parse(savedSessions));
    } catch {}

    getBrainSessions()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setSessions(data);
        }
      })
      .catch(() => {});

    // Load collections from localStorage
    try {
      const saved = localStorage.getItem("brain_collections");
      if (saved) setCollections(JSON.parse(saved));
    } catch {}

    // Fetch brain memory
    fetch("http://localhost:8000/api/v1/brain/memory")
      .then((r) => r.json())
      .then((data) => setBrainMemory(data))
      .catch(() => setBrainMemory(null));
  }, []);

  // Persist sessions to localStorage when they change
  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem("brain_sessions", JSON.stringify(sessions));
    }
  }, [sessions]);

  // Save collections to localStorage when they change
  useEffect(() => {
    localStorage.setItem("brain_collections", JSON.stringify(collections));
  }, [collections]);

  function createCollection() {
    if (!newCollectionName.trim()) return;
    const newCol: Collection = {
      id: crypto.randomUUID(),
      name: newCollectionName.trim(),
      color: COLLECTION_COLORS[collections.length % COLLECTION_COLORS.length],
      conversationIds: [],
    };
    setCollections((prev) => [...prev, newCol]);
    setNewCollectionName("");
    setShowNewCollection(false);
  }

  function addToCollection(sessionId: string, collectionId: string) {
    setCollections((prev) =>
      prev.map((c) =>
        c.id === collectionId && !c.conversationIds.includes(sessionId)
          ? { ...c, conversationIds: [...c.conversationIds, sessionId] }
          : c
      )
    );
    setContextMenuSession(null);
  }

  function startNewChat() {
    setSessionId(null);
    setMessages([]);
    // Show welcome message for current mode
    const welcome = WELCOME_MESSAGES[currentMode];
    if (welcome) {
      setMessages([{ role: "brain", content: welcome, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }]);
    }
  }

  // When mode changes, show welcome if no messages yet
  useEffect(() => {
    if (messages.length === 0) {
      const welcome = WELCOME_MESSAGES[currentMode];
      if (welcome) {
        setMessages([{ role: "brain", content: welcome, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }]);
      }
    }
  }, [currentMode]);

  function loadSession(session: Session) {
    setSessionId(session.id);
    // Load messages from localStorage
    try {
      const saved = localStorage.getItem(`brain_messages_${session.id}`);
      if (saved) {
        setMessages(JSON.parse(saved));
        return;
      }
    } catch {}
    if (session.messages && Array.isArray(session.messages)) {
      setMessages(session.messages);
    } else {
      setMessages([]);
    }
  }

  // Persist messages to localStorage when they change
  useEffect(() => {
    if (sessionId && messages.length > 1) {
      localStorage.setItem(`brain_messages_${sessionId}`, JSON.stringify(messages));
      // Also update the session in the sessions list with message count
      setSessions((prev) =>
        prev.map((s) => s.id === sessionId ? { ...s, messages } : s)
      );
    }
  }, [messages, sessionId]);

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
      const resp = await fetch(`${API_BASE}/api/v1/brain/llm/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [...messages, userMsg].map((m) => ({
            role: m.role === "brain" ? "assistant" : m.role,
            content: m.content,
          })),
          mode: currentMode,
        }),
      });
      const data = await resp.json();

      // Store session for history (simple client-side tracking)
      if (!sessionId) {
        const newId = crypto.randomUUID();
        setSessionId(newId);
        const newSession: Session = {
          id: newId,
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
            <span className="text-xs font-medium text-white">Ollama (llama3.2)</span>
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

          {/* Collections Section */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-[10px] font-medium text-gray-600 uppercase">Collections</h4>
              <button
                onClick={() => setShowNewCollection(true)}
                className="text-[10px] text-purple-400 hover:text-purple-300 flex items-center gap-0.5"
              >
                <FolderPlus className="h-3 w-3" /> New
              </button>
            </div>
            {showNewCollection && (
              <div className="flex items-center gap-1 mb-2">
                <input
                  value={newCollectionName}
                  onChange={(e) => setNewCollectionName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") createCollection(); }}
                  placeholder="Collection name..."
                  className="flex-1 rounded border border-white/[0.08] bg-white/[0.03] px-2 py-1 text-xs text-gray-300 outline-none"
                  autoFocus
                />
                <button onClick={createCollection} className="text-xs text-purple-400 hover:text-purple-300">Add</button>
              </div>
            )}
            {collections.length > 0 && (
              <div className="space-y-1 mb-2">
                {collections.map((col) => (
                  <button
                    key={col.id}
                    onClick={() => setFilterCollection(filterCollection === col.id ? null : col.id)}
                    className={`w-full flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors ${
                      filterCollection === col.id ? "bg-purple-600/20 border border-purple-500/30" : "hover:bg-white/[0.03]"
                    }`}
                  >
                    <Tag className="h-3 w-3" style={{ color: col.color }} />
                    <span className="text-gray-300">{col.name}</span>
                    <span className="ml-auto text-[10px] text-gray-600">{col.conversationIds.length}</span>
                  </button>
                ))}
              </div>
            )}
            {filterCollection && (
              <button onClick={() => setFilterCollection(null)} className="text-[10px] text-gray-500 hover:text-gray-300 mb-2 flex items-center gap-1">
                <Filter className="h-3 w-3" /> Clear filter
              </button>
            )}
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
            {sessions
              .filter((s) => !filterCollection || collections.find((c) => c.id === filterCollection)?.conversationIds.includes(s.id))
              .map((session) => (
              <div key={session.id} className="relative">
                <button
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
                  <button
                    onClick={(e) => { e.stopPropagation(); setContextMenuSession(contextMenuSession === session.id ? null : session.id); }}
                    className="p-0.5 rounded hover:bg-white/[0.05]"
                  >
                    <MoreHorizontal className="h-3.5 w-3.5 text-gray-600" />
                  </button>
                </button>
                {contextMenuSession === session.id && collections.length > 0 && (
                  <div className="absolute right-0 top-full z-10 mt-1 rounded-lg border border-white/[0.08] bg-[#1a1a3a] p-2 shadow-xl">
                    <p className="text-[10px] text-gray-500 px-2 mb-1">Add to collection:</p>
                    {collections.map((col) => (
                      <button
                        key={col.id}
                        onClick={() => addToCollection(session.id, col.id)}
                        className="w-full flex items-center gap-2 rounded px-2 py-1 text-xs text-gray-300 hover:bg-white/[0.05]"
                      >
                        <Tag className="h-3 w-3" style={{ color: col.color }} />
                        {col.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
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
                  <p className="text-sm text-gray-500">Select a mode above to get started</p>
                  <p className="text-xs text-gray-600 mt-1">
                    {brainOnline ? "🟢 Ollama connected" : "🔴 Brain offline — start Ollama"}
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
              {brainOnline ? "🟢 Connected to Ollama (llama3.2)" : "🔴 Brain offline — start Ollama"}
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
              {brainMemory ? (
                <>
                  {brainMemory.favorite_models && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Zap className="h-3.5 w-3.5 mt-0.5 text-green-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Preferred models</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_models) ? brainMemory.favorite_models.join(", ") : brainMemory.favorite_models}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_camera_moves && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Film className="h-3.5 w-3.5 mt-0.5 text-blue-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Favorite camera</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_camera_moves) ? brainMemory.favorite_camera_moves.join(", ") : brainMemory.favorite_camera_moves}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_lighting && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Sparkles className="h-3.5 w-3.5 mt-0.5 text-amber-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Lighting style</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_lighting) ? brainMemory.favorite_lighting.join(", ") : brainMemory.favorite_lighting}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_prompts && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Heart className="h-3.5 w-3.5 mt-0.5 text-pink-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Favorite prompts</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_prompts) ? brainMemory.favorite_prompts.slice(0, 3).join(", ") : brainMemory.favorite_prompts}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_workflows && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Brain className="h-3.5 w-3.5 mt-0.5 text-purple-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Workflows</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_workflows) ? brainMemory.favorite_workflows.join(", ") : brainMemory.favorite_workflows}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_editing_style && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Wand2 className="h-3.5 w-3.5 mt-0.5 text-cyan-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Editing style</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_editing_style) ? brainMemory.favorite_editing_style.join(", ") : brainMemory.favorite_editing_style}</p>
                      </div>
                    </div>
                  )}
                </>
              ) : (
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
              )}
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
