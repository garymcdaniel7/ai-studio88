"use client";

import { useState } from "react";
import { Search, MoreHorizontal, FolderPlus, Tag, Filter } from "lucide-react";
import type { Session, Collection } from "../types";

interface ConversationListProps {
  sessions: Session[];
  collections: Collection[];
  sessionId: string | null;
  filterCollection: string | null;
  onSelectSession: (session: Session) => void;
  onCreateCollection: (name: string) => void;
  onAddToCollection: (sessionId: string, collectionId: string) => void;
  onFilterChange: (collectionId: string | null) => void;
}

/**
 * Left sidebar: search, collections, and conversation list.
 */
export function ConversationList({
  sessions,
  collections,
  sessionId,
  filterCollection,
  onSelectSession,
  onCreateCollection,
  onAddToCollection,
  onFilterChange,
}: ConversationListProps) {
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
    ? sessions.filter((s) =>
        collections.find((c) => c.id === filterCollection)?.conversationIds.includes(s.id)
      )
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
        {filteredSessions.map((session) => (
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
