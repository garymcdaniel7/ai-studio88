"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Brain, Sparkles, Plus, Settings } from "lucide-react";
import { getBrainHealth } from "@/lib/api";

// Domain modules (Story 136.a extraction)
import { BRAIN_MODES, WELCOME_MESSAGES } from "./constants";
import { useBrainChat, useBrainMemory, useBrainSessions, useCollections } from "./hooks";
import {
  ChatThread,
  Composer,
  QuickActions,
  ConversationList,
  ContextSidebar,
  MemoryModal,
  SuggestionsModal,
  ShareModal,
} from "./components";

export default function BrainPage() {
  // --- Health polling ---
  const [brainOnline, setBrainOnline] = useState(false);
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

  // --- Mode ---
  const [currentMode, setCurrentMode] = useState("creative");

  // --- Sessions ---
  const {
    sessions,
    sessionId,
    createSession,
    loadSession,
    persistMessages,
    startNewChat,
  } = useBrainSessions();

  // --- Collections ---
  const {
    collections,
    filterCollection,
    setFilterCollection,
    createCollection,
    addToCollection,
  } = useCollections();

  // --- Memory ---
  const { brainMemory } = useBrainMemory();

  // --- Chat ---
  const { messages, loading, setMessages, sendMessage } = useBrainChat({
    currentMode,
    sessionId,
    onSessionCreated: createSession,
  });

  // --- Modals ---
  const [showMemoryModal, setShowMemoryModal] = useState(false);
  const [showSuggestionsModal, setShowSuggestionsModal] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);

  // --- Persist messages (debounced) ---
  const persistTimerRef = useRef<NodeJS.Timeout | null>(null);
  useEffect(() => {
    if (!sessionId || messages.length <= 1) return;
    if (persistTimerRef.current) clearTimeout(persistTimerRef.current);
    persistTimerRef.current = setTimeout(() => {
      persistMessages(sessionId, messages, currentMode);
    }, 3000);
    return () => {
      if (persistTimerRef.current) clearTimeout(persistTimerRef.current);
    };
  }, [messages, sessionId, currentMode, persistMessages]);

  // --- Mode change → welcome message ---
  useEffect(() => {
    const welcome = WELCOME_MESSAGES[currentMode];
    if (welcome) {
      setMessages([{
        role: "brain",
        content: welcome,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      }]);
    }
  }, [currentMode, setMessages]);

  // --- Handlers ---
  const handleLoadSession = useCallback((session: { id: string; title: string; created_at: string; messages?: Array<{ role: string; content: string; time: string; image?: string }> }) => {
    const msgs = loadSession(session);
    if (msgs.length > 0) {
      setMessages(msgs);
    }
  }, [loadSession, setMessages]);

  const handleNewChat = useCallback(() => {
    startNewChat();
    const welcome = WELCOME_MESSAGES[currentMode];
    if (welcome) {
      setMessages([{
        role: "brain",
        content: welcome,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      }]);
    }
  }, [startNewChat, currentMode, setMessages]);

  const handleSuggestionSelect = useCallback((prompt: string) => {
    sendMessage(prompt);
  }, [sendMessage]);

  return (
    <div className="space-y-4 -m-6">
      {/* Header */}
      <div className="flex items-center justify-between px-6 pt-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-content-primary">
            AI Brain <Sparkles className="h-5 w-5 text-status-info" />
          </h1>
          <p className="text-sm text-content-muted">
            Your creative co-pilot for ideas, strategy, and production.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-lg border border-border-default px-3 py-1.5">
            <span className="text-xs text-content-tertiary">Engine:</span>
            <span className="text-xs font-medium text-content-primary">Hermes</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${brainOnline ? "bg-green-500" : "bg-red-500"}`} />
            <span className={`text-xs ${brainOnline ? "text-status-success" : "text-status-error"}`}>
              {brainOnline ? "Online" : "Offline"}
            </span>
          </div>
          <button
            onClick={handleNewChat}
            className="flex items-center gap-2 rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700"
          >
            <Plus className="h-3.5 w-3.5" /> New Chat
          </button>
          <button aria-label="Brain settings" className="rounded-lg border border-border-default p-1.5 text-content-tertiary hover:bg-surface-hover">
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Mode Pills */}
      <div className="flex items-center gap-1.5 px-6 py-2">
        {BRAIN_MODES.map((mode) => (
          <button
            key={mode.key}
            onClick={() => setCurrentMode(mode.key)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
              currentMode === mode.key
                ? "bg-interactive-muted text-purple-300 border border-purple-500/40"
                : "text-content-muted hover:text-content-secondary hover:bg-surface-hover border border-transparent"
            }`}
          >
            <mode.icon className="h-3 w-3" />
            {mode.name}
          </button>
        ))}
      </div>

      {/* Three-panel layout */}
      <div className="grid grid-cols-[280px_1fr_300px] gap-0 border-t border-border-subtle" style={{ height: "calc(100vh - 140px)" }}>
        {/* Left: Conversations */}
        <ConversationList
          sessions={sessions}
          collections={collections}
          sessionId={sessionId}
          filterCollection={filterCollection}
          onSelectSession={handleLoadSession}
          onCreateCollection={createCollection}
          onAddToCollection={addToCollection}
          onFilterChange={setFilterCollection}
        />

        {/* Center: Chat */}
        <div className="flex flex-col">
          {/* Chat header */}
          <div className="flex items-center justify-between border-b border-border-subtle px-6 py-3">
            <h3 className="text-sm font-semibold text-content-primary">
              {sessionId ? sessions.find((s) => s.id === sessionId)?.title || "Chat" : "New Conversation"}
            </h3>
            <button onClick={() => setShowShareModal(true)} className="text-xs text-content-tertiary hover:text-content-secondary">Share</button>
          </div>

          {/* Messages */}
          <ChatThread
            messages={messages}
            loading={loading}
            currentMode={currentMode}
            brainOnline={brainOnline}
          />

          {/* Quick Actions */}
          <QuickActions onSelect={handleSuggestionSelect} />

          {/* Composer */}
          <Composer
            onSend={sendMessage}
            loading={loading}
            brainOnline={brainOnline}
          />
        </div>

        {/* Right: Context */}
        <ContextSidebar
          brainMemory={brainMemory}
          onShowMemory={() => setShowMemoryModal(true)}
          onShowSuggestions={() => setShowSuggestionsModal(true)}
        />
      </div>

      {/* Modals */}
      {showMemoryModal && (
        <MemoryModal brainMemory={brainMemory} onClose={() => setShowMemoryModal(false)} />
      )}
      {showSuggestionsModal && (
        <SuggestionsModal
          onSelect={handleSuggestionSelect}
          onClose={() => setShowSuggestionsModal(false)}
        />
      )}
      {showShareModal && (
        <ShareModal
          messages={messages}
          sessionTitle={sessions.find((s) => s.id === sessionId)?.title || "Conversation"}
          onClose={() => setShowShareModal(false)}
        />
      )}
    </div>
  );
}
