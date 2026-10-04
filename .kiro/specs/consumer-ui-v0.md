# Consumer UI — v0 Spec

**Codename:** "Grandma"  
**Vision:** AI Studio as a consumer creative app — grandma becomes a top creator in 2 taps.  
**Engine:** Same backend, same fleet, same cost model. Frontend is a new skin over the v1 API.

---

## Summary

This spec defines a **dual-mode UI** layered on top of the existing AI Studio engine:

- **Consumer Mode (new)** — a single-input creative feed. No model IDs, no steps, no queue. One prompt → one result. Grandma's path.
- **Creator Mode (existing)** — the full WRITE→CAST→MAKE→PUBLISH pipeline with all controls. Gary's path.

Both modes share one backend, one auth, one cost cap system. The nav relabel (START→WRITE→CAST→MAKE→PUBLISH) from the product positioning spec ships independently — it's a 10-minute config change in `navigation.ts`. This consumer spec is the new UI shell.

---

## Governance 1: Frictionless Auth with Zero Org Leak

### What the user sees (consumer mode)

1. Landing page: a big input field. No signup gate.
2. User types a prompt or uploads an image. Hits "Make it."
3. **Before generation starts:** Google SSO button or "Send me a magic link" appears as an overlay.
4. User clicks Google SSO (or enters email → receives link → clicks it).
5. **On first auth:** backend calls `POST /api/v1/workspaces/auto-provision`. This:
   - Creates a new `org` record scoped 1:1 to the user's identity
   - Creates the user's membership with role `owner`
   - Sets default cost cap (see Governance 2)
   - Returns a `session` + `access_token` — no "Welcome to your dashboard" screen
6. User lands back on the exact same input, now authenticated, and the job runs.

### What the backend enforces

The existing `org_id` middleware **does not change**. Every route still traces through `validate_org_id`. The difference:

- **Consumer flow:** `org_id` comes from the auto-provisioned workspace, never rendered to the user
- **Creator flow:** same system, but advanced users see it as "Projects" or "Workspaces" in Settings

### Endpoints required

| Endpoint | Method | Description | Risk |
|----------|--------|-------------|------|
| `POST /api/v1/workspaces/auto-provision` | POST | Creates org + membership + default cost cap for first-time Google/magic-link user | New route — needs tenant audit |
| `GET /api/v1/workspaces/current` | GET | Returns current org with cost cap, usage, role — for the frontend to display spent/remaining | Existing pattern, new fields |
| `POST /api/v1/auth/magic-link` | POST | Sends a one-time link to an email address. On click: auto-provisions if new, logs in if returning | **Critical** — rate-limit per IP/email |

### @cto's wiring check

- `org_id` is **never** exposed to the consumer frontend — no hidden JSON field, no localStorage, no URL param
- `auto-provision` creates a 1:1 org (not a shared one) — the workspace_members table should enforce `org_id` has exactly one `owner` membership for consumer-mode orgs
- Magic link expiry: 15 min, single-use, invalidates on use
- No org settings page for consumer mode — the gear menu shows only: Profile picture, Display name, Billing/cost cap, Logout

---

## Governance 2: Hard Default Cost Caps

### Architecture (already partially exists)

The capability registry (`backend/app/services/capability_registry.py`) classifies features. Costs exist in `POST /api/v1/costs`. The job queue has an `estimated_cost` field. What's missing: **enforcement at the consumer level**.

### Cap table: cost ceiling

| Tier | Default cap | Allowable actions | Override by |
|------|-----------|-------------------|-------------|
| **Consumer default** | $5.00 / month | Image gen (Krea T2I), Brain chat, 5s H3 clips (non-turbo), 1 LoRA training / mo | Parent/org admin via Settings |
| **Consumer + proof of ID** | $20.00 / month | Above + Motion Director chains (≤4 shots), Turbo mode, 2 LoRA trainings / mo | Same |
| **Creator (pro)** | $200.00 / month | Everything: 8-shot Motion Director chains, unlimited training, model-routing | Self-managed in Settings |
| **Parent/admin override** | Hard ceiling set by payer | Cannot be exceeded by the end user | Only in the admin/payer's panel |

