# AI Studio V2 — Complete Page Rendering Prompts (ChatGPT)

> Use these prompts to generate full-page mockup images in ChatGPT.
> Every page is designed with design thinking: reduce, reduce, reduce.
> Human-centered: users think in goals, not technical parameters.

## Design System Constants

All pages share:
- Background: dark navy (#0a0a1a)
- Accent: purple (#7c3aed)
- Cards: #12122a with subtle border (white/6% opacity)
- Text: white (headings), gray-400 (body), gray-600 (muted)
- Font: Inter (clean sans-serif)
- Corners: rounded-xl (12px)
- No technical ML terminology visible
- Cost always visible before any paid action
- Feedback (👍/👎) on every AI output

---

## 1. Home Page — "What would you like to create today?"

```
Create a full-page dark-theme SaaS dashboard mockup for an AI Creative Operating System called "AI Studio".

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR (200px, fixed):
- Logo: Purple brain icon + "AI STUDIO" text
- Nav items (small icons + labels, vertical):
  Home (highlighted purple), Brain, Projects, Studio, Training, Talent, Library, Publish, Admin
- Bottom: user avatar "Gary" + "Studio Owner" label

TOP BAR:
- Search bar: "Search projects, assets, talent..." with ⌘K shortcut badge
- Bell icon (notification alerts)
- Chat icon (link to Brain)
- Purple "Quick Create" button

MAIN CONTENT:
1. BRAIN HERO CARD (full width, purple gradient border, glass effect):
   - Brain icon (🧠) + "Ask your AI Creative Director"
   - "Describe what you want to create. The Brain handles the rest."
   - Purple "Open Brain" button
   - Below: 5 clickable suggestion pills: "Create a luxury campaign", "Generate product photos", "Train a new talent", "Animate these images", "Write a script"

2. QUICK ACTIONS ROW (4 buttons):
   - "Create Image" (purple solid), "Manage Talent", "Train LoRA", "Publish Content"

3. METRICS ROW (6 small cards, single row):
   - Active Projects: 3
   - Jobs: 47 (2 running)
   - GPU Spend: $3.20 today
   - Talent: 8 personas
   - Services: 6/9 online
   - Worker: Online (Tesla V100)

4. THREE COLUMN GRID:
   Left: "Active Productions" — list of running/queued jobs with icons
   Center: "Jobs Overview" — donut chart (completed/running/queued/failed)
   Right: "AI Brain Suggestions" — smart tips from the system

BOTTOM: Floating "Ask Brain anything..." pill bar (BrainDock)

Style: Premium SaaS like Linear × Midjourney. Dark, spacious, no clutter. Purple accents on interactive elements.
```

---

## 2. Brain Page — "Your AI Creative Director"

```
Create a full-page dark-theme AI chat interface for a creative production platform.

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR: Same nav as above (Brain highlighted)

LEFT PANEL (280px): "Conversations"
- Search input at top
- List of past conversations with timestamps:
  "Tokyo Campaign" (2h ago)
  "Product Shoot Planning" (yesterday)
  "Melissa LoRA Training" (3 days ago)
- "+ New Conversation" button at bottom

MAIN CHAT AREA:
- Small mode pills at very top (subtle, not prominent): Creative · Prompt · Story · Production
- Chat messages:
  - User: "Create a 5-image luxury campaign for Melissa in Tokyo at night"
  - AI (with purple avatar): Shows a STORYBOARD CARD inline:
    - 5 image thumbnails in a horizontal filmstrip
    - Each labeled: "Shot 1: Shibuya Crossing", "Shot 2: Neon Alley", etc.
    - Progress bar: "3/5 generated"
    - Buttons: [Generate All] [Modify] [Add to Project]
  - Below storyboard: "I've planned 5 shots with warm neon lighting to match Melissa's style. Shall I generate them all? Estimated cost: $0.015"
  - APPROVAL CARD: purple border, shows cost "$0.015", buttons [Approve ✓] [Modify] [Reject ✕]

- At bottom of chat: AI is currently responding with "Thinking..." indicator:
  - Purple brain avatar
  - "Thinking" text with 3 bouncing purple dots
  - Subtle text: "Planning campaign shots..."

BOTTOM: Wide chat input: "What would you like to create?" with Send button + attachment icon

Style: Clean chat like Claude/ChatGPT but with inline creative tools (storyboards, approval cards, image results). Dark theme, purple accents on AI elements.
```

---

## 3. Projects Page — "Organize your creative work"

```
Create a full-page dark-theme project management view for an AI creative platform.

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR: Same nav (Projects highlighted)

TOP: "Projects" heading + "New Project" purple button + search bar + filter pills (All, Active, Archived)

MAIN: Grid of project cards (3 columns):

Card 1:
- Small color bar at top (purple)
- Title: "Tokyo Luxury Campaign"
- Subtitle: "campaign"
- Stats: "12 assets • 24 generated • $1.40 spent"
- Tags: [luxury] [fashion] [tokyo]
- Footer: "Jul 11" + "Open in Brain →" link
- Archive icon on hover (subtle)

Card 2:
- Color bar (blue)
- Title: "Product Photography — Q3"
- Subtitle: "product"
- Stats: "8 assets • 15 generated • $0.80 spent"
- Tags: [product] [ecommerce]

Card 3:
- Color bar (amber)
- Title: "Melissa Training Set"
- Subtitle: "personal"
- Stats: "32 assets • 0 generated"

Card 4: DASHED BORDER "+" card
- "New Project"
- "Campaign, collection, or story"

Style: Clean project cards like Notion/Linear. Visual color coding. No technical details — just creative work organization.
```

---

## 4. Studio (Create) Page — "Talent + Recipe + Prompt → Generate"

```
Create a full-page dark-theme AI image generation interface. Human-centered — no technical ML parameters visible.

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR: Same nav (Studio highlighted)

TOP: Tab bar — Image (active) | Video | Audio

MAIN GENERATION PANEL:
- Card with subtle border:
  - Label: "Quick Generate"
  - Subtitle: "Describe what you want — AI handles the rest."
  
  ROW 1 — Talent + Recipe:
  - Left dropdown: "Generate as talent (optional)" → "Melissa Chen" selected with small avatar
  - Right dropdown: "Recipe" → "Magazine Cover ★4.8" selected
  
  ROW 2 — Prompt:
  - Large text input: "Melissa in a luxury Tokyo penthouse, evening golden hour lighting, editorial fashion photography"
  - Star icon to save as favorite
  
  ROW 3 — Model + Generate:
  - Model dropdown: "Flux 2 Klein ✓" (with checkmark = loaded)
  - Purple "Generate ~$0.003" button with sparkle icon
  
  BELOW: "AI Brain Suggestions" — 3 smart pills:
  - "Add 'shot on 85mm lens' for sharper focus"
  - "Your best results use 'soft rim lighting'"
  - "Melissa's LoRA works best with 'ohwx woman' trigger"

RESULT AREA (right side or below):
- Generated image (luxurious portrait)
- Below image: "10.3s • studio_sdxl_00001.png"
- [Saved ✓] [Open Folder] [Download] buttons
- Cost: "$0.000217"
- FEEDBACK: 👍 👎 buttons — "Rate this to help the AI learn"

Style: The generation flow is 3 steps: WHO (talent) + HOW (recipe) + WHAT (prompt) → Generate. No CFG, no steps, no sampler, no scheduler visible. Technical controls hidden behind "Advanced ▼" toggle.
```

---

## 5. Talent Page — "Your AI cast"

```
Create a full-page dark-theme talent management page for an AI creative platform. Think of it as an intelligent contact manager for AI personas.

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR: Same nav (Talent highlighted)

TOP: "Talent" heading + "Create Talent" purple button + search + 3 filter pills: People | Products | Locations

MAIN: Grid of talent cards (3-4 columns):

Card 1:
- Large square portrait (AI-generated face of a woman)
- Name: "Melissa Chen"
- Badge: "AI Model" (purple pill)
- Readiness: green dot "Ready" (has LoRA trained)
- Stat: "142 generations • 4.7★ quality"

Card 2:
- Portrait of a man
- Name: "Alex Rivera"  
- Badge: "Influencer" (blue pill)
- Readiness: amber dot "Training needed"
- Stat: "23 generations • New"

Card 3:
- Product photo (perfume bottle)
- Name: "Noir Perfume"
- Badge: "Product" (teal pill)
- Readiness: green dot "Ready"
- Stat: "45 product shots"

Card 4:
- Background photo (Tokyo skyline)
- Name: "Tokyo Night"
- Badge: "Location" (amber pill)
- Readiness: green dot "Ready"

SELECTED CARD shows slide-over panel (right side):
- Full profile with tabs: DNA | Media | Wardrobe | Voice | History
- Big purple button: "Generate as Melissa"
- DNA tab shows: preferred lighting, color palette, best angles, avoid list
- Visual style swatches

Style: Like a talent agency portfolio. People-focused, visual, no technical details. Each talent is a "person" (or product/location) with a creative profile.
```

---

## 6. Library (Assets) — "Find anything with AI search"

```
Create a full-page dark-theme AI-powered media library for a creative production platform.

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR: Same nav (Library highlighted)

TOP: Large AI search bar (full width):
- Input: "Find images of Melissa at the beach with gold jewelry..."
- Brain icon indicating AI-powered search
- Below: Active filter chips that appeared: [Melissa ×] [Beach ×] [Gold ×] [Images only]

MAIN: Masonry grid of images (Pinterest-style, 4 columns):
- Various AI-generated images (portraits, products, landscapes)
- Each image has hover overlay showing:
  - Talent name, Project, Date, Rating stars
  - Quick actions: ★ Favorite, Download, Add to Project
- Some items have video play icons
- Star ratings visible on corner of thumbnails

RIGHT PANEL (when item selected):
- Large preview of selected image
- Metadata: Created Jul 11, Project: "Tokyo Campaign", Talent: Melissa
- Relationships: "Also in: Summer Collection, Instagram Feed"
- Recipe used: "Magazine Cover ★4.8"
- Actions: [Download] [Add to Project] [Publish] [Delete]
- Feedback: ★★★★☆ (4/5 rated)

BOTTOM: "Showing 47 results" + infinite scroll indicator

Style: Like Unsplash/Pinterest but dark theme. Visual-first, AI-searchable. No folders, no file paths — just semantic relationships.
```

---

## 7. Training Page — "Teach your AI talent"

```
Create a full-page dark-theme LoRA training page with human-friendly preset system.

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR: Same nav (Training highlighted)

TOP: "Train Talent" heading with talent avatar (Melissa) + "32 training images ready"

MAIN (centered, max-width 800px):

STEP INDICATOR: ● ● ○ (step 2 of 3)

QUALITY PRESET CARDS (3 columns, most prominent element):
- "Quick" card: "15 min • $1.50 • Good for testing" — [Fast] badge
- "Standard" card (SELECTED, purple border): "45 min • $3.00 • Recommended" — [Best] badge  
- "Quality" card: "2 hrs • $8.00 • Maximum detail" — [Pro] badge

TRAINING IMAGES PREVIEW:
- 4x4 grid of small thumbnails (training photos)
- "+ Add more images" button
- "32 images uploaded" count

BIG ACTION BUTTON:
- Purple: "Start Training — $3.00 estimated"
- Cost is clear and prominent

COLLAPSED: "Advanced Options ▼" (hidden by default, contains steps/rank/optimizer for power users)

ACTIVE TRAINING (if running):
- Progress card: "Training in progress..."
- Progress bar: 67% complete
- ETA: "~15 min remaining"
- Cost so far: "$2.01"
- [Cancel] button

Style: Like a checkout flow — one clear action per step. No scary ML parameters visible. Cost always prominent.
```

---

## 8. Publish Page — "Content first, calendar second"

```
Create a full-page dark-theme social media publishing hub. Content-first design (not calendar-first).

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR: Same nav (Publish highlighted)

TOP: "Publishing Hub" + "Schedule Post" purple button

CONNECTED PLATFORMS ROW:
- Instagram ✓ (green dot), TikTok ✓, YouTube (gray "connect"), Pinterest (gray "connect")

MAIN — TWO COLUMNS:

LEFT (65%): "Ready to Publish" — Content queue:
- Each item is a card with:
  - Thumbnail (generated image/video)
  - Platform icon (Instagram)
  - Caption preview: "Golden hour in Tokyo..."
  - Scheduled: "Thu Jul 17, 6:00 PM"
  - Status pill: "Scheduled" (green) or "Draft" (gray)
  - Drag handle for reordering

RIGHT (35%): Monthly calendar
- Small monthly calendar with colored dots on dates with content
- Today highlighted

BOTTOM SECTION: "AI Suggestions"
- "Melissa's Tokyo images perform well on Thursdays at 6pm" 
- "Your audience engages most with carousel posts"
- "Optimal posting frequency: 3x per week"
- [Apply Suggestions] button

Style: Like Buffer/Later but with AI recommendations built in. Content thumbnails are prominent. Calendar is secondary. AI suggests timing.
```

---

## 9. Admin Page — "Operator control room"

```
Create a full-page dark-theme admin panel for a GPU cloud creative platform.

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR: Same nav (Admin highlighted)

TOP: "Admin — System Health" + all-green status dots (Supabase ✓, B2 ✓, Ollama ✓, Vast.ai ✓, RunPod ✓)

MAIN — Dashboard grid:

ROW 1 (3 cards):
- GPU Worker: "Tesla V100 • Running • $0.065/hr • 4.2hrs" + [Stop] [Pause] buttons
- GPU Balance: "$9.95" with breakdown "V: $9.95 · R: $0.00"  
- Provider: "RunPod (recommended)" with toggle to switch + note "Vast.ai available for cost savings. Load times may vary."

ROW 2 (3 cards):
- Cost Today: "$3.20 / $10 budget" with progress bar
- Models: "SDXL Turbo loaded • Flux 2 Dev (B2 cached)" + [Manage Models] link
- Queue: "0 queued • 47 completed • 2 failed"

ROW 3: Service Connection Cards (grid):
- Each service: name, status dot (green/red/amber), response time, [Toggle] switch
- Supabase 119ms ✓, Backblaze B2 0ms ✓, Ollama 847ms ✓, ComfyUI ✓, ElevenLabs ⚠️

BOTTOM:
- Sub-page links: Fleet | Models | Workflows | Keys | Knowledge | System
- "Learning Stats: 47 feedback entries, 3 patterns learned across 2 agents"

Style: Dense data dashboard like Grafana but cleaner. For operators who need to see everything at a glance. Technical language is OK here — this page IS for technical users.
```

---

## 10. Settings Page — "Your preferences"

```
Create a full-page dark-theme settings page with automation preferences.

Background: #0a0a1a. Purple accent: #7c3aed.

LEFT SIDEBAR: Same nav (Settings — gear icon in user section)

LEFT TAB NAVIGATION (vertical): Profile | Preferences | Connections | Team | Billing

"PREFERENCES" TAB ACTIVE:

Section 1 — AI Automation:
- "Auto-approve generation up to: [$0.05 ▼]"
- "Auto-approve GPU launch: [Off toggle]"  
- "Daily budget limit: [$10.00]"
- "Monthly budget limit: [$100.00]"

Section 2 — Default Creative Settings:
- "Preferred recipe: [Auto ▼]"
- "Default format: [Instagram Square ▼]"
- "Always use talent LoRA when available: [On ✓]"

Section 3 — Brain Preferences:
- "Default mode: [Creative ▼]"
- "Show agent decisions: [Off toggle]" (for transparency/debug)
- "LLM Provider: [GPU Ollama ▼]" with status "(connected ✓)"

Section 4 — Notifications:
- "Training complete: [Push + Email]"
- "Generation ready: [Push only]"
- "Budget alert at 80%: [On ✓]"
- "Weekly learning report: [Email]"

Style: Clean settings like Stripe/Linear. Grouped sections, clear labels, toggle switches. Every setting has a human-friendly description.
```

---

## Navigation Bar Analysis (Final Recommendation)

Current (10 items) → Recommended (8 items):

```
REMOVE:
- Editor → merge storyboard into Projects, quick edit into Studio
- Analytics → merge into Admin as a tab

RENAME:
- Create → Studio (professional creative workspace, not "create a thing")
- Assets → Library (semantic search, not file management)

FINAL NAV:
  Home          → Dashboard + Brain hero
  Brain         → THE product (conversational AI creative director)
  Projects      → Organize campaigns (includes storyboard)
  Studio        → Manual generation (talent + recipe + prompt)
  Training      → Train LoRAs (preset-based)
  Talent        → AI cast (people, products, locations)
  Library       → Find anything (AI search)
  Publish       → Distribute content
  Admin         → Operator controls (includes fleet, analytics, settings)
```

---

## AI Brain Suggestions (Create/Studio Page)

The Brain suggestions on the Create page should be SMART — contextual to what the user is doing:

```
IF talent selected:
  "Melissa's LoRA works best with 'ohwx woman' trigger word"
  "Best results at 1024x1024 with this talent"
  "Last 5 generations scored 4.7★ with golden hour lighting"

IF recipe selected:
  "Magazine Cover works best with dramatic pose keywords"
  "This recipe auto-applies 25 steps for maximum detail"
  
IF prompt typed:
  "Add 'shot on 85mm lens' for sharper focus"
  "Consider adding 'soft rim lighting' — your top-rated results use it"
  "Avoid 'realistic' keyword with Flux — it's already photorealistic"

IF no context:
  "Try: 'luxury editorial portrait of [talent name]'"
  "Tip: Pick a recipe first — it sets optimal params automatically"
  "Your most successful prompts start with the subject"
```

These come from the Araye (Prompt Artist) agent + Akose (Recipe Master) agent learning from the user's feedback history.
