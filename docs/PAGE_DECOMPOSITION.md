# Page Decomposition Inventory (Story 136)

## Oversized Pages (>500 lines)

| Page | Lines | Priority | Domain Responsibilities |
|------|-------|----------|------------------------|
| talent | 1988 | P1 | CRUD, physical attrs, relationships, LoRA status, wardrobe, voice, gallery |
| create | 1808 | P1 | Image/video gen, prompt editor, model selection, batch, preview, save |
| brain | 1129 | P2 | Chat, modes, sessions, collections, memory, suggestions, sharing, approvals |
| editor | 956 | P2 | Source upload, transform selection, preview, output management |
| admin | 831 | P3 | Service connections, fleet, workers, settings, diagnostics |
| models | 742 | P3 | Model registry, B2 cache, availability, worker deployment |
| training | 539 | P4 | Dataset upload, config, job monitoring, version history |
| publish | 508 | P4 | Calendar, destinations, scheduling, preflight, status |

## Brain Page Responsibility Map

### Current (1129 lines in one file)
- **Chat engine**: message state, send/receive, AIOS API calls, streaming
- **Mode selector**: 6 modes with welcome messages
- **Session management**: create, load, persist to localStorage + backend
- **Collections**: create, filter, add-to
- **Context sidebar**: project, memory, suggestions
- **Modals**: memory, suggestions, share
- **Approvals**: inline approval cards with approve/reject
- **Image generation**: auto-approved generation trigger
- **Use-as-prompt**: popup to send brain output to Create page

### Decomposed Target
```
frontend/src/app/brain/
  page.tsx              — Layout shell + state coordination (~100 lines)
  _components/
    mode-selector.tsx   — Mode pills + welcome messages
    chat-panel.tsx      — Messages + input + sending logic
    session-list.tsx    — Conversations + collections + search
    context-sidebar.tsx — Project, memory, suggestions panels
    approval-card.tsx   — Inline approval widget (already extracted)
    use-as-prompt.tsx   — Popup component (already extracted)
  _hooks/
    use-brain-chat.ts   — Chat state machine, send, receive
    use-brain-sessions.ts — Session CRUD, localStorage + backend sync
    use-brain-health.ts — Health polling
```

## Decomposition Principles
1. Extract state into typed hooks (one concern per hook)
2. Extract rendering into focused components (<200 lines each)
3. Page file orchestrates layout + passes props
4. Side effects via canonical services (never raw fetch in components)
5. Preserve public route behavior exactly
