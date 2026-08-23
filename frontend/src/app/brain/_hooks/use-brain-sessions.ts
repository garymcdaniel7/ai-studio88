"use client";

import { useState, useEffect } from "react";
import { getBrainSessions } from "@/lib/api";

export interface ChatMessage {
  role: string;
  content: string;
  time: string;
  image?: string;
}

export interface Session {
  id: string;
  title: string;
  created_at: string;
  messages?: ChatMessage[];
}

export interface Collection {
  id: string;
  name: string;
  color: string;
  conversationIds: string[];
}

export const COLLECTION_COLORS = ["#8b5cf6", "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#ec4899"];

/**
 * Hook: Brain session and collection management.
 * Handles localStorage persistence, backend sync, and collection CRUD.
 */
export function useBrainSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load sessions from localStorage, then try backend
  useEffect(() => {
    try {
      const saved = localStorage.getItem("brain_sessions");
      if (saved) setSessions(JSON.parse(saved));
    } catch {}
    getBrainSessions()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setSessions(data as unknown as Session[]);
        }
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Could not load conversations from the server.");
      })
      .finally(() => setIsLoading(false));
  }, []);

  // Load collections from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("brain_collections");
      if (saved) setCollections(JSON.parse(saved));
    } catch {}
  }, []);

  // Persist sessions
  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem("brain_sessions", JSON.stringify(sessions));
    }
  }, [sessions]);

  // Persist collections
  useEffect(() => {
    localStorage.setItem("brain_collections", JSON.stringify(collections));
  }, [collections]);

  function createSession(title: string, id?: string): Session {
    const newSession: Session = {
      id: id || crypto.randomUUID(),
      title: title || "New Chat",
      created_at: new Date().toISOString(),
    };
    setSessions((prev) => [newSession, ...prev]);
    setSessionId(newSession.id);
    return newSession;
  }

  function createCollection(name: string): Collection | null {
    if (!name.trim()) return null;
    const newCol: Collection = {
      id: crypto.randomUUID(),
      name: name.trim(),
      color: COLLECTION_COLORS[collections.length % COLLECTION_COLORS.length],
      conversationIds: [],
    };
    setCollections((prev) => [...prev, newCol]);
    return newCol;
  }

  function addToCollection(sid: string, collectionId: string) {
    setCollections((prev) =>
      prev.map((c) =>
        c.id === collectionId && !c.conversationIds.includes(sid)
          ? { ...c, conversationIds: [...c.conversationIds, sid] }
          : c
      )
    );
  }

  function updateSessionMessages(sid: string, messages: ChatMessage[]) {
    setSessions((prev) =>
      prev.map((s) => (s.id === sid ? { ...s, messages } : s))
    );
  }

  return {
    sessions,
    collections,
    sessionId,
    setSessionId,
    createSession,
    createCollection,
    addToCollection,
    updateSessionMessages,
    isLoading,
    error,
  };
}
