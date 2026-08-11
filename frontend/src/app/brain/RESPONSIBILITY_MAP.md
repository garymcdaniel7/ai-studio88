# Brain Page Responsibility Map — Story 136.a

## Current State

The Brain page (`page.tsx`) is ~650 lines containing 8+ responsibilities:

## Responsibility Domains

| # | Domain | Lines | Extracted To | Status |
|---|--------|-------|-------------|--------|
| 1 | **Types & Constants** | ~50 | `types.ts`, `constants.ts` | ✅ Done |
| 2 | **Health Polling** | ~10 | Inline in page (simple) | ✅ Done |
| 3 | **Session/Conversation Management** | ~80 | `hooks/use-brain-sessions.ts` | ✅ Done |
| 4 | **Collections Management** | ~40 | `hooks/use-collections.ts` | ✅ Done |
| 5 | **Memory Management** | ~20 | `hooks/use-brain-memory.ts` | ✅ Done |
| 6 | **Chat/Message Sending** | ~100 | `hooks/use-brain-chat.ts` | ✅ Done |
| 7 | **Conversation List Panel** | ~120 | `components/ConversationList.tsx` | ✅ Done |
| 8 | **Chat Thread Panel** | ~100 | `components/ChatThread.tsx` | ✅ Done |
| 9 | **Composer (Input + Attachments + Voice)** | ~80 | `components/Composer.tsx` | ✅ Done |
| 10 | **Context Sidebar (Memory + Suggestions)** | ~100 | `components/ContextSidebar.tsx` | ✅ Done |
| 11 | **Modals (Memory, Suggestions, Share)** | ~120 | `components/BrainModals.tsx` | ✅ Done |
| 12 | **ApprovalCard** | ~50 | `components/ApprovalCard.tsx` | ✅ Done |
| 13 | **UseAsPromptButton** | ~40 | `components/UseAsPromptButton.tsx` | ✅ Done |

## Issues Found

1. ~~**Raw `fetch` to `API_BASE`** — should use shared `api.ts` transport (Story 008)~~ Moved to hooks (isolated)
2. ~~**`window` globals for image attachment** — unsafe~~ Fixed: Composer uses React state
3. **localStorage as primary persistence** — should be cache only, backend is truth (follow-up)
4. ~~**Health polling duplicates** system health store (Story 118)~~ Isolated in page (simple)
5. ~~**No error handling** on chat send failures~~ Fixed: reconnect message on error
6. ~~**Mode change clears session** — may lose unsaved work~~ Preserved (intentional UX)

## Extraction Plan (Priority Order)

### Phase 1: Types + Constants (Done)
- `types.ts` — shared interfaces

### Phase 2: Hooks (replaces local state logic)
- `use-brain-chat.ts` — sendMessage, loading, messages, session creation
- `use-brain-sessions.ts` — load/save sessions, localStorage cache + backend sync
- `use-collections.ts` — CRUD collections, filter logic
- `use-brain-memory.ts` — fetch and display brain memory

### Phase 3: Components (UI extraction)
- `ConversationList.tsx` — left panel
- `ChatThread.tsx` — message rendering + loading indicator
- `Composer.tsx` — input, attachments, voice, send button
- `ContextSidebar.tsx` — right panel (memory + suggestions)
- `BrainModals.tsx` — memory, suggestions, share modals

### Phase 4: Cleanup
- Remove `window.__brain_attached_image` hack → use Composer state
- Replace raw fetch with `api.post()` / `api.get()`
- Replace health polling with `useHealthStore()` subscription
- Add error boundaries per panel

## Canonical Services to Consume

| Current Local Logic | Replace With |
|--------------------|-------------|
| `getBrainHealth()` polling | `health-store.ts` subscription |
| `fetch(API_BASE + "/aios/v1/chat")` | `api.post("/aios/v1/chat")` |
| `localStorage` sessions | Backend sync via `api.get("/api/v1/brain/sessions")` |
| `localStorage` collections | Backend sync via `api.post("/api/v1/brain/collections")` |
| `fetch(API_BASE + "/api/v1/brain/memory")` | `api.get("/api/v1/brain/memory")` |

## Browser-Side Authority Removed

- ❌ Session ID generation (`crypto.randomUUID()`) → server provides ID
- ❌ Message persistence timing (3s debounce) → immediate on send via API
- ❌ Window globals for attachments → React state in Composer

## Tests Required

- Chat send → message appears → session created
- Mode switch → welcome message → previous session preserved
- Attachment upload → preview → sent with message → cleared
- Voice input → transcript appended
- Approval card → approve/reject → status changes
- Collections CRUD → filter works
- Reconnect → messages recovered from backend
- Error state → user sees helpful message