### Backend enforcement chain

```
Frontend clicks "Generate"
  → POST /api/v1/generate (or consumer equivalent)
    → Backend checks: org_id.cost_cap_remaining >= job.estimated_cost?
      → YES: allow, decrement from cap (soft reserve)
      → NO: 402 Payment Required
        → Body: { error: "cost_cap_exceeded", 
                  cap: 5.00, 
                  spent: 5.50, 
                  reset: "2026-11-01T00:00:00Z",
                  upgrades: [ { tier: "Creator", href: "/settings/billing", monthly: 20.00 } ]
                }
```

### New endpoint

`POST /api/v1/cost-caps/estimate` — pre-flight check BEFORE the user sees a "Generate" button. Returns cost of the current job given the current prompt + settings. Consumer frontend calls this on every prompt change (debounced, 2s).

```json
// Response
{
  "estimated_cost": 0.035,
  "estimated_time_minutes": 4,
  "cap_remaining": 4.97,
  "would_exceed": false,
  "upgrade_suggested": false
}
```

### What the frontend renders

- **Green badge** when remaining > 2× estimated cost: "Available"  
- **Yellow badge** when remaining < 2× estimated cost: "$X.XX remaining this month"  
- **Red + blocked** when exceeded: "Monthly spend used up. Resets Nov 1. [Upgrade →]"  

The button is **never** disabled with a dead end — the upgrade path is always visible.

---

## Governance 3: The Consumer API Boundary

### The contract: fast vs heavy

Every route in the consumer API returns an `estimated_cost_class` and `estimated_seconds` in the response header or body. The frontend uses this to decide what UX to show.

| Class | Latency | Cost band | UX treatment |
|-------|---------|-----------|--------------|
| **⚡ Instant** | <3s | <$0.001 | Sync response — result inline, no loading state needed |
| **⏱ Quick** | 3-30s | $0.001-$0.01 | Loading spinner + ETA. Poll every 2s or SSE |
| **⏳ Heavy** | 30s-5min | $0.01-$0.10 | Full progress bar with ETA. "Come back in X min" suggests email notification |
| **🌙 Overnight** | >5min | >$0.10 | Queued. Email/mobile push on completion. "We'll ping you when it's ready." |

### Route classification table

| Consumer route | Class | Implementation | Notes |
|----------------|-------|----------------|--------|
| `POST /generate/image` | ⚡ Instant | Krea 2 T2I via ComfyUI sync wrapper. 12 steps, cfg 1, exp_heun. ~$0.0003. | Synchronous call. Frontend holds the connection open. |
| `POST /generate/video` | ⏳ Heavy | H3 5s clip at 768p. ~$0.035, ~4 min. | Async to job queue. Frontend polls `GET /jobs/:id/status` every 5s. |
| `POST /generate/series` | 🌙 Overnight | Motion Director chain (8 shots). ~$1.56, ~3 hrs. | Async. Email notification on complete. |
| `POST /brain/chat` | ⚡ Instant | Ollama 8B or DeepSeek Flash. Simple turn. $0-$0.003. | Streaming SSE response (fast tokens). |
| `POST /brain/deep-chat` | ⏱ Quick | DeepSeek Flash / Hermes 70B. Complex turn. ~$0.003-$0.006. | Same SSE contract, slightly slower. |
| `POST /talent/character-sheet` | ⏱ Quick | Krea 2 Identity Edit → 4-view turnaround. ~$0.001, ~15s. | Sync with ComfyUI timeout. |
| `POST /training/start` | 🌙 Overnight | Musubi Tuner LoRA training. ~$0.30, ~30 min GPU compute. | Queued. |
| `GET /jobs/:id/result` | ⚡ Instant | File read from object storage. | Direct CDN redirect. |

