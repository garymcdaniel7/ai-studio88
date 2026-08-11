"use client";

import { Brain } from "lucide-react";
import type { ChatMessage } from "../types";
import { ApprovalCard } from "./ApprovalCard";
import { UseAsPromptButton } from "./UseAsPromptButton";
import { LOADING_MESSAGES } from "../constants";

interface ChatThreadProps {
  messages: ChatMessage[];
  loading: boolean;
  currentMode: string;
  brainOnline: boolean;
}

/**
 * Chat message thread — renders messages, approval cards, and loading indicator.
 */
export function ChatThread({ messages, loading, currentMode, brainOnline }: ChatThreadProps) {
  if (messages.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto p-6">
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <Brain className="h-12 w-12 text-purple-400/30 mx-auto mb-3" />
            <p className="text-sm text-gray-500">Select a mode above to get started</p>
            <p className="text-xs text-gray-600 mt-1">
              {brainOnline ? "🟢 Hermes connected" : "🔴 Reconnecting..."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
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
            {/* Attached image */}
            {msg.image && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={msg.image} alt="Attached" className="rounded-lg max-w-[300px] max-h-[200px] object-cover mb-2" />
            )}
            {/* Message content or approval card */}
            {msg.content.startsWith("__APPROVAL__") ? (
              <ApprovalCard data={JSON.parse(msg.content.replace("__APPROVAL__", ""))} onAction={() => {}} />
            ) : (
              <p className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
            )}
            <p className="mt-1 text-[10px] text-gray-500">{msg.time}</p>
            {/* Use as Prompt hover button */}
            {msg.role !== "user" && i > 0 && !msg.content.startsWith("__APPROVAL__") && (
              <div className="absolute -bottom-3 right-2 opacity-0 group-hover/msg:opacity-100 transition-opacity">
                <UseAsPromptButton content={msg.content} />
              </div>
            )}
          </div>
        </div>
      ))}
      {loading && <LoadingIndicator currentMode={currentMode} />}
    </div>
  );
}

function LoadingIndicator({ currentMode }: { currentMode: string }) {
  return (
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
          {LOADING_MESSAGES[currentMode] || "Processing your request..."}
        </p>
      </div>
    </div>
  );
}
