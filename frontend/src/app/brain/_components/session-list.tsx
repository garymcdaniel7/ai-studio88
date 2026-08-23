"use client";

import { useState } from "react";
import { Search, MoreHorizontal, FolderPlus, Tag, Filter, AlertTriangle, MessageSquarePlus } from "lucide-react";
import type { Session, Collection } from "../_hooks/use-brain-sessions";

interface SessionListProps {
  sessions: Session[];
  collections: Collection[];
  sessionId: string | null;
  filterCollection: string | null;
  /** True while the backend session fetch is in flight. */
  isLoading?: boolean;
  /** Set when loading conversations from the server failed. */
  error?: string | null;
  onSelectSession: (session: Session) => void;
  onCreateCollection: (name: string) => void;
  onAddToCollection: (sessionId: string, collectionId: string) => void;
  onFilterChange: (collectionId: string | null) => void;
}

/**
 * Conversations sidebar with search, collections, and session list.
 * Renders loading skeletons, error, and empty (all / filtered) states.
 */
export function SessionList({
  sessions,
  collections,
  sessionId,
  filterCollection,
  isLoading = false,
  error = null,
  onSelectSession,
  onCreateCollection,
  onAddToCollection,
  onFilterChange,
}: SessionListProps) {
  const [showNewCollection, setShowNewCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [contextMenuSession, setContextMenuSession] = useState<string | null>(null);

  function handleCreateCollection() {
    if (newCollectionName.trim()) {
      onCreateCollection(newCollectionName.trim());
      setNewCollectionName("");
      setShowNewCollection(false);
    }
  }

  const filteredSessions = filterCollection
    ? sessions.filter((s) => collections.find((c) => c.id === filterCollection)?.conversationIds.includes(s.id))
    : sessions;

  return (
    <div className="border-r border-white/[0.06] p-4 overflow-y-auto">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">Conversations</h3>
      </div>
      <div className="mb-3 flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1.5">
        <Search className="h-3.5 w-3.5 text-gray-500" />
        <input className="flex-1 bg-transparent text-xs text-gray-300 placeholder:text-gray-600 outline-none" placeholder="Search conversations..." />
      </div>

      {/* Collections */}
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
              onKeyDown={(e) => { if (e.key === "Enter") handleCreateCollection(); }}
              placeholder="Collection name..."
              className="flex-1 rounded border border-white/[0.08] bg-white/[0.03] px-2 py-1 text-xs text-gray-300 outline-none"
              autoFocus
            />
            <button onClick={handleCreateCollection} className="text-xs text-purple-400 hover:text-purple-300">Add</button>
          </div>
        )}
        {collections.length > 0 && (
          <div className="space-y-1 mb-2">
            {collections.map((col) => (
              <button
                key={col.id}
                onClick={() => onFilterChange(filterCollection === col.id ? null : col.id)}
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
          <button onClick={() => onFilterChange(null)} className="text-[10px] text-gray-500 hover:text-gray-300 mb-2 flex items-center gap-1">
            <Filter className="h-3 w-3" /> Clear filter
          </button>
        )}
      </div>

      {/* Session list */}
      <div className="space-y-1">
        <p className="text-[10px] font-medium text-gray-600 uppercase px-2 mt-3">Recent</p>

        {/* Error: server load failed and nothing to fall back to */}
        {error && filteredSessions.length === 0 && (
          <div
            className="mx-1 mt-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-3"
            role="alert"
          >
            <p className="flex items-center gap-1.5 text-xs font-medium text-red-300">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> Couldn&apos;t load conversations
            </p>
            <p className="mt-1 text-[10px] leading-relaxed text-gray-500">
              {error} New chats still work here — past conversations will reappear when the
              connection recovers.
            </p>
          </div>
        )}

        {/* Loading skeletons */}
        {!error && isLoading && filteredSessions.length === 0 && (
          <div className="mt-2 space-y-2" aria-label="Loading conversations" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="animate-pulse rounded-lg px-3 py-2.5">
                <div className="h-3 w-3/4 rounded bg-white/[0.06]" />
                <div className="mt-1.5 h-2 w-1/3 rounded bg-white/[0.04]" />
              </div>
            ))}
          </div>
        )}

        {/* Empty: no conversations at all */}
        {!error && !isLoading && sessions.length === 0 && (
          <div className="px-2 py-6 text-center" role="status">
            <MessageSquarePlus className="h-6 w-6 mx-auto mb-2 text-gray-600" />
            <p className="text-xs text-gray-400">No conversations yet</p>
            <p className="mt-1 text-[10px] text-gray-600">
              Start a new chat and it will show up here.
            </p>
          </div>
        )}

        {/* Empty: filter active but no matches */}
        {!error && !isLoading && sessions.length > 0 && filteredSessions.length === 0 && (
          <div className="px-2 py-6 text-center" role="status">
            <Tag className="h-5 w-5 mx-auto mb-2 text-gray-600" />
            <p className="text-xs text-gray-400">Nothing in this collection yet</p>
            <button
              onClick={() => onFilterChange(null)}
              className="mt-2 text-[10px] text-purple-400 hover:text-purple-300"
            >
              Clear filter to see all conversations
            </button>
          </div>
        )}

        {filteredSessions.length > 0 && filteredSessions.map((session) => (
          <div key={session.id} className="relative">
            <div
              onClick={() => onSelectSession(session)}
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
                    onClick={() => { onAddToCollection(session.id, col.id); setContextMenuSession(null); }}
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
      </div>
    </div>
  );
}
