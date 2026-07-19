# AI Studio V2 — Human-Centered UX Refactor & AI Brain Product Evolution

> **Document Type:** Complete Product Discovery & UX Redesign Analysis  
> **Date:** July 2026  
> **Authors:** AI Studio Development Team (13 Specialists)  
> **Status:** Analysis Complete — Ready for Implementation Planning

---

## Table of Contents

1. [Complete UX Audit](#1-complete-ux-audit)
2. [Current Navigation Analysis](#2-current-navigation-analysis)
3. [Human-Centered Redesign Proposal](#3-human-centered-redesign-proposal)
4. [Information Architecture](#4-information-architecture)
5. [User Personas](#5-user-personas)
6. [User Journeys](#6-user-journeys)
7. [Brain Interaction Flows](#7-brain-interaction-flows)
8. [Navigation Map](#8-navigation-map)
9. [Screen Inventory](#9-screen-inventory)
10. [Design System Recommendations](#10-design-system-recommendations)
11. [Creative Team Architecture](#11-creative-team-architecture)
12. [Creative Recipes](#12-creative-recipes)
13. [AI Automation Boundaries](#13-ai-automation-boundaries)
14. [Migration Strategy](#14-migration-strategy)
15. [Risk Analysis](#15-risk-analysis)
16. [Phased Implementation Roadmap](#16-phased-implementation-roadmap)

---

## 1. Complete UX Audit

### Page-by-Page Analysis

#### `/` — Home (Dashboard)
**File:** `frontend/src/app/page.tsx`  
**Purpose:** System overview dashboard with live metrics, quick actions, suggestions.

**Issues Identified:**
- **Information overload on first load** — 6 metric cards + 3-column grid + system status bar all compete for attention. New users have no mental model for "Worker," "Fleet," or "GPU Spend."
- **Hardcoded suggestions** — The "AI Brain Suggestions" panel shows static content ("Reuse FLUX workflow," "Optimize GPU costs") that doesn't reflect actual user activity.
- **No project context** — The dashboard shows infrastructure metrics but nothing about the user's creative work. No recent projects, no continuation prompts.
- **Technical language** — "GPU Spend (today)," "Services Online 6/9," "Worker: Offline" — these are operator terms, not creator terms.
- **Dismiss pattern is localStorage-only** — Dismissed suggestions persist per-browser but not per-account.
- **Jobs donut chart** — Useless when total is 0 (common for new users). Shows empty ring.
- **No onboarding** — No first-run experience. A brand new user lands on infrastructure metrics.

#### `/brain` — AI Brain
**File:** `frontend/src/app/brain/page.tsx`  
**Purpose:** Conversational AI interface with 6 modes, session management, memory panel.

**Issues Identified:**
- **Three-panel layout is cramped** — 280px conversations + main chat + 300px context = no breathing room on smaller screens.
- **Mode switching resets conversation** — Switching between Creative Chat/Prompt Engineer/etc clears messages. Users expect context to persist.
- **Collections are localStorage-only** — Loss on device switch. No cloud sync.
- **Window globals for image state** — `(window).__brain_attached_image` is a fragile anti-pattern.
- **6 mode cards take premium viewport space** — 50% of the above-fold area is mode selection that users pick once and rarely change.
- **"Brain Context" sidebar is mostly empty** — Shows "No active project" and static placeholder suggestions. Doesn't feel intelligent.
- **Approval cards inline in chat** — Good pattern, but no batching. Multiple approvals stack vertically and push conversation out of view.
- **No streaming** — Messages appear all-at-once after full generation. No token streaming.
- **Share modal options are naive** — SMS/iMessage sharing for a professional tool feels off-brand.

#### `/create` — Create Page
**File:** `frontend/src/app/create/page.tsx`  
**Purpose:** Multi-tab generation interface (Image, Video, Audio, Full Production).

**Issues Identified:**
- **900+ lines in a single component** — Massive monolith. No code splitting by tab.
- **Technical parameter exposure** — Steps, CFG, Seed, ControlNet strength shown by default (behind "Advanced" toggle but still prominently placed). Users shouldn't need to know what CFG means.
- **No connection to Talent DNA** — Talent injection exists in Advanced panel but is hidden. Should be primary UX: "Generate as [Melissa]."
- **Full Production tab is a dead end** — Just shows a big icon and "Open Video Editor" link. Not a real feature.
- **Favorite prompts use localStorage** — Same device-only problem.
- **Music tab admits it doesn't work** — Shows "requires a connected provider (Suno or Udio)" — should be hidden if unavailable.
- **No generation queue visualization** — User clicks Generate and gets a spinner. No position-in-queue, no ETA.
- **Model list doesn't indicate which are actually available** — Shows all models registered in DB. User picks Flux 2 Dev (24GB+) but might have an 8GB worker.

#### `/editor` — Video Editor
**File:** `frontend/src/app/editor/page.tsx`  
**Purpose:** Storyboard + Quick Edit (video trimming via FFmpeg).

**Issues Identified:**
- **Two unrelated tools forced together** — Storyboard (shot planning + AI generation) and Quick Edit (video trimming) share a page but have zero interaction.
- **Storyboard UX is shot-centric, not story-centric** — Users add shots one-by-one without narrative structure. No act breaks, no story arc visualization.
- **Quick Edit is basic** — Trim, speed, resolution, color grade, text overlay. Competes poorly with CapCut/DaVinci which are free.
- **Assembly endpoint likely returns errors** — Assemble calls `/api/v1/productions/assemble` which requires FFmpeg on a GPU worker that may not be running.
- **No preview of assembled video** — Users get a URL string result, not an inline video player.
- **Drag-to-reorder lacks touch support** — HTML5 drag API doesn't work on mobile/tablet.

#### `/workflows` — Workflow Viewer
**File:** `frontend/src/app/workflows/page.tsx`  
**Purpose:** Read-only visualization of ComfyUI workflow templates.

**Issues Identified:**
- **Expert-only content** — Normal creators have no use for viewing ComfyUI node graphs. This page serves developers/operators only.
- **Linear visualization is misleading** — ComfyUI workflows are DAGs, not linear pipelines. The left-to-right layout misrepresents branching.
- **No editing** — "Read-only" is stated. If users can't modify workflows, this is reference documentation disguised as a page.
- **No connection to generation** — Can't select a workflow and generate from it. It's disconnected from the Create page.

#### `/talent` — Talent Management
**File:** `frontend/src/app/talent/page.tsx`  
**Purpose:** CRUD for AI personas (models, characters, voices, wardrobe, products, backgrounds).

**Issues Identified:**
- **1000+ line monolith** — Includes TalentMediaSection, TalentLoraSection, TalentVoiceSection, TalentRelationshipsSection, TalentEditModal, TalentProfileImage, VoiceDemoButton all in one file.
- **8 filter tabs overwhelm** — "All Talent | Models | Characters | Voices | Influencers | Wardrobe | Products | Backgrounds" — too many categories for a new user.
- **Detail panel is right-aligned** — On wide screens, the grid + panel layout works. On 1440px screens, the 380px panel compresses the grid to unusable widths.
- **Edit modal is a massive form** — Every field for every type in one modal. Conditional sections (wardrobe vs product vs background) help but cognitive load is still high.
- **Relationships are powerful but hidden** — The AIOS architecture identifies relationships as the key differentiator. But it's a tab within a tab, accessible only after clicking a talent then "Relationships."
- **No bulk operations** — Can't select multiple talent and batch-apply actions (assign LoRA, add to project, etc.)

#### `/assets` — Assets Page
**File:** `frontend/src/app/assets/page.tsx`  
**Purpose:** File browser for uploaded/generated content.

**Issues Identified:**
- **Identity crisis** — Per AIOS architecture (Section 9.5): "The Assets page becomes redundant. Assets are just files." Yet it exists as a standalone navigation item.
- **No relationship to Talent** — Uploaded assets don't link to talent entities. They're orphaned files.
- **Filter categories don't match actual content** — "Objects," "Backgrounds," "Wardrobe," "Products," "Brand" filters use tag-matching that rarely hits because assets aren't tagged on upload.
- **Export All downloads every asset individually with setTimeout stagger** — This will trigger browser download blocking and isn't scalable.
- **No visual DNA** — The architecture envisions "Every asset gets Object DNA." Current page shows filename and thumbnail only.
- **Delete confirmation is browser `confirm()`** — Inconsistent with the premium dark theme aesthetic.

#### `/models` — Model Manager
**File:** `frontend/src/app/models/page.tsx`  
**Purpose:** Manage AI models (checkpoints, LoRAs, VAEs, ControlNets).

**Issues Identified:**
- **Technical operator tool** — Regular creators shouldn't need to manage safetensors files. This is admin/operator territory.
- **Upload flow exposes internal paths** — B2 paths, ComfyUI paths, storage paths visible.
- **Model inventory is useful but misplaced** — Shows what's on B2 vs what's on worker. Important for operators, irrelevant for creators.
- **No connection to generation** — Can't go from model → generate with it. Should link to Create page with model pre-selected.

#### `/training` — LoRA Training
**File:** `frontend/src/app/training/page.tsx`  
**Purpose:** Upload training images, configure hyperparameters, submit training jobs.

**Issues Identified:**
- **Technical parameters exposed raw** — Steps (1000), Rank (16), Optimizer (adamw_bf16), Scheduler (polynomial), Learning Rate (1e-4) — these mean nothing to a creator.
- **Good: Pre-populates from Talent page** — `?talent_id=` param integration works well.
- **Missing: Cost estimate before submission** — Architecture principle says "All GPU jobs must have a cost estimate before dispatching." Not shown here.
- **No training presets** — Every time a user trains, they configure from scratch. Should offer "Quick (500 steps) / Standard (1000) / Quality (2000)" presets.
- **Job status polling is basic** — No progress visualization beyond percentage.

#### `/production` — Production Queue
**File:** `frontend/src/app/production/page.tsx`  
**Purpose:** Job queue monitor + fleet status + GPU worker management.

**Issues Identified:**
- **Pure infrastructure monitor** — Shows jobs, workers, costs. No creative context (which project is this job for?).
- **Worker launch is one-click but expensive** — Launches a $1.50/hr GPU with no confirmation of spend.
- **Clear completed jobs is destructive** — Deletes jobs from DB. Should archive instead.
- **No job detail view** — Can't click a job to see its prompt, output, parameters, or timeline.
- **Duplicate of Admin functionality** — Admin page also shows fleet/worker controls.

#### `/publish` — Publishing Calendar
**File:** `frontend/src/app/publish/page.tsx`  
**Purpose:** Content calendar with scheduling for social platforms.

**Issues Identified:**
- **Calendar-first UX is wrong** — Users come to publish specific content. Showing a monthly calendar first forces them to find the date then discover if anything is scheduled.
- **No OAuth integration visible** — Can schedule posts but platforms aren't connected. Should show connected/disconnected state prominently.
- **No content preview** — Schedule form asks for title/platform/date but doesn't show what will be posted.
- **No content library integration** — Can't browse generated assets and schedule them. Have to know what you want to post before opening this page.

#### `/analytics` — Analytics
**File:** `frontend/src/app/analytics/page.tsx`  
**Purpose:** Cost tracking, generation metrics, publishing performance.

**Issues Identified:**
- **Mixed concerns** — GPU costs (operator metric) alongside content engagement (creator metric). Different users care about different sections.
- **Bar chart visualization is custom** — Hand-rolled SVG bars instead of a proper charting library. Limited interactivity.
- **Publishing analytics shows dummy engagement data** — Views, likes, comments, shares — but no actual social API integration to source these.
- **No time-range comparison** — Can filter by 30 days but can't compare periods (this month vs last month).

#### `/admin` — Admin Panel
**File:** `frontend/src/app/admin/page.tsx`  
**Purpose:** Service connections, worker control, system configuration.

**Issues Identified:**
- **Correct audience, wrong structure** — Has 5 sub-pages (fleet, ise, keys, knowledge, downloads) but main page tries to do everything.
- **GPU provider controls are duplicated** — Worker launch/stop/pause/resume also available on Production page.
- **Ollama preference toggle is well-designed** — Local/Remote/Auto selector is clear.
- **Service health checks are useful** — Shows Supabase, B2, Vast.ai, Ollama connectivity status.
- **No audit log** — Architecture calls for decision traceability. No UI for viewing it.

#### `/admin/fleet` — GPU Fleet Management
- Worker fleet management, multi-provider orchestration.
- Good: purpose-specific sub-page for operators.

#### `/admin/ise` — ISE (Quality Agent)
- Corresponds to Ìṣẹ́ quality agent from AIOS architecture.
- Likely placeholder or early implementation.

#### `/admin/keys` — API Key Management
- Configure external service keys (Vast.ai, OpenAI, ElevenLabs, etc.)
- Critical for setup but visited rarely.

#### `/admin/knowledge` — Knowledge Base
- Brain memory, embeddings, RAG configuration.
- Operator-level feature.

#### `/admin/downloads` — Model Downloads
- B2 model management, download status.
- Operator-level feature.

#### `/settings` — Settings
**File:** `frontend/src/app/settings/page.tsx`  
**Purpose:** Profile, help docs, FAQ, about page.

**Issues Identified:**
- **Underutilized** — Only shows profile name, generation count, and static help text.
- **No preference management** — Should control: default model, preferred resolution, auto-approve thresholds, notification preferences, theme, etc.
- **No account management** — No team invitations, no role management, no billing (as per Phase 5 roadmap).
- **Help content is inline text** — Should be a proper documentation site or at minimum a more structured guide.

---

### Cross-Cutting UX Issues

| Issue | Severity | Affected Pages |
|-------|----------|----------------|
| No onboarding / first-run experience | Critical | All |
| localStorage for state that should be cloud-synced | High | Brain, Create, Talent, Home |
| Technical terminology exposed to non-technical users | High | Create, Training, Models, Production, Home |
| No project-centric organization | High | All — everything is entity-centric (talent, assets, models) not project/campaign-centric |
| No loading skeletons — uses spinners | Medium | All pages |
| No error boundaries — silent failures | Medium | All pages |
| Inconsistent empty states | Medium | Assets, Production, Analytics |
| Mobile unresponsive (sidebar hidden, grids fixed) | Medium | All pages |
| No keyboard shortcuts | Low | Brain, Create, Editor |
| No dark/light theme toggle (dark only) | Low | All |
| `API_BASE` hardcoded as Railway production URL in fallback | Critical | All pages use `process.env.NEXT_PUBLIC_API_URL || "https://web-production-1f511.up.railway.app"` — leaks production URL |

---

## 2. Current Navigation Analysis

### Sidebar Structure (from `sidebar.tsx`)

```
[No Label]
  Home        /
  Brain       /brain

[Create]
  Create      /create
  Editor      /editor
  Workflows   /workflows
  Training    /training

[Manage]
  Talent      /talent
  Assets      /assets
  Models      /models

[Operate]
  Production  /production
  Publish     /publish
  Analytics   /analytics
  Admin       /admin
```

### Page Survival Assessment

| Page | Who Uses It | Verdict | Reasoning |
|------|------------|---------|-----------|
| `/` Home | Everyone | **Redesign** | Needs project focus, not infrastructure metrics |
| `/brain` | Creators, Operators | **Promote** | Becomes the primary interface. Brain IS the product. |
| `/create` | Creators | **Absorb into Brain** | "Create a luxury image of Melissa" should work from Brain. Keep as advanced/manual mode. |
| `/editor` | Creators | **Keep + Evolve** | Storyboard is unique value. Quick Edit can merge into Projects. |
| `/workflows` | Developers only | **Move to Admin** | Not a creator tool. Developer reference. |
| `/talent` | Creators, Operators | **Keep + Simplify** | Core entity management. Rename to "Cast" or keep "Talent." |
| `/assets` | Everyone | **Merge into Talent/Projects** | Per AIOS design: assets belong to talent, not standalone. Global gallery remains as a filtered view. |
| `/models` | Operators only | **Move to Admin** | Creators shouldn't manage model files. Brain handles selection. |
| `/training` | Creators (advanced) | **Keep + Simplify** | Valuable but needs "one-click" preset mode. |
| `/production` | Operators | **Merge into Projects** | Job queue belongs in project context, not a separate page. |
| `/publish` | Creators | **Keep + Evolve** | Content calendar is a first-class feature. Needs content browser integration. |
| `/analytics` | Creators, Operators | **Split** | Creator analytics (content performance) ≠ Operator analytics (GPU costs). |
| `/admin` | Operators | **Keep** | Correct scope. Absorb Models, Workflows, Fleet. |
| `/settings` | Everyone | **Expand** | Add preferences, team, billing, integrations. |

---

## 3. Human-Centered Redesign Proposal

### Three Experience Modes

#### Brain Mode (Default — Conversational)
**Audience:** All users  
**Metaphor:** Talking to a creative director who has a team behind them.

- Single conversational interface
- User says: "Create a luxury fashion campaign for Melissa in Tokyo"
- Brain orchestrates: selects talent, picks model, designs prompt, generates content, suggests publishing
- All parameters hidden — Brain makes intelligent defaults
- Approval gates only when cost/risk thresholds exceeded
- Users can ask follow-up questions, refine, iterate

**UI:** Full-screen chat with contextual panels that slide in (talent preview, generation progress, results gallery).

#### Studio Mode (Visual Creative)
**Audience:** Hands-on creators who want visual control  
**Metaphor:** Creative studio with workstations

- Project-centric workspace
- Visual canvas for storyboards, mood boards, shot lists
- Drag-and-drop asset management
- Side-by-side generation and refinement
- Quick parameter tweaks (but still intelligently pre-configured)
- Talent DNA always visible and injectable

**UI:** Multi-panel workspace with project sidebar, canvas area, and toolbars.

#### Expert Mode (Technical)
**Audience:** Operators, developers, power users  
**Metaphor:** Control room

- Full parameter control
- Workflow editor (ComfyUI visual)
- Model management, GPU fleet control
- Raw API access, debugging tools
- Cost analytics, system health
- Same features as V1 but better organized

**UI:** Dense dashboard with tabs, tables, and technical controls.

### Mode Switching

- User selects default mode in onboarding
- Can switch via toggle in top bar
- Brain Mode is always accessible (bottom dock) regardless of active mode
- Content created in any mode appears in the same project

---

## 4. Information Architecture

### V2 Page Structure

```
/                          → Smart Home (project feed + Brain quick-start)
/brain                     → Brain Mode (full conversational interface)
/projects                  → Projects (campaigns, collections, stories)
/projects/[id]             → Project workspace (all assets, shots, timeline)
/talent                    → Talent Library (people, wardrobe, products, backgrounds)
/talent/[id]               → Talent Profile (DNA, media, relationships, generations)
/create                    → Studio Mode (manual generation with visual controls)
/editor                    → Production Editor (storyboard + video assembly)
/library                   → Global Gallery (all generated content, searchable)
/publish                   → Publishing Hub (calendar + content queue + analytics)
/training                  → Training Center (simplified, preset-driven)
/settings                  → User Settings (preferences, team, billing, integrations)
/admin                     → Admin Panel (operators only)
/admin/fleet               → GPU Fleet Management
/admin/models              → Model Registry
/admin/workflows           → Workflow Templates
/admin/keys                → API Keys & Providers
/admin/knowledge           → Knowledge Base
/admin/analytics           → System Analytics (costs, performance)
/admin/ise                 → Quality Agent
```

### Key Structural Changes

1. **Projects become first-class** — Replace "Production" with project workspaces that contain jobs, assets, storyboards, publishing plans.
2. **Assets dissolve** — Generated content lives within Talent profiles and Projects. A "Library" provides global search.
3. **Models move to Admin** — Creators never see safetensors files.
4. **Workflows move to Admin** — Developer/operator reference only.
5. **Analytics splits** — Content performance stays in Publish. System costs move to Admin.

---

## 5. User Personas

### Persona 1: Creator (Primary)
**Name:** Sophia, 28  
**Role:** AI content creator / agency freelancer  
**Goals:** Produce consistent, high-quality AI influencer content for clients  
**Frustrations:** ComfyUI complexity, parameter guessing, inconsistent results  
**Needs:** "Tell me what you want and I'll figure out the technical stuff"  
**Key pages:** Brain, Projects, Talent, Publish  
**Mode:** Brain Mode (80%), Studio Mode (20%)

### Persona 2: Brand Manager
**Name:** Marcus, 35  
**Role:** Marketing director at a D2C fashion brand  
**Goals:** Generate campaign content featuring AI influencers wearing their products  
**Frustrations:** Wants results, not process. Doesn't want to learn AI tools.  
**Needs:** "Here's our brand guide and product photos. Make a campaign."  
**Key pages:** Brain, Projects, Publish, Analytics  
**Mode:** Brain Mode (95%), Studio Mode (5%)

### Persona 3: Technical User (Operator)
**Name:** Alex, 32  
**Role:** Platform operator / technical director at an agency  
**Goals:** Optimize GPU costs, manage model inventory, ensure system reliability  
**Frustrations:** Needs granular control, monitoring, and debugging tools  
**Needs:** "Show me what's running, what it costs, and let me tune it"  
**Key pages:** Admin, Fleet, Models, Workflows, Analytics  
**Mode:** Expert Mode (90%), Brain Mode (10%)

### Persona 4: New User (Onboarding)
**Name:** Jordan, 24  
**Role:** Creator exploring AI content for the first time  
**Goals:** Understand what's possible, create their first AI persona  
**Frustrations:** Overwhelmed by options, doesn't know where to start  
**Needs:** "Show me what this can do. Walk me through it."  
**Key pages:** Brain (exclusively during first week)  
**Mode:** Brain Mode (100%) with guided onboarding

---

## 6. User Journeys

### Journey 1: First-Run Experience (New User)

```
1. Sign up → Welcome screen with 30-second video showing capabilities
2. "What brings you here?" — Select: Content Creator / Brand / Developer
3. Based on selection, set default mode (Brain / Brain / Expert)
4. Brain greets: "Hey! I'm your AI creative director. Want me to help you create your first AI persona?"
5. Guided conversation: Name → Style → Upload reference photos → Brain auto-creates Talent
6. Brain offers: "Want to see what I can do? I'll generate a portrait of [Name] right now."
7. First generation happens → result displayed inline in chat
8. Brain suggests: "Great! You can ask me to generate more, try different styles, or start a campaign."
9. User lands on Home with their first project visible
```

### Journey 2: Create a Campaign

```
1. User (Brain Mode): "Create a summer beachwear campaign for Melissa, 5 images, Instagram-ready"
2. Brain: "I'll create this for you. Let me check Melissa's DNA... She looks great in warm lighting, 
   beach settings. I'll use Flux Dev with her identity LoRA. Estimated cost: $0.015 for 5 images."
3. Brain shows plan card with [Approve] [Modify] [Reject]
4. User: [Approve]
5. Brain generates 5 images, shows them in a grid within chat
6. Brain: "Here are your 5 images. Rate your favorites and I'll learn your preferences. 
   Want me to schedule these for Instagram this week?"
7. User picks 3 favorites → rates them → Brain stores feedback in Creative DNA
8. User: "Schedule them for Monday, Wednesday, Friday"
9. Brain creates publish schedule, shows calendar preview
10. User confirms → Campaign complete
```

### Journey 3: Train Talent LoRA

```
1. User goes to Talent → selects persona → uploads 30 photos
2. Brain (sidebar dock): "I see you uploaded training photos. Want me to train a LoRA? 
   It'll cost about $3 and take 45 minutes."
3. User: "Yes, standard quality"
4. Brain configures: 1000 steps, rank 16, Flux Dev base, polygon scheduler — user sees none of this
5. Training queued → progress shown as notification badge
6. 45 minutes later: "Training complete! Here's a sample generation with your new model."
7. Brain auto-generates 4 test images, shows quality comparison
```

### Journey 4: Generate Content (Studio Mode)

```
1. Creator switches to Studio Mode for fine control
2. Selects project → "Summer Campaign"
3. Sees canvas: Talent (Melissa) pinned left, Generation panel center, Results right
4. Types prompt in generation panel — Talent DNA auto-injected
5. Adjusts: picks resolution preset (Instagram Square), style preset (Golden Hour)
6. Generates → sees result immediately
7. Drags result to project board
8. Iterates with seed lock, slight prompt variations
```

### Journey 5: Publish Content

```
1. User opens Publish → sees timeline of scheduled posts
2. "Add Post" → Browse from Project gallery or Library
3. Selects 3 images from "Summer Campaign" project
4. Platform: Instagram → Format: Carousel
5. AI Brain suggests caption: "Based on your brand voice, here's a caption..."
6. User edits, schedules for Friday 6pm
7. Publish page shows preview of how it'll look on Instagram
```

---

## 7. Brain Interaction Flows

### Conversational Orchestration Model

The Brain is the single interface users interact with. Behind it, the Creative Team (Yoruba-inspired agents) handles specialized tasks.

```
User → Brain (Èṣù routes) → Appropriate Agent(s) → Results → Brain presents

Example:
User: "Create a luxury product shot of our new perfume on a marble surface"

Brain (Èṣù) identifies:
  - Need: Image generation
  - Subject: Product (perfume) — checks if product exists in Talent library
  - Setting: Marble surface — checks for background talent with "marble" tag
  - Style: Luxury — checks Creative DNA for luxury presets

Brain (Ọ̀ṣun) recommends:
  - Model: Flux Dev (best quality for product photography)
  - Prompt enhanced with luxury photography keywords
  - Lighting: studio, soft shadows (learned from user's preferred_lighting)

Brain (Ògún) provisions:
  - Checks if worker is running → if not, asks user permission to launch ($0.50/hr)
  - Verifies Flux Dev is loaded → if not, estimates download time

Brain presents to user:
  "I'll create a luxury product shot using Flux Dev. Your perfume will be on marble 
   with soft studio lighting. Cost: ~$0.003. [Generate] [Modify settings]"
```

### Brain Capabilities by Mode

| Mode | Brain Capabilities |
|------|-------------------|
| Creative Chat | Brainstorm, ideate, mood board creation, reference finding |
| Production | Generate images, videos, audio. Full pipeline orchestration. |
| Prompt Engineer | Optimize prompts, A/B test variations, explain what works |
| Story Assistant | Develop narratives, character arcs, episode planning |
| Script Writer | Write scripts, captions, ad copy, social content |
| Image Analyzer | Analyze uploaded images, extract style, suggest recreation |
| Admin (hidden) | System status, cost reports, troubleshooting (operator-only) |

### Proactive Brain Behaviors

The Brain doesn't just respond — it initiates:

1. **Session planning:** "What kind of session today? I'll pre-load the right models."
2. **Quality coaching:** "Your last 5 Melissa images scored 4.2/5. Want me to try a different lighting approach?"
3. **Cost awareness:** "You've spent $3.20 today. Your daily budget is $5. Want me to switch to faster/cheaper models?"
4. **Continuity:** "Last time we were working on the Tokyo campaign. Want to continue?"
5. **Learning:** "I noticed you always prefer warm color grades. I'll make that the default."

### Command Center Pattern

Instead of users navigating pages to do things, the Brain offers a **Command Center** — a quick-action palette (⌘+K style):

```
⌘+K → type action:
  "generate portrait Melissa"     → triggers generation
  "train lora alex"               → opens training with Alex selected
  "schedule post friday"          → opens publish scheduler
  "show costs this week"          → shows inline cost chart
  "switch to studio mode"         → toggles interface mode
  "launch gpu worker"             → starts provisioning
```

---

## 8. Navigation Map

### Proposed V2 Navigation

```
┌─────────────────────────────────────────┐
│ Primary Navigation (always visible)      │
├─────────────────────────────────────────┤
│ 🧠 Brain          → /brain              │
│ 📁 Projects       → /projects           │
│ 🎭 Talent         → /talent             │
│ 🎨 Create         → /create             │
│ 📚 Library        → /library            │
│ 📤 Publish        → /publish            │
├─────────────────────────────────────────┤
│ Secondary (collapsed)                    │
│ 🎬 Editor         → /editor             │
│ 🎓 Training       → /training           │
│ ⚙️ Settings       → /settings           │
├─────────────────────────────────────────┤
│ Operator (role-gated)                    │
│ 🔧 Admin          → /admin              │
└─────────────────────────────────────────┘
│ Brain Dock (always visible at bottom)    │
│ "Ask Brain anything..." + status dot     │
└─────────────────────────────────────────┘
```

### Navigation Reduction: 14 items → 9 items

**Removed from primary nav:**
- Workflows → moved to Admin
- Models → moved to Admin
- Assets → replaced by Library (global) + per-Talent media
- Production → absorbed into Projects
- Analytics → split between Publish (content) and Admin (costs)

**Added:**
- Projects (new first-class entity)
- Library (replaces Assets with AI-powered search)

---

## 9. Screen Inventory

### Current State (V1) — 19 Screens

| # | Screen | Lines of Code | Complexity |
|---|--------|---------------|-----------|
| 1 | Home | ~300 | Medium |
| 2 | Brain | ~580 | High |
| 3 | Create | ~900+ | Very High |
| 4 | Editor | ~700+ | High |
| 5 | Workflows | ~180 | Low |
| 6 | Training | ~300 | Medium |
| 7 | Talent | ~1000+ | Very High |
| 8 | Assets | ~200 | Medium |
| 9 | Models | ~400 | Medium |
| 10 | Production | ~200 | Medium |
| 11 | Publish | ~200 | Medium |
| 12 | Analytics | ~300 | Medium |
| 13 | Admin | ~400 | High |
| 14 | Admin/Fleet | ~300 | Medium |
| 15 | Admin/ISE | ~200 | Low |
| 16 | Admin/Keys | ~200 | Low |
| 17 | Admin/Knowledge | ~200 | Low |
| 18 | Admin/Downloads | ~200 | Low |
| 19 | Settings | ~200 | Low |

### Proposed V2 — 16 Screens (more focused)

| # | Screen | Key Changes |
|---|--------|-------------|
| 1 | Home | Project feed + Brain quick-start + smart suggestions |
| 2 | Brain | Enhanced: streaming, tool results inline, approval cards, context panel |
| 3 | Projects List | New: campaign/project browser with status, thumbnails |
| 4 | Project Workspace | New: all assets, shots, timeline, team, status for one project |
| 5 | Talent Library | Simplified: grid + quick preview. Detail is a slide-over, not a panel |
| 6 | Talent Profile | Redesigned: tabbed profile with DNA, media, relationships, generations |
| 7 | Create (Studio Mode) | Simplified: preset-driven, Brain suggestions, talent-first workflow |
| 8 | Editor | Kept: storyboard + video assembly (remove Quick Edit to Project) |
| 9 | Library | New: global searchable gallery with AI tagging, filters, bulk actions |
| 10 | Publish | Redesigned: content-first then calendar. Connected accounts visible. |
| 11 | Training | Simplified: preset modes (Quick/Standard/Quality) + advanced toggle |
| 12 | Settings | Expanded: preferences, team, billing, integrations |
| 13 | Admin Hub | Consolidated: service health, quick actions, navigation to sub-pages |
| 14 | Admin/Fleet | Kept: GPU management |
| 15 | Admin/Models+Workflows | Merged: model registry + workflow viewer |
| 16 | Admin/System | New: analytics, costs, keys, knowledge, ISE all as tabs |

---

## 10. Design System Recommendations

### Terminology Changes

| V1 Term | V2 Term | Reasoning |
|---------|---------|-----------|
| Worker | GPU Session | "Worker" is infrastructure jargon |
| Fleet | GPU Pool | More intuitive |
| Generation Job | Creation | User-facing term |
| CFG Scale | Creativity (slider) | Abstracted for non-technical users |
| Steps | Quality (Draft/Standard/High) | Preset-based instead of numbers |
| Seed | Variation Lock | Describes the outcome, not the mechanism |
| LoRA | Style/Identity Model | Users understand "style" |
| Checkpoint | Base Model | Slightly more intuitive |
| Inference | Generation | Standard creative AI term |
| ComfyUI Workflow | Recipe | First-class object (see Section 12) |
| Prompt Enhancement | AI Polish | Describes what Brain does to improve prompts |
| Object DNA | Smart Properties | AI-understood metadata |
| Creative DNA | Creative Profile | Per-talent learned preferences |
| Negative Prompt | Avoid (list) | What to exclude |
| ControlNet | Pose Reference / Guide Image | Describes the function |
| IP-Adapter | Style Reference | Describes the function |
| Brain Mode | Focus | "Creative Focus" / "Production Focus" |

### Visual Patterns

**Cards:** All entities (talent, projects, assets) represented as rich cards with:
- Thumbnail/avatar (primary visual)
- Title + type badge
- Status indicator (active/archived/generating)
- Quick actions on hover
- Selection state (checkbox + purple border)

**Empty States:** Always include:
- Contextual illustration
- What this area does
- Clear CTA to first action
- Brain prompt suggestion ("Ask Brain to help you get started")

**Loading:** Skeleton screens (not spinners) matching the final layout shape.

**Modals:** Use slide-over panels instead of centered modals for:
- Detail views (talent profile, job details)
- Forms (create talent, edit settings)

Centered modals only for:
- Confirmations (delete, approve)
- Quick actions (rename, move)

**Approval Cards:** Inline in Brain chat with clear cost display:
```
┌─────────────────────────────────────┐
│ ⚡ Generate 5 portraits of Melissa  │
│ Model: Flux Dev  Cost: $0.015       │
│ [Approve ✓]  [Modify]  [Reject ✕]  │
└─────────────────────────────────────┘
```

### Component Library Additions Needed

- `<RecipeCard>` — For Creative Recipes (see Section 12)
- `<ProjectCard>` — Project thumbnail with status, asset count, last modified
- `<ApprovalInline>` — In-chat approval with cost, action, and buttons
- `<TalentPicker>` — Reusable multi-select for talent across all generation flows
- `<GenerationProgress>` — Shows model loading, queue position, generation, saving
- `<BrainDock>` — Persistent bottom-bar mini Brain input available on all pages
- `<CommandPalette>` — ⌘+K quick action overlay
- `<CostBadge>` — Small badge showing estimated cost before any paid action

---

## 11. Creative Team Architecture

### The 6 Departments of AI Agents

Users interact with **one Brain**. Behind it, 6 departments handle specialized work:

#### Department 1: Intelligence (The Minds)

| Agent | Yoruba Name | Role | V1 Equivalent |
|-------|------------|------|---------------|
| Chief Strategist | Orunmila | Plans campaigns, sequences tasks, reasons about intent | Brain planner (keyword-based) |
| Knowledge Keeper | Ifa | RAG search, memory retrieval, context injection | Brain memory + embeddings |
| Communicator | Hermes/Èṣù | Routes requests, selects tools, coordinates agents | Brain module registry |

**User-visible behavior:** Brain understands context, remembers preferences, plans multi-step campaigns.

#### Department 2: Creative (The Artists)

| Agent | Yoruba Name | Role | V1 Equivalent |
|-------|------------|------|---------------|
| Creative Director | Osun (Ọ̀ṣun) | Visual quality, brand consistency, style coaching | Creative Director agent |
| Story Director | Oya | Narrative continuity, adaptive story arcs | Story Engine |
| Prompt Artist | Araye | Prompt optimization, enhancement, variation | Prompt Director dept |
| Style Director | Aso | Wardrobe, fashion, visual themes | Photography Director |
| Set Designer | Ile | Backgrounds, environments, lighting | Art Director dept |

**User-visible behavior:** High-quality generations that match talent's style. Consistent visual language across a campaign. Smart prompt enhancement.

#### Department 3: Identity (The Guardians)

| Agent | Yoruba Name | Role | V1 Equivalent |
|-------|------------|------|---------------|
| Identity Architect | Obatala | Talent DNA, LoRA management, identity consistency | Character Director |
| Memory Keeper | Yemoja | Creative DNA evolution, preference learning, relationship graph | Creative DNA + feedback |

**User-visible behavior:** Talent looks consistent across all generations. The system learns what works and improves over time.

#### Department 4: Production (The Builders)

| Agent | Yoruba Name | Role | V1 Equivalent |
|-------|------------|------|---------------|
| Production Manager | Esu | Job scheduling, queue management, pipeline orchestration | Worker Orchestrator |
| Infrastructure | Ogun (Ògún) | GPU provisioning, model loading, worker management | Connection Race, Fleet |
| Renderer | Sango (Ṣàngó) | ComfyUI dispatch, video assembly, audio stitching | Generation Engine |
| Recipe Master | Akose | Workflow DNA, parameter optimization, preset learning | Workflow selector |

**User-visible behavior:** Fast, reliable generation. Smart resource allocation. Cost-efficient.

#### Department 5: Distribution (The Messengers)

| Agent | Yoruba Name | Role | V1 Equivalent |
|-------|------------|------|---------------|
| Publisher | Aroko | Social scheduling, cross-platform publishing, format adaptation | Publishing module |
| Commerce | Aje (Ajé) | Cost tracking, billing, marketplace, ROI | Cost Intelligence |

**User-visible behavior:** One-click publishing to connected platforms. Cost visibility.

#### Department 6: Governance (The Protectors)

| Agent | Yoruba Name | Role | V1 Equivalent |
|-------|------------|------|---------------|
| Guardian | Obaluaye (Ọbalúayé) | System health, quality assurance, reliability | Provider reputation, ISE |
| Council | Egbe | Authority enforcement, approval workflows, audit | New (per AIOS architecture) |

**User-visible behavior:** The system doesn't break. Destructive actions require confirmation. Everything is auditable.

### How Departments Collaborate (Example)

**User request:** "Create a 3-post Instagram series for Melissa at the Tokyo hotel"

```
Intelligence (Orunmila): Plans 3-image series with visual progression
Intelligence (Ifa): Retrieves Melissa's Creative DNA, Tokyo hotel references
Creative (Osun): Recommends warm evening lighting, luxury aesthetic
Creative (Araye): Crafts 3 enhanced prompts with progression (arrival → room → rooftop)
Identity (Obatala): Injects Melissa's LoRA at strength 0.7, trigger words
Identity (Yemoja): Recalls user prefers golden hour, uses last successful settings
Production (Akose): Selects Flux Dev recipe (best for portraits), 1024x1024, 20 steps
Production (Ogun): Verifies worker is running, Flux Dev loaded
Production (Sango): Dispatches 3 generation jobs to ComfyUI
Distribution (Aroko): Prepares Instagram-optimized versions (1080x1080, crop hints)
Governance (Egbe): Auto-approves ($0.009 total, within daily budget)
```

**User sees:** "Here are your 3 images for the Tokyo series. Want me to schedule them?"

---

## 12. Creative Recipes

### Definition

A **Creative Recipe** is a proven combination of model + parameters + style + context that produces reliable results. Recipes are the V2 replacement for manual parameter configuration.

### Recipe Structure

```typescript
interface CreativeRecipe {
  id: string;
  name: string;                    // "Luxury Portrait — Warm Studio"
  description: string;             // Human-readable explanation
  category: RecipeCategory;        // "portrait" | "product" | "landscape" | "video" | "editorial"
  
  // What it produces
  content_type: "image" | "video" | "audio";
  aspect_ratios: string[];         // ["1:1", "4:5", "9:16"]
  
  // Technical configuration (hidden from users)
  model: string;                   // "flux-dev"
  loras: { id: string; strength: number }[];
  sampler: string;
  scheduler: string;
  cfg: number;
  steps: number;
  negative_prompt: string;
  
  // Intelligence
  quality_score: number;           // 0-5, learned from user feedback
  success_rate: number;            // Historical success percentage
  avg_generation_time: number;     // Seconds
  avg_cost: number;                // USD per generation
  times_used: number;
  
  // Metadata
  created_by: "system" | "user" | "community" | "ai_learned";
  recommended_for: string[];       // ["luxury", "fashion", "portrait"]
  compatible_talent_types: string[]; // ["model", "influencer"]
  
  // Learning
  feedback_history: { rating: number; date: string }[];
  auto_improvements: { field: string; old_value: unknown; new_value: unknown; reason: string }[];
}
```

### Recipe Categories

| Category | Example Recipes |
|----------|----------------|
| **Portrait** | Studio Headshot, Golden Hour Portrait, Editorial Beauty, Street Style |
| **Product** | Marble Surface, Lifestyle Context, Clean White, Luxury Close-up |
| **Landscape** | Cinematic Wide, Urban Night, Beach Golden Hour, Abstract Background |
| **Editorial** | Magazine Cover, Fashion Spread, Campaign Hero, Billboard |
| **Video** | Slow Motion Walk, Product Reveal, Fashion Transition, Ambient Loop |
| **Social** | Instagram Story, TikTok Hook, YouTube Thumbnail, Twitter Card |

### How Recipes Work in the UX

**Brain Mode:**
```
User: "Create a portrait of Melissa"
Brain: "I'll use the 'Luxury Portrait — Warm Studio' recipe. It has a 92% success rate 
       with your Melissa talent. Want me to proceed?"
```

**Studio Mode:**
- Recipe browser panel on the left
- Click a recipe → all parameters auto-fill
- Can override specific settings
- "Save as new recipe" for customized versions

**Learning Loop:**
```
User generates image → User rates (👍/👎 or 1-5 stars)
  → Rating stored with recipe + talent + parameters
  → After 10+ ratings: recipe quality_score updates
  → After 50+ ratings: AI suggests parameter improvements
  → Recipe evolves over time, getting better for this user
```

### System-Provided Recipes vs User Recipes

- **System:** Pre-built optimal configurations for common tasks. Updated by AI Studio team.
- **User:** Created from successful generations. "Save this as a recipe" button.
- **AI-Learned:** Automatically discovered from high-rated generations. "I noticed your best images use these settings..."
- **Community:** (Future) Shared recipes marketplace.

---

## 13. AI Automation Boundaries

### What AI Decides (No Human Input Needed)

| Decision | Agent | Reasoning |
|----------|-------|-----------|
| Model selection for a given prompt | Akose | Matches prompt content to model strengths |
| Prompt enhancement (add quality keywords) | Araye | Always improves output, reversible |
| Negative prompt injection | Araye | Standard quality safeguards |
| LoRA selection for known talent | Obatala | If talent has identity LoRA, always use it |
| Sampler/scheduler/CFG | Akose | Model-specific optimal defaults |
| Resolution based on platform target | Araye | Instagram=1080x1080, TikTok=1080x1920 |
| Memory retrieval and context injection | Ifa | Always enriches responses |
| Conversation persistence | Yemoja | Auto-saves, never loses work |
| Provider failover | Ogun | If Ollama is down, switch to OpenAI silently |
| Worker reuse (model already loaded) | Ogun | Cost optimization, no downside |

### What AI Recommends (Human Approves)

| Decision | Agent | When to Ask |
|----------|-------|-------------|
| Launch GPU worker | Ogun | Always (costs money: $0.50+/hr) |
| Generate content (when cost > $0.01) | Sango | Budget-dependent threshold |
| Start LoRA training | Ogun | Always (costs $3-10, takes 30-60 min) |
| Publish to social platform | Aroko | Always (public action, not reversible) |
| Modify Creative DNA | Yemoja | When changes are significant |
| Switch to expensive model (GPT-4, Claude) | Hermes | When cost > $0.01 per query |
| Batch generation (5+ images) | Sango | Aggregated cost check |

### What AI Never Decides (Human-Only)

| Decision | Why |
|----------|-----|
| Delete talent or projects | Destructive, not reversible |
| Delete trained models | Expensive to recreate |
| Spend over daily budget | Financial boundary |
| Voice cloning (consent required) | Legal/ethical requirement |
| Publish timing (specific date/time) | Business decision |
| Brand guidelines | Creative ownership |
| Which generations to keep vs discard | Taste is subjective |
| Team access and permissions | Security decision |

### Configurable Thresholds (Settings Page)

```
Auto-approve generation: [✓] (up to $_____ per generation)  [$0.05 ▼]
Auto-approve batch:      [✓] (up to $_____ per batch)      [$0.50 ▼]
Auto-approve training:   [ ] (always ask)
Auto-approve publishing: [ ] (always ask)
Auto-approve GPU launch: [ ] (always ask)
Daily spend limit:       [$10.00]
Monthly spend limit:     [$100.00]
```

---

## 14. Migration Strategy

### Principle: Additive Evolution, Never Destructive

V2 is built alongside V1. Users can opt-in to V2 features progressively.

### Phase A: Foundation (Weeks 1-3)

**Backend:**
- AIOS Gateway deployed at `/aios/v1/` (already started — `backend/aios/gateway.py`)
- Existing `/api/v1/` endpoints continue working unchanged
- Add `projects` table and API endpoints
- Add `creative_recipes` table and seeded recipes

**Frontend:**
- Add `BrainDock` component to all pages (mini input bar at bottom)
- Add `CommandPalette` (⌘+K) overlay
- No navigation changes yet

**Impact:** Zero disruption. Additive features only.

### Phase B: Brain Enhancement (Weeks 3-5)

**Backend:**
- AIOS streaming chat endpoint (`/aios/v1/chat` with SSE)
- Agent Council initial deployment (Èṣù, Orunmila, Ògún)
- Recipe-based workflow configuration

**Frontend:**
- Upgrade Brain page: streaming responses, tool results inline
- Add Recipe browser to Create page sidebar
- Project creation flow (basic)

**Impact:** Brain becomes noticeably smarter. Create page gets presets.

### Phase C: Navigation Restructure (Weeks 5-7)

**Frontend:**
- Add `/projects` and `/library` pages
- Move Workflows to Admin
- Move Models to Admin
- Replace Assets nav with Library
- Merge Production into Projects
- Update sidebar navigation

**Backend:**
- Project-based job grouping
- Library search with AI tagging
- Asset-to-Talent linking API

**Impact:** Navigation simplifies. Users alerted to changes via in-app banner.

### Phase D: Mode System (Weeks 7-10)

**Frontend:**
- Implement mode toggle (Brain/Studio/Expert)
- Brain Mode: full-screen chat with contextual panels
- Studio Mode: visual workspace with talent pinning
- Expert Mode: unlocks all V1 technical controls

**Backend:**
- Per-user mode preference storage
- Mode-specific API response formats (simplified vs full)

**Impact:** Major UX transformation. Old pages still accessible in Expert Mode.

### Phase E: Creative Team & Recipes (Weeks 10-14)

**Backend:**
- Full Agent Council deployment (9 agents)
- Recipe learning from feedback
- Automatic Recipe generation from high-rated outputs
- Workflow DNA table and population

**Frontend:**
- Recipe cards in Studio Mode
- Feedback UI (rate generations, mark favorites)
- Brain shows which agents contributed to results
- Learning dashboard ("Your recipes are improving")

**Impact:** Product differentiator deployed. AI becomes proactively helpful.

### Backward Compatibility Guarantees

1. All V1 API endpoints remain operational for 6 months after V2 launch
2. All V1 pages remain accessible via Expert Mode
3. No data loss — all existing talent, assets, models, jobs preserved
4. No forced migration — users can stay in Expert Mode indefinitely
5. Database changes are additive only (new tables, new columns)

### Feature Flags

```
FEATURE_V2_BRAIN_STREAMING=true     // SSE streaming in Brain chat
FEATURE_V2_PROJECTS=true            // Projects system
FEATURE_V2_RECIPES=true             // Creative Recipes
FEATURE_V2_LIBRARY=true             // Global Library (replaces Assets)
FEATURE_V2_MODES=true               // Brain/Studio/Expert toggle
FEATURE_V2_AGENT_COUNCIL=true       // Full multi-agent orchestration
FEATURE_V2_ONBOARDING=true          // First-run experience
FEATURE_V2_NAV=true                 // New navigation structure
```

---

## 15. Risk Analysis

### Critical Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Brain can't actually orchestrate complex multi-step campaigns | High | Critical | Start with simple orchestration (single generation), expand incrementally. Fallback to manual mode always available. |
| LLM quality insufficient for reliable planning | Medium | High | Keep keyword planner as fallback. Use structured output parsing. Test extensively with llama3.1:8b before shipping. |
| Recipe learning produces bad recommendations | Medium | Medium | Always show recipe quality score. User can override. Manual recipes always available. |
| Navigation change confuses existing users | Medium | Medium | In-app migration guide. Expert Mode preserves V1 layout. Feature flags for gradual rollout. |
| Performance regression from agent orchestration | Medium | Medium | Agent calls are async. Show progress. Cache decisions. 3-second maximum for planning step. |
| Multi-tenant recipe isolation | Low | Critical | All recipes scoped by org_id. RLS policies on recipe tables. Never show cross-tenant data. |
| Over-automation frustrates power users | Medium | Medium | Expert Mode exists. All automation is configurable/disableable in Settings. |

### Backward Compatibility Concerns

| Concern | Status | Resolution |
|---------|--------|-----------|
| `/api/v1/brain/chat` consumers | Active | Gateway wraps existing endpoint. Both work simultaneously. |
| Frontend hardcoded to specific API shapes | Active | V2 responses include V1-compatible fields. Gradual migration. |
| localStorage state (sessions, favorites, collections) | Active | Migrate to Supabase on first V2 login. Keep localStorage as cache. |
| ComfyUI workflow JSON format | Active | No changes needed. Recipes are a layer above workflows. |
| GPU worker architecture | Active | No changes. AIOS adds intelligence layer above existing worker management. |
| Brain conversation history | Active | Existing `brain_conversations` table preserved. New sessions use enhanced schema. |

### What Could Go Wrong (Worst Cases)

1. **Brain hallucinates costly actions** → Governance layer blocks. All costs require explicit approval above threshold.
2. **Agent Council deadlocks** → 5-second timeout on all agent reasoning. Fallback to simple rule-based logic.
3. **Recipe learning degrades quality** → Quality score has minimum threshold. System recipes can't be modified by learning.
4. **New navigation loses users** → Analytics on page views pre/post. Revert flag available. A/B test with subset.
5. **Performance drop from agent orchestration** → All agent work is async with streaming. User never waits for all agents to complete.

---

## 16. Phased Implementation Roadmap

### Phase 1: Brain Enhancement + Foundation (Weeks 1-4)
**Lead:** Backend + AI/ML  
**Theme:** "Make the Brain actually smart"

- [ ] AIOS Gateway streaming endpoint (SSE chat)
- [ ] Token streaming from Ollama/OpenAI to frontend
- [ ] Session persistence migration (localStorage → Supabase)
- [ ] Creative Recipes table + 20 seeded system recipes
- [ ] Projects table + basic CRUD endpoints
- [ ] BrainDock component (mini-chat on all pages)
- [ ] Command Palette (⌘+K) component
- [ ] Brain page streaming UI update

**Milestone:** Brain streams responses in real-time. Users can access Brain from any page.

### Phase 2: Recipe-Driven Creation (Weeks 4-7)
**Lead:** Frontend + AI/ML  
**Theme:** "Parameters disappear behind intelligent defaults"

- [ ] Recipe browser component (cards with quality scores)
- [ ] Recipe-based generation flow (select recipe → generate)
- [ ] Auto-configuration via AIOS workflow intelligence
- [ ] Feedback UI (rate generations 1-5 stars)
- [ ] Recipe learning pipeline (aggregate ratings → update scores)
- [ ] Simplified Create page (recipe picker replaces raw parameters)
- [ ] Talent-first generation flow ("Generate as [Talent]")

**Milestone:** Users can generate without touching any technical parameters.

### Phase 3: Projects & Organization (Weeks 7-10)
**Lead:** Full Stack  
**Theme:** "Everything belongs to a project"

- [ ] Projects page (list, create, archive)
- [ ] Project workspace page (assets, shots, timeline, status)
- [ ] Job-to-project association
- [ ] Asset-to-talent linking
- [ ] Library page (global search with AI tagging)
- [ ] Navigation restructure (add Projects, Library; move Workflows, Models to Admin)
- [ ] Onboarding flow (first-run guided experience)

**Milestone:** Users organize work in campaigns/projects. Navigation is simplified.

### Phase 4: Mode System + Agent Council (Weeks 10-14)
**Lead:** Frontend + Backend + AI/ML  
**Theme:** "The Brain has a team"

- [ ] Mode toggle component (Brain/Studio/Expert)
- [ ] Brain Mode: full-screen conversational interface
- [ ] Studio Mode: visual workspace with talent pinning
- [ ] Expert Mode: V1 controls preserved
- [ ] Agent Council deployment (3 initial: Èṣù, Orunmila, Ògún)
- [ ] Decision traceability logging
- [ ] Approval workflow enhancement (cost display, batch approvals)
- [ ] Proactive Brain behaviors (session planning, cost alerts)

**Milestone:** Three distinct experience modes serve three user types. AI orchestration is visible.

### Phase 5: Distribution & Polish (Weeks 14-18)
**Lead:** Full Stack + UI/UX  
**Theme:** "Ship the product"

- [ ] Publish page redesign (content-first, connected accounts)
- [ ] Settings page expansion (preferences, team, thresholds)
- [ ] Mobile responsive pass (all pages)
- [ ] Accessibility audit (WCAG 2.1 AA)
- [ ] Performance optimization (code splitting, lazy loading)
- [ ] Error boundaries on all async operations
- [ ] Analytics split (creator analytics in Publish, system analytics in Admin)
- [ ] MCP server for external AI integration

**Milestone:** Production-ready V2 with complete feature parity and UX improvement.

### Phase 6: Scale & Learn (Weeks 18+)
**Lead:** All  
**Theme:** "The system gets smarter over time"

- [ ] Full 9-agent Council deployment
- [ ] Community recipes marketplace
- [ ] Advanced recipe learning (auto-generate from patterns)
- [ ] Multi-worker session orchestration
- [ ] Voice Sequencer (long-form audio)
- [ ] Vercel deployment parity
- [ ] Billing integration (Stripe)
- [ ] Team/org management

**Milestone:** Self-improving platform that gets better with every generation.

---

## Summary of Recommendations

### Top 5 Immediate Actions

1. **Add BrainDock to all pages** — Users should always have Brain access without navigating to `/brain`.
2. **Create 20 system recipes** — Replace raw parameter exposure with intelligent presets.
3. **Implement streaming** — Brain responses should stream token-by-token, not appear all at once.
4. **Add Projects entity** — Give users a place to organize their work beyond individual generations.
5. **Simplify Create page** — Hide Advanced by default. Lead with: Talent + Recipe + Prompt → Generate.

### Success Metrics

| Metric | Current (V1) | Target (V2) |
|--------|-------------|-------------|
| Time to first generation (new user) | 5+ minutes (if they figure it out) | 60 seconds (Brain-guided) |
| Parameters configured before generation | 5-10 (model, steps, cfg, size, negative) | 0-1 (just the prompt) |
| Pages visited for a complete workflow | 3-4 (Create → Assets → Publish) | 1 (Brain orchestrates) |
| User needs to know "CFG" | Yes | Never |
| Generation success rate | Unknown | 90%+ (recipes are proven) |
| Cost visibility before action | Sometimes | Always |

### The Core Insight

**V1 is built around capabilities** (what the system can do).  
**V2 is built around intentions** (what the user wants to achieve).

The shift from "here are your tools" to "tell me what you want" is the fundamental transformation. The Brain becomes the product. Everything else supports it.

---

*End of V2 UX Redesign Analysis*
