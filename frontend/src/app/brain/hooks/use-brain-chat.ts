"use client";

import { useState, useCallback, useRef } from "react";
import type { ChatMessage } from "../types";
import { authFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface UseBrainChatOptions {
  currentMode: string;
  sessionId: string | null;
  onSessionCreated: (id: string, title: string) => void;
}

interface AutoApprovedAction {
  tool: string;
  reasoning: string;
  parameters?: Record<string, unknown>;
}

/**
 * Hook: Brain chat message sending and response handling.
 *
 * Handles:
 * - Sending messages to /aios/v1/chat
 * - Processing governance approvals and auto-approved actions
 * - Image generation from auto-approved actions
 * - Error handling with reconnect messaging
 */
export function useBrainChat({ currentMode, sessionId, onSessionCreated }: UseBrainChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const setInitialMessages = useCallback((msgs: ChatMessage[]) => {
    setMessages(msgs);
  }, []);

  const sendMessage = useCallback(async (
    input: string,
    attachedImage?: string | null,
    attachedPreview?: string | null,
  ) => {
    if (!input.trim() || loading) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: input.replace(/\[Image:.*?\]/g, "").trim() || "Analyze this image",
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    if (attachedPreview) {
      userMsg.image = attachedPreview;
    }

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      abortRef.current = new AbortController();

      const resp = await authFetch(`${API_BASE}/aios/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: input,
          mode: currentMode,
          session_id: sessionId || undefined,
          images: attachedImage ? [attachedImage] : undefined,
        }),
        signal: abortRef.current.signal,
      });
      const data = await resp.json();

      // Session creation
      if (!sessionId) {
        const newId = data.session_id || crypto.randomUUID();
        onSessionCreated(newId, input.slice(0, 40) || "New Chat");
      }

      // Brain response
      const brainMsg: ChatMessage = {
        role: "brain",
        content: data.response || data.detail || "No response",
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) +
          (data.provider ? ` · ${data.provider}` : ""),
        image: data.generation?.image_base64
          ? `data:image/png;base64,${data.generation.image_base64}`
          : undefined,
      };
      setMessages((prev) => [...prev, brainMsg]);

      // Governance: pending approvals
      const pendingApprovals = data.governance?.pending_approval || [];
      for (const approval of pendingApprovals) {
        const approvalMsg: ChatMessage = {
          role: "brain",
          content: `__APPROVAL__${JSON.stringify(approval)}`,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        };
        setMessages((prev) => [...prev, approvalMsg]);
      }

      // Governance: auto-approved actions
      const autoApproved: AutoApprovedAction[] = data.governance?.auto_approved || [];
      for (const action of autoApproved) {
        if (action.tool === "generate_image") {
          const genMsg: ChatMessage = {
            role: "brain",
            content: "✅ Generating image... (auto-approved)",
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          };
          setMessages((prev) => [...prev, genMsg]);

          try {
            const genResp = await authFetch(`${API_BASE}/api/v1/generate/image`, {
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
          } catch {
            // Generation failed silently
          }
        } else {
          const autoMsg: ChatMessage = {
            role: "brain",
            content: `✅ ${action.tool}: ${action.reasoning}`,
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          };
          setMessages((prev) => [...prev, autoMsg]);
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setMessages((prev) => [
        ...prev,
        {
          role: "brain",
          content: "Brain is reconnecting... The service may need a moment to start. Check Admin → Services if this persists.",
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }, [loading, currentMode, sessionId, onSessionCreated]);

  return {
    messages,
    loading,
    setMessages: setInitialMessages,
    sendMessage,
  };
}