### Consumer API prefix

All consumer routes live under `/api/v2/consumer/` — distinct from the `/api/v1/` creator routes. The v2 router is a thin wrapper:

1. Receives the consumer request
2. Validates auth (auto-provisioned session or Google token)
3. Checks cost cap (Governance 2)
4. Calls the appropriate v1 endpoint internally
5. Returns the estimated class + ETA so the frontend knows what UX to show

This keeps the backend integration contract explicit: **v1 is the engine, v2 is the consumer skin.**

### What the frontend MUST NOT do

- Do NOT hardcode any model IDs, step counts, or CFG values. The `/api/v2/consumer/capabilities` call returns all generation affordances dynamically.
- Do NOT assume sync responses exist for video. Always check `estimated_class` before holding a connection open.
- Do NOT poll `/generate/*` endpoints — poll `/jobs/:id/status` instead. The generate endpoint fires once and returns a job ID.

---

## Consumer UI — User Flow (what grandma sees)

### Page 1: The Feed (landing page)

```
┌──────────────────────────────────────┐
│  [Logo]                        [👤]  │
│                                      │
│ ┌──────────────────────────────────┐ │
│ │ "What story do you want to      │ │
│ │  tell today?"                   │ │
│ │                                  │ │
│ │ [📎 Upload reference — optional] │ │
│ │                                  │ │
│ │ [🚀 Make it]                     │ │
│ └──────────────────────────────────┘ │
│                                      │
│ ┌─ RECENTLY MADE ──────────────────┐ │
│ │ ○ "Space cowboy" — 3h ago      │ │
│ │   [▶ 0:15] [↻ Remix] [📤 Share] │ │
│ │ ○ "Dragon emerges" — yesterday │ │
│ │   [▶ 0:30] [↻ Remix] [📤 Share] │ │
│ └──────────────────────────────────┘ │
│                                      │
│ [💡 Try: "A warrior wakes up in     │ │
│   a desert with no memory..."]       │ │
└──────────────────────────────────────┘
```

Key design decisions:
- **No dashboard.** The landing IS the creative action — a single input, not a grid of stats.
- **Recent work is a feed, not a project list.** Vertical scroll, autoplay on tap, share button always visible.
- **Prompt suggestions** cycle through genre hooks. Gradient from "make a thing" to "make a show."
- **Upload reference** is optional and collapsed — not a required step.
- **Auth gating:** user can type, upload, and tap "Make it" before auth. The overlay appears on submit.

### Page 2: Generation (loading state)

```
┌──────────────────────────────────────┐
│  ← Back to feed                     │
│                                      │
│  "Space cowboy"                      │
│  ┌──────────────────────────────────┐ │
│  │                                  │ │
│  │     [⏳ Preparing your           │ │
│  │      creation...]                │ │
│  │                                  │ │
│  │     ████████░░░░ 64%             │ │
│  │     ~2 min remaining             │ │
│  │                                  │ │
│  └──────────────────────────────────┘ │
│                                      │
│  [⚡ Prefer speed over quality]      │
│  [🎭 Cancel and tweak]               │
└──────────────────────────────────────┘
```

- **Only one progress item visible** — the current generation. No queue summary.
- **Cancel** kills the ComfyUI job + returns the cost to the cap.
- **"Prefer speed"** toggles Turbo mode (H3 4-step, cfg 1.0, shift 1.0/1.0) for faster but lower quality.

### Page 3: Result (playable)

