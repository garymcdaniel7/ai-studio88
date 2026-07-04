# AI Studio — UX Recommendations

> Date: 2026-07-04

---

## Recommended Navigation Structure (Implemented)

```
[Top]
  Home          — Dashboard overview
  Brain         — AI assistant chat

[Create]
  Create        — Generate images/video/audio
  Editor        — Timeline video editor
  Training      — Fine-tune LoRA models

[Manage]
  Talent        — AI personas & characters
  Assets        — Media library
  Story         — Story universes
  Models        — AI model manager

[Operate]
  Production    — Job queue & workers
  Publish       — Content calendar
  Analytics     — Platform metrics
  Admin         — Settings & infrastructure
```

---

## Design System Observations

### Consistent Patterns (Keep)
- Card: `rounded-xl border border-white/[0.06] bg-[#12122a] p-5`
- Button primary: `rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700`
- Button secondary: `rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300`
- Page title: `text-2xl font-bold text-white` + subtitle `text-sm text-gray-500`
- Status dots: green=active, amber=warning, gray=offline
- Loading: `<Loader2 className="h-8 w-8 animate-spin text-purple-500" />`

### Gaps
- No standard "confirm dialog" component (using browser `confirm()`)
- No toast/notification system for success/error feedback
- No standard "badge" component (each page reimplements)
- No standard "modal" component (Brain suggestions uses custom)
- No breadcrumbs for drill-down pages (Story universe → characters)

---

## Quick Wins (< 1 hour each)

1. Add talent tab filtering (filter by type field)
2. Replace Math.random() analytics with real data from `/api/v1/infrastructure/cost` and `/api/v1/generation/history`
3. Add a toast component for success/error feedback
4. Make talent "Import" button show a file picker for JSON import
5. Add breadcrumbs to Story page when viewing a universe

---

## Larger Redesign Recommendations

### 1. Workspace/Project Model
Currently there's no concept of "projects" grouping work together. Recommend:
- Add a "Projects" entity that groups: talent + story + assets + generated content
- Allow switching between projects from sidebar
- This gives structure to the homepage "Active Projects" KPI

### 2. Unified Generation Queue
The Create page generates synchronously (waits for result). For video/audio which take longer:
- Submit to job queue → redirect to Production page
- Production page shows real-time progress
- Notification when job completes

### 3. Real-Time Feedback
Replace browser `alert()` and `confirm()` with:
- A toast library (react-hot-toast or sonner)
- A confirmation dialog component (shadcn AlertDialog)
- WebSocket or SSE for long-running job updates

### 4. Onboarding Flow
New users see an empty dashboard with "0" everywhere. Recommend:
- First-time guided tour (highlight sidebar sections)
- "Getting Started" checklist on homepage
- Pre-populate Brain with a welcome conversation
