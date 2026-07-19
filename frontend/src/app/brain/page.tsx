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
  FolderPlus,
  Tag,
  Filter,
} from "lucide-react";
import { getBrainSessions, getBrainHealth } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

const WELCOME_MESSAGES: Record<string, string> = {
  creative: "Hey! 👋 Welcome to AI Studio. I'm your Creative Director AI. I can help you brainstorm ideas, explore concepts, develop campaigns, and push creative boundaries. What are you working on today?",
  prompt_engineer: "Let's build the perfect prompt. 🎯 Tell me what you want to create — describe the subject, mood, or concept — and I'll guide you toward a production-ready prompt optimized for Flux, SDXL, or WAN 2.1. Start simple, I'll refine it with you.",
  script_writer: "I'm your Script Writer. ✍️ I'm skilled in all genres — screenplays, songs, reels, commercials, TikTok hooks, YouTube scripts, R&B lyrics, and cinematic narratives. I'll ask probing questions to develop award-winning content. What are we creating together?",
  story_assistant: "I'm your Story Assistant. 📖 I help develop narratives for commercials, series, social content, and films. Whether it's a 15-second reel or a 10-episode series, let's build a compelling story. What's the concept?",
  production_advisor: "Production Advisor here. 📊 I help optimize your workflows, estimate GPU costs, plan pipelines, and schedule batch renders. What production challenge are you facing?",
  image_analyzer: "Image Analyzer ready. 🖼️ Describe an image or paste a reference, and I'll break down the composition, lighting, color palette, and suggest how to recreate or improve it with AI generation.",
};

const modes = [
  { name: "Creative Chat", desc: "General conversations", icon: MessageSquare, key: "creative" },
  { name: "Prompt Engineer", desc: "Improve your prompts", icon: Wand2, key: "prompt_engineer" },
  { name: "Script Writer", desc: "Scripts, songs & screenplays", icon: BookOpen, key: "script_writer" },
  { name: "Story Assistant", desc: "Develop narratives", icon: Film, key: "story_assistant" },
  { name: "Production Advisor", desc: "Plan & optimize workflows", icon: Search, key: "production_advisor" },
  { name: "Image Analyzer", desc: "Analyze images & assets", icon: ImageIcon, key: "image_analyzer" },
];

interface ChatMessage {
  role: string;
  content: string;
  time: string;
  image?: string;  // Base64 data URL for attached images
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
  const [brainMemory, setBrainMemory] = useState<Record<string, unknown> | null>(null);
  const [showMemoryModal, setShowMemoryModal] = useState(false);
  const [showSuggestionsModal, setShowSuggestionsModal] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  const [attachedImagePreview, setAttachedImagePreview] = useState<string | null>(null);

  // Check brain health on mount and every 10s
  useEffect(() => {
    const checkHealth = () => {
      getBrainHealth()
        .then((d) => setBrainOnline(Boolean(d.connected)))
        .catch(() => setBrainOnline(false));
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  // Load sessions from localStorage first, then try backend
  useEffect(() => {
    try {
      const savedSessions = localStorage.getItem("brain_sessions");
      if (savedSessions) setSessions(JSON.parse(savedSessions as string));
    } catch {}

    getBrainSessions()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setSessions(data as unknown as Session[]);
        }
      })
      .catch(() => {});
  }, []);

