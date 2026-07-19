# AI Studio V2 — ChatGPT Visual Prompts

> Use these prompts with ChatGPT (DALL-E or image generation) to create UI mockup visuals for each page of AI Studio V2.

## Design Language

All prompts share this base:
- Dark navy background (#0a0a1a)
- Purple accent (#7c3aed)
- Minimal, clean, modern SaaS UI
- Dark theme with subtle glass effects
- San-serif typography (Inter)
- Rounded corners, soft shadows
- No technical jargon visible — human-friendly labels

---

## 1. Brain Page (Default Home — Conversational AI)

```
Create a modern dark-theme SaaS UI mockup for an AI Creative Operating System chat page. 
Dark navy background (#0a0a1a). Purple accents (#7c3aed).

Layout:
- Left sidebar (200px): navigation with icons (Brain, Projects, Talent, Assets, Library, Publish, Settings). Brain is highlighted in purple.
- Main area: full-screen conversational chat interface
- Chat messages alternate: user messages (right-aligned, purple bubble) and AI messages (left-aligned, dark card with subtle border)
- The AI is currently responding and shows "Thinking..." with a blinking purple dot animation
- Top of chat: a mode selector with pill buttons (Creative, Production, Story, Prompt)
- AI message includes an inline image result: a luxury fashion photo of an AI model in Tokyo
- Below the image: action buttons (Save to Project, Generate More, Publish, Rate ★★★★☆)
- Bottom: wide chat input with placeholder "What would you like to create?" and a purple Send button
- Above the input: small chips showing context (Talent: Melissa, Project: Tokyo Campaign, Budget: $0.05)

Style: Premium SaaS, like Linear meets Midjourney. Clean, spacious, no clutter.
```

---

## 2. Projects Page

```
Create a modern dark-theme SaaS UI mockup for a Projects page in an AI Creative Operating System.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar with navigation (Brain, Projects highlighted, Talent, Assets, Library, Publish, Settings)
- Top bar: "Projects" heading + "New Project" purple button + search bar
- Main area: grid of project cards (3 columns)
- Each card shows:
  - Thumbnail mosaic (4 small generated images in a 2x2 grid)
  - Project name: "Tokyo Luxury Campaign"
  - Status badge: "In Progress" (amber) or "Complete" (green)
  - Talent avatar(s) pinned (small circles)
  - "12 assets • 3 videos • Last edited 2h ago"
  - Subtle progress bar at bottom
- One card is a "New Project" card with a dashed border and + icon
- Top right: filter pills (All, Active, Archived) and view toggle (Grid/List)

Style: Clean cards like Notion or Linear project views. Visual thumbnails give immediate context.
```

---

## 3. Brain — Storyboard Mode (Chat-Driven)

```
Create a modern dark-theme SaaS UI mockup showing an AI storyboard creation flow within a chat interface.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left: navigation sidebar
- Main: conversation between user and AI Brain
- User message: "Create a 5-shot storyboard for Melissa walking through Tokyo at night"
- AI response: A visual storyboard card showing 5 shots in a horizontal filmstrip:
  - Shot 1: "Melissa arrives at Shibuya crossing" (with generated thumbnail)
  - Shot 2: "Close-up, neon reflections on her face" (with generated thumbnail)
  - Shot 3: "Walking through narrow alley, lanterns above" (generating... spinner)
  - Shot 4: "Rooftop bar, city skyline behind" (queued, grey placeholder)
  - Shot 5: "Final pose, Tokyo Tower in background" (queued, grey placeholder)
- Below the storyboard: action buttons: [Regenerate Shot 2] [Add Shot] [Generate All] [Create Video]
- A progress bar showing "3/5 shots generated"
- Bottom: chat input for refinement ("Make shot 3 more cinematic")

Style: The storyboard feels like a film planning tool embedded in a chat. Visual and creative, not technical.
```

---

## 4. Storyboard Editor (Manual Mode)

```
Create a modern dark-theme SaaS UI mockup for a visual storyboard editor.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar: navigation
- Top bar: "Storyboard: Tokyo Night Walk" + Back to Project + Export
- Main area: horizontal timeline of shots (like a film strip)
  - Each shot is a card with: thumbnail, shot number, brief description, duration
  - Drag handles for reordering
  - + button between shots to add new shot
- Selected shot expands below into a detail panel:
  - Large preview image (generated)
  - Prompt used (editable)
  - Duration: 4 seconds
  - Transition: Crossfade
  - Camera: Slow zoom in
  - Actions: [Regenerate] [Replace Image] [Edit Prompt] [Delete]
- Right panel: "Video Assembly"
  - Total duration: 24 seconds
  - Music: "Tokyo Ambient Night" (audio waveform)
  - [Assemble Video] purple button
  - [Add to Movie Timeline] button

Style: Like a simplified DaVinci Resolve meets Canva. Visual, drag-and-drop, no code.
```

---

## 5. Talent Page

```
Create a modern dark-theme SaaS UI mockup for a Talent management page in an AI Creative Operating System.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar with navigation (Talent highlighted)
- Top: "Talent" heading + "Create Talent" purple button + search + filter pills (People, Products, Wardrobe, Locations)
- Main: grid of talent cards (3-4 columns)
- Each card shows:
  - Large portrait/photo (AI-generated face or product shot)
  - Name: "Melissa Chen"
  - Type badge: "AI Model" (purple) or "Product" (blue)
  - Readiness indicator: green circle "Ready" (has LoRA) or amber "Training needed"
  - Small stat: "142 generations • 4.7★ quality"
- One card is selected (purple border glow) showing a slide-over panel on the right:
  - Full profile: name, description, style tags
  - "Generate as Melissa" big purple button
  - Tabs: DNA | Media | Wardrobe | Voice | Relationships | History
  - DNA tab showing: preferred lighting, color palette, best angles, avoid list

Style: Like a talent agency portfolio. Visual, people-focused, no technical details visible.
```

---

## 6. Create Page (Studio Mode — Simplified)

```
Create a modern dark-theme SaaS UI mockup for a simplified AI image generation page.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar with navigation (Create highlighted)
- Main area split: Left 60% generation, Right 40% results
- Left panel:
  - Top: Talent selector (avatar + name: "Melissa Chen ✓")
  - Below: Recipe selector (card: "Luxury Portrait — Warm Studio" with quality score 4.8★)
  - Center: Large prompt text area with placeholder "Describe your creative vision..."
  - Below prompt: Quick options row (Style: Editorial | Mood: Warm | Format: Instagram Square)
  - NO technical parameters visible (no CFG, steps, sampler)
  - Big purple button: "Generate" with cost badge "$0.003"
- Right panel: Results gallery
  - 2x2 grid of recent generations
  - Each has: image, quick actions (★ Favorite, Save to Project, Download, Regenerate)
  - Top of panel: "Recent Creations" + filter
- Bottom bar: "Powered by Flux Dev • Recipe: Luxury Portrait v3" (subtle, informational)

Style: Clean, visual, creative-focused. Like Midjourney's generation UX but more structured. No ML terminology.
```

---

## 7. Library (Global Asset Search)

```
Create a modern dark-theme SaaS UI mockup for an AI-powered media library.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar with navigation (Library highlighted)
- Top bar: Large search input with AI icon: "Search: beach, Melissa, luxury, golden hour..."
- Below search: Smart filter chips that appeared based on search: [Melissa ×] [Beach ×] [Golden Hour ×] [Images] [Videos]
- Main: Masonry grid of images and videos (Pinterest-style layout)
  - Each item shows: thumbnail, hover overlay with (Talent, Project, Date, Rating)
  - Some items have a small play icon (videos) or sound wave (audio)
  - Star ratings visible on thumbnails
- Right sidebar (collapsible): "Asset Details" when item selected
  - Large preview
  - Metadata: created date, project, talent, recipe used
  - Relationships: "Also appears in: Tokyo Campaign, Instagram Feed"
  - Actions: [Download] [Add to Project] [Publish] [Delete]
- Bottom: pagination or infinite scroll indicator

Style: Like Unsplash meets Pinterest but dark theme. Visual-first, AI-searchable.
```

---

## 8. Publish Hub

```
Create a modern dark-theme SaaS UI mockup for a social media publishing hub.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar with navigation (Publish highlighted)
- Top: "Publishing Hub" heading + "Schedule Post" purple button
- Below: Connected platforms row (Instagram ✓ green, TikTok ✓ green, YouTube • connect, Pinterest • connect)
- Main area split:
  - Left 65%: Content queue (vertical list of scheduled posts)
    - Each post card: thumbnail, platform icon, caption preview, scheduled time, status (Scheduled/Published/Draft)
    - Drag handles for reordering
  - Right 35%: Calendar view (monthly, dots on days with scheduled content)
- Below content queue: "Content Suggestions" from Brain
  - "Melissa's Tokyo images perform well on Thursdays at 6pm"
  - "Your audience engages most with carousel posts"
  - [Schedule Suggested] button

Style: Like Buffer or Later but with AI suggestions built in. Content-first, not calendar-first.
```

---

## 9. Training (Simplified)

```
Create a modern dark-theme SaaS UI mockup for a simplified AI model training page.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar with navigation (Training highlighted under secondary nav)
- Top: "Train Talent" heading with talent avatar showing who we're training
- Main area (centered, max-width 800px):
  - Step 1: Talent selected (Melissa Chen, with small avatar and "32 training images ready")
  - Step 2: Quality preset selector — 3 large cards:
    - "Quick" (15min, $1.50, good for testing)
    - "Standard" (45min, $3.00, recommended) ← highlighted with purple border
    - "Quality" (2hrs, $8.00, best results)
  - Step 3: Training images grid preview (4x4 thumbnails of uploaded photos)
  - Big purple button: "Start Training — $3.00 estimated"
  - Below: "Advanced Options ▼" collapsed toggle (hides all technical params)
- If training is active: progress card showing step, percentage, ETA, cost so far

Style: Like a checkout flow — clear steps, one decision per step, cost always visible. No scary ML parameters.
```

---

## 10. Settings

```
Create a modern dark-theme SaaS UI mockup for a settings page.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar with navigation (Settings highlighted)
- Main: Left tab navigation (Profile, Preferences, Connections, Team, Billing)
- "Preferences" tab active, showing:
  - AI Automation section:
    - "Auto-approve generation up to: [$0.05 ▼]"
    - "Auto-approve GPU launch: [Off toggle]"
    - "Daily budget limit: [$10.00]"
  - Default Creative Settings:
    - "Preferred quality: [Standard ▼]"
    - "Default format: [Instagram Square ▼]"
    - "Always use talent LoRA when available: [On toggle]"
  - Brain Preferences:
    - "Default mode: [Creative ▼]"
    - "Show agent decisions: [Off toggle]" (for transparency/debug)
    - "LLM Provider: [Local Ollama ▼] (connected ✓)"
  - Notifications:
    - "Training complete: [Push + Email]"
    - "Generation ready: [Push only]"
    - "Budget alert at 80%: [On]"

Style: Clean settings page like Stripe or Linear. Grouped sections, clear labels, toggle switches.
```

---

## 11. Admin Panel (Operators Only)

```
Create a modern dark-theme SaaS UI mockup for an admin/operator panel.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar with navigation (Admin highlighted, showing sub-items: Fleet, Models, System)
- Top: "Admin — System Health" with all-green status row (Supabase ✓, B2 ✓, Ollama ✓, Vast.ai ✓)
- Main area: Dashboard grid (2 columns):
  - GPU Worker card: "RTX 3090 • Running • $0.45/hr • 2.3hrs uptime" with [Stop] [Pause] buttons
  - Cost card: "$3.20 today / $10.00 budget" with bar chart
  - Model Inventory: "8 models cached (42GB)" with [Manage] link
  - Queue: "0 jobs queued • 47 completed today"
  - System Log: last 5 events (timestamps + messages)
  - Brain Status: "Ollama connected • llama3.1:8b loaded • 847ms avg response"
- Everything is dense, data-rich, operator-focused. This is the "control room."

Style: Like a Grafana dashboard but cleaner. Dense information for people who need it.
```

---

## 12. Onboarding (First-Run Experience)

```
Create a modern dark-theme SaaS UI mockup for a first-time user onboarding flow.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Full screen (no sidebar yet — it appears after onboarding)
- Centered card (max-width 600px):
  - Step indicator: ● ○ ○ (step 1 of 3)
  - Heading: "Welcome to AI Studio"
  - Subheading: "Your AI Creative Operating System"
  - Body: "What brings you here?"
  - Three large selection cards:
    - 🎨 "I create AI content" (social media, campaigns, art)
    - 🏢 "I manage a brand" (product photos, marketing, campaigns)
    - ⚙️ "I'm technical" (I know ComfyUI, models, infrastructure)
  - Selected card has purple border glow
  - Below: [Continue →] purple button
  - Footer: "This helps us customize your experience. You can change this anytime."

Style: Clean onboarding like Notion or Arc browser. One question per screen. Welcoming, not overwhelming.
```

---

## 13. Movie Assembly (Video Timeline)

```
Create a modern dark-theme SaaS UI mockup for a video movie assembly timeline.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Left sidebar with navigation
- Top: "Movie: Tokyo Night Walk — Episode 1" + [Export] [Share] buttons
- Main area (full width):
  - Video preview player (16:9, showing current frame)
  - Play/pause, scrub bar, timecode
- Below player: Multi-track timeline
  - Track 1 (Video): Color-coded clips on a timeline (each clip is a generated video segment)
    - Clip 1: "Shibuya Crossing" (4s)
    - Clip 2: "Neon Alley" (6s)  
    - Clip 3: "Rooftop" (5s)
    - Transitions shown as small diamond icons between clips
  - Track 2 (Audio): Music waveform spanning full timeline
  - Track 3 (Voice): Narration segments
- Right panel: "Clip Library" — generated video clips available to drag onto timeline
  - Thumbnails with duration badges
  - [Generate New Clip] button
  - [Import from Brain] button
- Bottom bar: total duration, export format selector, render button

Style: Like a simplified iMovie or CapCut editor. Visual timeline, drag-and-drop, no code.
```

---

## 14. Brain with "Thinking..." State

```
Create a modern dark-theme SaaS UI mockup showing an AI chat with a "thinking" loading state.
Dark navy background (#0a0a1a). Purple accents.

Layout:
- Full chat interface (Brain page)
- Previous messages visible above
- User's latest message: "Create a luxury perfume campaign with 3 hero shots and a 15-second video"
- AI response area shows a thinking indicator:
  - Small AI avatar (purple gradient circle)
  - Next to it: "Thinking..." text with a blinking purple dot animation (three dots, pulsing)
  - Below the dots: subtle text "Planning campaign • Selecting talent • Choosing recipe..."
  - The card has a soft purple glow border to indicate active processing
- Chat input at bottom is slightly dimmed (waiting for response)
- Top right: small badge showing "Orunmila planning..." (optional — shows which agent is active)

Style: The thinking state should feel alive and intelligent. Not a generic spinner — it shows WHAT the AI is thinking about.
```

---

## Usage Notes

- Use these prompts as-is in ChatGPT with DALL-E or image generation
- Adjust specific details (talent names, project names) as needed
- The dark navy + purple accent theme should be consistent across all pages
- Each prompt describes ONE screen — generate them individually
- Use the results as reference images for the actual frontend implementation

---

## Key Design Decisions Captured

1. **"Thinking..." with blinking dots** — shows during Ollama response generation
2. **Storyboard in chat** — Brain can generate storyboards conversationally
3. **Manual storyboard editor** — for hands-on creators who want to sequence shots
4. **Movie assembly timeline** — combine clips into longer videos
5. **No CFG, Steps, Samplers visible** — unless user explicitly enters Expert Mode
6. **Cost always visible** — before any paid action
7. **Recipe-based generation** — proven combinations replace manual parameters
8. **Talent-first workflow** — select WHO first, then WHAT to create
