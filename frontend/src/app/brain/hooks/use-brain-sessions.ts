"use client";

import { useState, useEffect, useCallback } from "react";
import { getBrainSessions } from "@/lib/api";
import type { Session, ChatMessage } from "../types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Hook: Brain session management.
 * Handles session CRUD, localStorage cache, and backend persistence.
 */
export function useBrainSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Load sessions from localStorage first, then try backend
  useEffect(() => {
    try {
      const saved = localStorage.getItem("brain_sessions");
      if (saved) setSessions(JSON.parse(saved));
    } catch {
      // Ignore parse errors
    }

    getBrainSessions()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setSessions(data as unknown as Session[]);
        }
      })
      .catch(() => {});
  }, []);

  // Persist sessions to localStorage
  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem("brain_sessions", JSON.stringify(sessions));
    }
  }, [sessions]);

  const createSession = useCallback((id: string, title: string) => {
    const newSession: Session = {
      id,
      title: title || "New Chat",
      created_at: new Date().toISOString(),
    };
    setSessions((prev) => [newSession, ...prev]);
    setSessionId(id);
  }, []);

  const loadSession = useCallback((session: Session): ChatMessage[] => {
    setSessionId(session.id);
    try {
      const saved = localStorage.getItem(`brain_messages_${session.id}`);
      if (saved) return JSON.parse(saved);
    } catch {
      // Ignore parse errors
    }
    return session.messages || [];
  }, []);

  const persistMessages = useCallback((sid: string, messages: ChatMessage[], mode: string) => {
    // Save to localStorage
    localStorage.setItem(`brain_messages_${sid}`, JSON.stringify(messages));

    // Update session in list
    setSessions((prev) =>
      prev.map((s) => (s.id === sid ? { ...s, messages } : s))
    );

    // Sync to backend (debounced at call site)
    fetch(`${API_BASE}/api/v1/brain/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: sid,
        title: messages[1]?.content?.slice(0, 50) || "Chat",
        mode,
        messages: messages.map((m) => ({ role: m.role, content: m.content, time: m.time })),
      }),
    }).catch(() => {});
  }, []);

  const startNewChat = useCallback(() => {
    setSessionId(null);
  }, []);

  return {
    sessions,
    sessionId,
    setSessionId,
    createSession,
    loadSession,
    persistMessages,
    startNewChat,
  };
}