  // Load collections from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("brain_collections");
      if (saved) setCollections(JSON.parse(saved as string));
    } catch {}
  }, []);

  // Fetch brain memory
  useEffect(() => {
    fetch(`${API_BASE}/api/v1/brain/memory`)
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

  // Save collections to localStorage AND backend when they change
  useEffect(() => {
    localStorage.setItem("brain_collections", JSON.stringify(collections));
  }, [collections]);

  // Persist messages to backend when conversation updates (debounced)
  useEffect(() => {
    if (!sessionId || messages.length <= 1) return;
    const timer = setTimeout(() => {
      fetch(`${API_BASE}/api/v1/brain/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: sessionId,
          title: messages[1]?.content?.slice(0, 50) || "Chat",
          mode: currentMode,
          messages: messages.map((m) => ({ role: m.role, content: m.content, time: m.time })),
        }),
      }).catch(() => {});
    }, 3000); // Save 3s after last message
    return () => clearTimeout(timer);
  }, [messages, sessionId, currentMode]);

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
    // Persist to backend
    fetch(`${API_BASE}/api/v1/brain/collections`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newCol.name, color: newCol.color }),
    }).catch(() => {});
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

  // When mode changes, always show the new mode's welcome message
  useEffect(() => {
    const welcome = WELCOME_MESSAGES[currentMode];
    if (welcome) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMessages([{ role: "brain", content: welcome, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }]);
    }
    // Clear session context when switching modes
    setSessionId(null);
  }, [currentMode]); // eslint-disable-line react-hooks/exhaustive-deps

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
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSessions((prev) =>
        prev.map((s) => s.id === sessionId ? { ...s, messages } : s)
      );
    }
  }, [messages, sessionId]);

  async function sendMessage() {
    if (!input.trim() || loading) return;
    // Include image in the user message if attached
    const attachedImage = (window as unknown as Record<string, unknown>).__brain_attached_image as string | undefined;
    const attachedPreview = attachedImagePreview;

    const userMsg: ChatMessage = {
      role: "user",
      content: input.replace(/\[Image:.*?\]/g, "").trim() || "Analyze this image",
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    // Store image data URL in the message for rendering
    if (attachedPreview) {
      userMsg.image = attachedPreview;
    }
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      if (attachedImage) {
        // Clear after use
        delete (window as unknown as Record<string, unknown>).__brain_attached_image;
        delete (window as unknown as Record<string, unknown>).__brain_attached_filename;
        setAttachedImagePreview(null);
      }

      const resp = await fetch(`${API_BASE}/aios/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: [...messages, userMsg].slice(-1)[0].content,
          mode: currentMode,
          session_id: sessionId || undefined,
          images: attachedImage ? [attachedImage] : undefined,
        }),
      });
      const data = await resp.json();

      // Use AIOS session ID if returned
      if (!sessionId && data.session_id) {
        setSessionId(data.session_id);
        const newSession: Session = {
          id: data.session_id,
          title: input.slice(0, 40) || "New Chat",
          created_at: new Date().toISOString(),
        };
        setSessions((prev) => [newSession, ...prev]);
      } else if (!sessionId) {
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
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + (data.provider ? ` · ${data.provider}` : ""),
      };
      setMessages((prev) => [...prev, brainMsg]);

      // Show pending approvals as inline action cards with buttons
      const pendingApprovals = data.governance?.pending_approval || [];
      const autoApproved = data.governance?.auto_approved || [];

      if (pendingApprovals.length > 0) {
        for (const approval of pendingApprovals as Array<{tool: string; reason: string; approval_id: string; estimated_cost_usd?: number}>) {
          const approvalMsg: ChatMessage = {
            role: "brain",
            content: `__APPROVAL__${JSON.stringify(approval)}`,
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          };
          setMessages((prev) => [...prev, approvalMsg]);
        }
      }

      if (autoApproved.length > 0) {
        for (const action of autoApproved as Array<{tool: string; reasoning: string; parameters?: Record<string, unknown>}>) {
          // For image generation, trigger it and show result
          if (action.tool === "generate_image") {
            const genMsg: ChatMessage = {
              role: "brain",
              content: `✅ Generating image... (auto-approved)`,
              time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            };
            setMessages((prev) => [...prev, genMsg]);

            // Actually trigger generation and show result
            try {
              const genResp = await fetch(`${API_BASE}/api/v1/generate/image`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(action.parameters || { prompt: input }),
              });
              if (genResp.ok) {
                const genData = await genResp.json();
                if (genData.image_base64) {
                  const resultMsg: ChatMessage = {
                    role: "brain",
                    content: `Generated in ${genData.generation_time || "?"}s — ${genData.model || ""}`,
                    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                    image: `data:image/png;base64,${genData.image_base64}`,
                  };
                  setMessages((prev) => [...prev, resultMsg]);
                }
              }
            } catch {}
          } else {
            const autoMsg: ChatMessage = {
              role: "brain",
              content: `✅ ${action.tool}: ${action.reasoning}`,
              time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            };
            setMessages((prev) => [...prev, autoMsg]);
          }
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "brain",
          content: "Brain is reconnecting... The Ollama service may need a moment to start. Check Admin → Services if this persists.",
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
            <span className="text-xs font-medium text-white">Ollama (llama3.1:8b)</span>
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
          <button aria-label="Brain settings" className="rounded-lg border border-white/[0.08] p-1.5 text-gray-400 hover:bg-white/[0.04]">
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Mode Pills — compact horizontal selector */}
      <div className="flex items-center gap-1.5 px-6 py-2">
        {modes.map((mode) => (
          <button
            key={mode.key}
            onClick={() => setCurrentMode(mode.key)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
              currentMode === mode.key
                ? "bg-purple-600/20 text-purple-300 border border-purple-500/40"
                : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.04] border border-transparent"
            }`}
          >
            <mode.icon className="h-3 w-3" />
            {mode.name}
          </button>
        ))}
      </div>

      {/* Three-panel layout */}
      <div className="grid grid-cols-[280px_1fr_300px] gap-0 border-t border-white/[0.06]" style={{ height: "calc(100vh - 140px)" }}>
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
                <div
                  onClick={() => loadSession(session)}
                  role="button"
                  tabIndex={0}
                  className={`w-full flex items-center justify-between rounded-lg px-3 py-2.5 text-left transition-colors cursor-pointer ${
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
                </div>
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
            <button onClick={() => setShowShareModal(true)} className="text-xs text-gray-400 hover:text-gray-200">Share</button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {messages.length === 0 && (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <Brain className="h-12 w-12 text-purple-400/30 mx-auto mb-3" />
                  <p className="text-sm text-gray-500">Select a mode above to get started</p>
                  <p className="text-xs text-gray-600 mt-1">
                    {brainOnline ? "🟢 Ollama connected" : "🔴 Reconnecting..."}
                  </p>
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 group/msg ${msg.role === "user" ? "justify-end" : ""}`}>
                {msg.role !== "user" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-600/20">
                    <Brain className="h-4 w-4 text-purple-400" />
                  </div>
                )}
                <div className={`max-w-[600px] rounded-2xl px-4 py-3 relative ${
                  msg.role === "user"
                    ? "bg-purple-600/20 border border-purple-500/20"
                    : "bg-white/[0.03] border border-white/[0.06]"
                }`}>
                  {/* Show image if message has one */}
                  {msg.image && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={msg.image} alt="Attached" className="rounded-lg max-w-[300px] max-h-[200px] object-cover mb-2" />
                  )}
                  {/* Render approval cards with buttons */}
                  {msg.content.startsWith("__APPROVAL__") ? (
                    <ApprovalCard data={JSON.parse(msg.content.replace("__APPROVAL__", ""))} onAction={() => {}} />
                  ) : (
                    <p className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                  )}
                  <p className="mt-1 text-[10px] text-gray-500">{msg.time}</p>
                  {/* Use as Prompt — shows on hover for brain messages */}
                  {msg.role !== "user" && i > 0 && (
                    <div className="absolute -bottom-3 right-2 opacity-0 group-hover/msg:opacity-100 transition-opacity">
                      <UseAsPromptButton content={msg.content} />
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-600/20">
                  <Brain className="h-4 w-4 text-purple-400 animate-pulse" />
                </div>
                <div className="rounded-2xl bg-white/[0.03] border border-purple-500/20 px-4 py-3 shadow-lg shadow-purple-500/5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-purple-300">Thinking</span>
                    <span className="flex gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "300ms" }} />
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-500 mt-1">
                    {currentMode === "creative" ? "Crafting a creative response..." :
                     currentMode === "prompt_engineer" ? "Optimizing your prompt..." :
                     currentMode === "story_assistant" ? "Developing narrative..." :
                     currentMode === "production_advisor" ? "Analyzing your workflow..." :
                     currentMode === "image_analyzer" ? "Analyzing visual content..." :
                     "Processing your request..."}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Quick Actions */}
          <div className="flex gap-2 px-6 py-2">
            {[
              { label: "Create Storyboard", prompt: "Help me create a storyboard for a short video. Ask me about the concept, target audience, and mood." },
              { label: "Generate Prompt", prompt: "Help me write an optimized image generation prompt. Ask me what I want to create." },
              { label: "Brainstorm Ideas", prompt: "Let's brainstorm creative content ideas together. What's the project or campaign about?" },
              { label: "Suggest Music", prompt: "Suggest music tracks or instrumentals for my video project. What's the mood and genre?" },
            ].map((action) => (
              <button
                key={action.label}
                onClick={() => { setInput(action.prompt); }}
                className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-xs text-gray-400 hover:bg-white/[0.05] hover:text-gray-200"
              >
                {action.label}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="border-t border-white/[0.06] p-4">
            {/* Attached Image Preview */}
            {attachedImagePreview && (
              <div className="mb-2 flex items-center gap-2 rounded-lg border border-purple-500/20 bg-purple-500/5 px-3 py-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={attachedImagePreview} alt="Attached" className="h-10 w-10 rounded object-cover" />
                <span className="text-xs text-purple-300 flex-1">Image attached — will be analyzed on send</span>
                <button onClick={() => { setAttachedImagePreview(null); delete (window as unknown as Record<string, unknown>).__brain_attached_image; }} className="text-xs text-gray-500 hover:text-red-400">&times;</button>
              </div>
            )}
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
                <label className="p-1.5 text-gray-500 hover:text-gray-300 cursor-pointer" title="Attach image" aria-label="Attach image">
                  <ImageIcon className="h-4 w-4" />
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        const reader = new FileReader();
                        reader.onload = (ev) => {
                          const dataUrl = ev.target?.result as string;
                          const base64 = dataUrl?.split(",")[1] || "";
                          setAttachedImagePreview(dataUrl);
                          // Store for sending with next message
                          (window as unknown as Record<string, unknown>).__brain_attached_image = base64;
                          (window as unknown as Record<string, unknown>).__brain_attached_filename = file.name;
                        };
                        reader.readAsDataURL(file);
                      }
                      e.target.value = "";
                    }}
                  />
                </label>
                <button className="p-1.5 text-gray-500 hover:text-gray-300" title="Code block" aria-label="Insert code block" onClick={() => setInput((prev) => prev + "\n```\n\n```")}><Code className="h-4 w-4" /></button>
                <button
                  className="p-1.5 text-gray-500 hover:text-gray-300"
                  title="Voice to text"
                  aria-label="Voice to text"
                  onClick={() => {
                    if (!("webkitSpeechRecognition" in window) && !("SpeechRecognition" in window)) {
                      alert("Speech recognition not supported in this browser. Use Chrome.");
                      return;
                    }
                    const SpeechRecognition = (window as unknown as Record<string, unknown>).SpeechRecognition || (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
                    const recognition = new (SpeechRecognition as new () => { lang: string; continuous: boolean; onresult: (e: { results: { transcript: string }[][] }) => void; onerror: () => void; start: () => void })();
                    recognition.lang = "en-US";
                    recognition.continuous = false;
                    recognition.onresult = (e) => {
                      const transcript = e.results[0][0].transcript;
                      setInput((prev) => prev + (prev ? " " : "") + transcript);
                    };
                    recognition.onerror = () => {};
                    recognition.start();
                  }}
                >
                  <Mic className="h-4 w-4" />
                </button>
                <button
                  onClick={sendMessage}
                  disabled={loading || !input.trim()}
                  aria-label="Send message"
                  className="ml-2 rounded-lg bg-purple-600 p-2 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
            </div>
            <p className="mt-1 text-center text-[10px] text-gray-600">
              {brainOnline ? "🟢 Connected to Ollama (llama3.1:8b)" : "🔴 Brain offline — check Admin → Services"}
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
            <p className="text-sm font-medium text-white">No active project</p>
            <p className="text-xs text-gray-500">Select a project from Production</p>
          </div>

          {/* Brain Memory */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-semibold text-white">Brain Memory</h4>
              <button onClick={() => setShowMemoryModal(true)} className="text-[10px] text-purple-400 hover:text-purple-300">View all</button>
            </div>
            <div className="space-y-2">
              {brainMemory ? (
                <>
                  {brainMemory.favorite_models && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Zap className="h-3.5 w-3.5 mt-0.5 text-green-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Preferred models</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_models) ? brainMemory.favorite_models.join(", ") : String(brainMemory.favorite_models)}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_camera_moves && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Film className="h-3.5 w-3.5 mt-0.5 text-blue-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Favorite camera</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_camera_moves) ? brainMemory.favorite_camera_moves.join(", ") : String(brainMemory.favorite_camera_moves)}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_lighting && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Sparkles className="h-3.5 w-3.5 mt-0.5 text-amber-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Lighting style</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_lighting) ? brainMemory.favorite_lighting.join(", ") : String(brainMemory.favorite_lighting)}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_prompts && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Heart className="h-3.5 w-3.5 mt-0.5 text-pink-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Favorite prompts</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_prompts) ? brainMemory.favorite_prompts.slice(0, 3).join(", ") : String(brainMemory.favorite_prompts)}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_workflows && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Brain className="h-3.5 w-3.5 mt-0.5 text-purple-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Workflows</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_workflows) ? brainMemory.favorite_workflows.join(", ") : String(brainMemory.favorite_workflows)}</p>
                      </div>
                    </div>
                  )}
                  {brainMemory.favorite_editing_style && (
                    <div className="flex items-start gap-2 rounded-lg bg-white/[0.02] p-2">
                      <Wand2 className="h-3.5 w-3.5 mt-0.5 text-cyan-400" />
                      <div>
                        <p className="text-xs font-medium text-gray-200">Editing style</p>
                        <p className="text-[10px] text-gray-500">{Array.isArray(brainMemory.favorite_editing_style) ? brainMemory.favorite_editing_style.join(", ") : String(brainMemory.favorite_editing_style)}</p>
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
              <button onClick={() => setShowSuggestionsModal(true)} className="text-[10px] text-purple-400 hover:text-purple-300">View all</button>
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

      {/* Memory Modal */}
      {showMemoryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowMemoryModal(false)}>
          <div className="w-full max-w-lg rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white">Brain Memory</h2>
              <button onClick={() => setShowMemoryModal(false)} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">&times;</button>
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
      )}

      {/* Suggestions Modal */}
      {showSuggestionsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowSuggestionsModal(false)}>
          <div className="w-full max-w-lg rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white">AI Suggestions</h2>
              <button onClick={() => setShowSuggestionsModal(false)} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">&times;</button>
            </div>
            <p className="text-xs text-gray-500 mb-4">Contextual suggestions based on your current project and workflow.</p>
            <div className="space-y-2">
              {[
                { title: "Continue this creative direction", desc: "Build on what we discussed — refine the concept further" },
                { title: "Generate a prompt from our chat", desc: "Turn our conversation into a production-ready image/video prompt" },
                { title: "Create a storyboard outline", desc: "Map out the visual sequence for this concept" },
                { title: "Suggest music/audio direction", desc: "Recommend genres, mood, and tempo for this project" },
                { title: "Write a TikTok/Reel script", desc: "Short-form hook + content + CTA based on our ideas" },
                { title: "Train a LoRA for this style", desc: "Capture the visual direction as a reusable AI model" },
              ].map((s) => (
                <button key={s.title} onClick={() => { setInput(s.title); setShowSuggestionsModal(false); }} className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-left hover:bg-white/[0.04]">
                  <p className="text-sm font-medium text-gray-200">{s.title}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{s.desc}</p>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Share Modal */}
      {showShareModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowShareModal(false)}>
          <div className="w-full max-w-sm rounded-2xl border border-white/[0.08] bg-[#0f0f24] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white">Share Conversation</h2>
              <button onClick={() => setShowShareModal(false)} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/[0.08]">&times;</button>
            </div>
            <div className="space-y-3">
              <button
                onClick={() => {
                  const text = messages.map((m) => `${m.role === "user" ? "You" : "Brain"}: ${m.content}`).join("\n\n");
                  navigator.clipboard.writeText(text);
                  setShowShareModal(false);
                }}
                className="w-full flex items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 hover:bg-white/[0.04]"
              >
                <span className="text-lg">📋</span>
                <div className="text-left">
                  <p className="text-sm font-medium text-white">Copy to Clipboard</p>
                  <p className="text-[10px] text-gray-500">Copy full conversation text</p>
                </div>
              </button>
              <button
                onClick={() => {
                  const text = messages.map((m) => `${m.role === "user" ? "You" : "Brain"}: ${m.content}`).join("\n\n");
                  const subject = `AI Studio Brain Chat — ${sessions.find(s => s.id === sessionId)?.title || "Conversation"}`;
                  window.open(`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text)}`);
                  setShowShareModal(false);
                }}
                className="w-full flex items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 hover:bg-white/[0.04]"
              >
                <span className="text-lg">📧</span>
                <div className="text-left">
                  <p className="text-sm font-medium text-white">Share via Email</p>
                  <p className="text-[10px] text-gray-500">Open email client with conversation</p>
                </div>
              </button>
              <button
                onClick={() => {
                  const text = messages.map((m) => `${m.role === "user" ? "You" : "Brain"}: ${m.content}`).join("\n\n");
                  window.open(`sms:&body=${encodeURIComponent(text.slice(0, 1000))}`);
                  setShowShareModal(false);
                }}
                className="w-full flex items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 hover:bg-white/[0.04]"
              >
                <span className="text-lg">💬</span>
                <div className="text-left">
                  <p className="text-sm font-medium text-white">Share via SMS / iMessage</p>
                  <p className="text-[10px] text-gray-500">Send conversation summary</p>
                </div>
              </button>
              <button
                onClick={() => {
                  const text = messages.map((m) => `${m.role === "user" ? "You" : "Brain"}: ${m.content}`).join("\n\n");
                  const blob = new Blob([text], { type: "text/plain" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `brain-chat-${new Date().toISOString().slice(0, 10)}.txt`;
                  a.click();
                  URL.revokeObjectURL(url);
                  setShowShareModal(false);
                }}
                className="w-full flex items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 hover:bg-white/[0.04]"
              >
                <span className="text-lg">📄</span>
                <div className="text-left">
                  <p className="text-sm font-medium text-white">Download as Text</p>
                  <p className="text-[10px] text-gray-500">Save .txt file to your device</p>
                </div>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Use as Prompt — Button + Popup to inject brain output into Create page
// ---------------------------------------------------------------------------

function UseAsPromptButton({ content }: { content: string }) {
  const [showPopup, setShowPopup] = useState(false);

  const generationTypes = [
    { key: "image", label: "Image", icon: "🖼️", tab: "image" },
    { key: "video", label: "Video", icon: "🎬", tab: "video" },
    { key: "voice", label: "Voice", icon: "🎙️", tab: "audio" },
    { key: "music", label: "Music", icon: "🎵", tab: "audio" },
  ];

  function handleSelect(tab: string) {
    // Store prompt in sessionStorage and navigate to Create page
    sessionStorage.setItem("injected_prompt", content);
    sessionStorage.setItem("injected_tab", tab);
    window.location.href = `/create?tab=${tab}&prompt=${encodeURIComponent(content.slice(0, 500))}`;
  }

  return (
    <div className="relative">
      <button
        onClick={() => setShowPopup(!showPopup)}
        className="flex items-center gap-1 rounded-full bg-purple-600/80 px-2.5 py-1 text-[10px] font-medium text-white shadow-lg hover:bg-purple-600 transition-colors"
      >
        <Sparkles className="h-3 w-3" />
        Use as Prompt
      </button>

      {showPopup && (
        <div className="absolute bottom-8 right-0 z-50 w-48 rounded-xl border border-white/[0.1] bg-[#12122a] p-2 shadow-2xl">
          <p className="px-2 py-1 text-[10px] font-semibold text-gray-400 uppercase">Generate as...</p>
          {generationTypes.map((type) => (
            <button
              key={type.key}
              onClick={() => handleSelect(type.tab)}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-gray-300 hover:bg-purple-600/20 hover:text-white transition-colors"
            >
              <span>{type.icon}</span>
              <span>{type.label}</span>
              <ArrowRight className="h-3 w-3 ml-auto text-gray-600" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Approval Card — inline approve/reject buttons in chat
// ---------------------------------------------------------------------------

function ApprovalCard({ data, onAction }: { data: { tool: string; reason: string; approval_id: string; estimated_cost_usd?: number }; onAction: () => void }) {
  const [status, setStatus] = useState<"pending" | "approved" | "rejected">("pending");
  const [executing, setExecuting] = useState(false);

  const API_BASE_CARD = process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app";

  async function handleApprove() {
    setExecuting(true);
    try {
      const resp = await fetch(`${API_BASE_CARD}/aios/v1/approvals/${data.approval_id}/approve`, { method: "POST" });
      if (resp.ok) {
        setStatus("approved");
        onAction();
      }
    } catch {}
    setExecuting(false);
  }

  async function handleReject() {
    try {
      await fetch(`${API_BASE_CARD}/aios/v1/approvals/${data.approval_id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Rejected from Brain chat" }),
      });
      setStatus("rejected");
      onAction();
    } catch {}
  }

  if (status === "approved") {
    return <p className="text-xs text-green-400">✅ Approved — executing {data.tool}</p>;
  }
  if (status === "rejected") {
    return <p className="text-xs text-gray-500">❌ Rejected — {data.tool} cancelled</p>;
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-amber-300">⚡ Action requires your approval:</p>
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
        <p className="text-xs font-medium text-white">{data.tool}</p>
        <p className="text-[10px] text-gray-400 mt-0.5">{data.reason}</p>
        {data.estimated_cost_usd != null && data.estimated_cost_usd > 0 && (
          <p className="text-[10px] text-amber-400 mt-0.5">Estimated cost: ${data.estimated_cost_usd.toFixed(3)}</p>
        )}
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleApprove}
          disabled={executing}
          className="rounded-lg bg-green-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
        >
          {executing ? "Executing..." : "Approve"}
        </button>
        <button
          onClick={handleReject}
          className="rounded-lg border border-white/[0.08] px-4 py-1.5 text-xs text-gray-400 hover:text-white"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