```
┌──────────────────────────────────────┐
│  ← Back                              │
│                                      │
│  ┌──────────────────────────────────┐ │
│  │ [▶] 0:15                [ℹ] [📌] │ │
│  │                                  │ │
│  │     [Video plays inline]         │ │
│  │                                  │ │
│  └──────────────────────────────────┘ │
│                                      │
│  "Space cowboy — 0:15 — $0.03"       │
│                                      │
│  [↻ Remix] [📤 Share to YouTube]     │
│  [📤 Share to TikTok]                │
│  [+ Make it a series]                │
│                                      │
│  ┌─ COST THIS MONTH ────────────┐   │
│  │ Spent: $0.47 of $5.00        │   │
│  │ [Upgrade →]                   │   │
│  └──────────────────────────────┘   │
└──────────────────────────────────────┘
```

- **"Make it a series"** graduates the user to creator mode — opens the WRITE pipeline with the current result as episode 1.
- **Share buttons** are one-tap. Backend generates a shareable link with the video embedded.
- **Cost display** is subtle but present — educates without alarming.

---

## Sidebar: What changes vs what stays

| Component | Current state | Consumer mode | Creator mode |
|-----------|--------------|---------------|--------------|
| Nav sections | Create/Manage/Operate | Hidden (feed nav only) | START→WRITE→CAST→MAKE→PUBLISH (post-relabel) |
| Topbar | Alerts, search, mobile menu | Minimal: logo + user avatar + gear | Same as consumer + brain dock |
| Dashboard | Metric cards, job queue, system status | Replaced by the Feed | Collapsed to journey prompt (per product positioning spec) |
| Admin/Settings | Top-level nav items | Moved to gear dropdown | Moved to gear dropdown |
| Brain | Nav item | Persistent floating FAB | Persistent floating FAB |
| Admin panel | Full route | Hidden from non-owner roles | Same |
| Analytics | Full route | Summary in Settings | Accessible from gear menu |

---

## Implementation order (for Kiro)

| Phase | What | Why |
|-------|------|-----|
| **P0** | Nav relabel in `navigation.ts` (Create→START, Manage→WRITE... etc) | 10-min win, unblocks all future UX work |
| **P1** | `POST /api/v1/workspaces/auto-provision` + `POST /api/v1/auth/magic-link` | CTO governance #1 — auth gate blocks everything |
| **P1** | `POST /api/v1/cost-caps/estimate` endpoint | CTO governance #2 — cost gate before any consumer gen |
| **P1** | Cost cap enforcement in job queue `claim_next_job()` | Worker-side check, not just frontend |
| **P2** | `/api/v2/consumer/` wrapper router + route classification headers | CTO governance #3 — explicit API boundary |
| **P2** | Consumer feed page (new frontend route `app/feed/`) | Primary UX surface |
| **P2** | One-tap "Make it" → auth overlay → generation → result | End-to-end consumer flow |
| **P3** | "Make it a series" transition → creator pipeline | The conversion funnel |
| **P3** | Share-to-YouTube/TikTok one-tap buttons | Distribution layer |
| **P3** | Session-stable capability badges (fix flicker from spec-review skill) | Demo-ready |

---

## Guardrails (from our production playbook)

| Lesson | Where it applies |
|--------|------------------|
| **Simulation fallback is env-gated, not deleted** — consumer mode in dev/staging should simulate without a GPU | Every `/api/v2/consumer/generate` path wraps the v1 call in a try/except that falls back to `simulated: true` metadata (local/staging only). Prod fails hard. |
| **Model-ID canonicalization** — consumer frontend sends `"quickest"`, `"best_quality"`, `"turbo"` as affordances, not model names | The v2 router maps these to canonical model IDs. NEVER pass model IDs to the consumer frontend. |
| **Cost estimates are approximate** — display as "~$X.XX", never a precise number | Consumer UI shows range or rounded. Only the capability is precise; the cost is an estimate. |
| **GPU idle time is the enemy** — consumer mode should batch idle requests | If the user hasn't generated in 30s, flush the GPU state. Re-init costs less than idle VRAM. |
| **Never animate a still that failed edge-energy check** — consumer T2I stills get the same QA gate | Consumer mode runs the same edge-energy ≥6 / variance ≥800 check silently. If it fails, re-generate once before surfacing to the user. |