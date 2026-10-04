"use client";

import { useState, useEffect, useCallback } from "react";
import { getBrainSessions } from "@/lib/api";
import type { Session, ChatMessage } from "../types";

function isCanonicalId(id: unknown): id is string {
  return typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id);
}

/**
 * Hook: Brain session management.
 * Handles session CRUD, localStorage cache, and backend persistence.
 */
export function useBrainSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load sessions from localStorage first, then try backend
  useEffect(() => {
    try {
      const saved = localStorage.getItem("brain_sessions");
      if (saved) {
        const local = JSON.parse(saved);
        if (Array.isArray(local)) setSessions(local.filter((s) => isCanonicalId(s?.id)));
      }
    } catch {
      // Ignore parse errors
    }

    getBrainSessions()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setSessions(data.filter((s) => isCanonicalId(s.id)).map((s) => ({
            id: String(s.id),
            title: String(s.title || "New Chat"),
            created_at: String(s.created_at || new Date().toISOString()),
          })) as Session[]);
        }
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Could not load conversations from the server.");
      })
      .finally(() => setIsLoading(false));
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

    // Canonical chat persists messages transactionally; do not replay them via
    // an unauthenticated legacy POST (which also created duplicate sessions).
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
    isLoading,
    error,
  };
}
