# AI Studio — User Journeys

> Date: 2026-07-04

---

## 1. New User Opens App

```
Home (/) → See dashboard with 0s across the board
         → "Backend not connected" if API not running
         → Quick actions: New Project, AI Brain, Upload Asset, Create Image
         → System Status bar at bottom shows service health
```

**Experience:** Functional but cold. All metrics show 0. No guided onboarding.
**Recommendation:** Add "Getting Started" card when metrics are all zero.

---

## 2. Create First Talent

```
Home → Sidebar: Talent → Click "New Talent" → Fill name + bio → Submit
     → Talent appears in grid
     → Click talent card → Detail panel shows
```

**Experience:** Works well. Form is simple. Refresh persists data from Supabase.
**Issue:** Tabs (Models, Characters, Voices, etc.) don't actually filter.

---

## 3. Upload Asset

```
Home → Sidebar: Assets → Click "Upload Asset" → File picker opens
     → Select image/video → Upload to backend
     → Asset appears in grid with thumbnail
```

**Experience:** Clean flow. Works end-to-end.
**Note:** Filters (Images, Videos, etc.) in the toolbar don't filter yet.

---

## 4. Use AI Brain

```
Home → Sidebar: Brain (or quick action "AI Brain Chat")
     → Select mode (Creative Chat, Prompt Engineer, etc.)
     → Welcome message appears per mode
     → Type message → Send → Response from Ollama
     → Conversation persists in left panel
     → Collections system lets you tag/group conversations
```

**Experience:** Excellent. 6 modes with distinct personalities. Persistence works.
**Issue:** If Ollama is offline, error message tells user to start it. Good fallback.

---

## 5. Generate Image

```
Home → Sidebar: Create → Image tab selected by default
     → Type prompt → Select model (SDXL Turbo, Flux Dev, SD 1.5)
     → Click "Generate" → Loading spinner
     → Result shows inline with generation time
     → Error if ComfyUI/worker not running
```

**Experience:** Works when GPU worker is active. Clear error when not.
**Prerequisite:** Must have worker launched from Admin or Production page.

---

## 6. Launch & Monitor GPU Worker

```
Home → Sidebar: Admin → "GPU Worker" section
     → Click "Launch Worker" (confirm dialog appears — costs money)
     → Status changes: launching → Worker comes online
     → Vast.ai indicator: gray→amber→green
     → Can Pause (saves money) or Stop (destroys)
     → Service toggles for ComfyUI/Ollama appear enabled
```

**Experience:** Full lifecycle supported. Visual feedback at every stage.
**Note:** Auto-refreshes every 15s. Status bar on homepage reflects changes.

---

## 7. View Job Status

```
Home → Sidebar: Production → See job queue
     → KPIs: Active Workers, Jobs in Queue, GPU Spend, Fleet Status
     → Job list with status badges (completed/running/queued/failed)
     → Auto-refreshes every 10s
```

**Experience:** Works well. Real data from API.
**Issue:** Empty state now correctly says "generate from Create page".

---

## 8. Manage Models

```
Home → Sidebar: Models → See model cards
     → Each shows B2 cache status (cached / not cached)
     → "Download to B2" button for uncached models
     → CLI command shown as fallback
```

**Experience:** Clean. Download triggers background process.

---

## 9. Story / Narrative Development

```
Home → Sidebar: Story → See universe cards (or empty state)
     → Click "New Story" → Form: title, desc, genre, platform
     → Universe created → Click card
     → View characters + episodes
     → Add Character / Add Episode forms
```

**Experience:** Full CRUD works. Drill-down navigation.
**Issue:** No breadcrumbs. Back button exists but no visual trail.

---

## 10. Admin / Provider Configuration

```
Home → Sidebar: Admin → Summary cards (Services, Connected, Balance, GPU Status)
     → Service Connections grid with status dots
     → GPU Services toggles (smart: disabled without worker)
     → Integrations panel (ElevenLabs, OAuth, Ollama B2 cache status)
```

**Experience:** Comprehensive. Clear about what needs external setup.

---

## 11. Training (LoRA Fine-Tuning)

```
Home → Sidebar: Training → Drag-drop images
     → Configure: base model, steps, rank, trigger word
     → Click "Start Training" → Job submitted to backend
     → Job history shows status
```

**Experience:** Well-designed form. Needs GPU worker running for actual training.

---

## 12. Publishing / Calendar

```
Home → Sidebar: Publish → Monthly calendar view
     → Navigate months (prev/next arrows)
     → "Schedule Post" shows informational message
     → Scheduled posts appear on calendar dates
```

**Experience:** Calendar renders correctly. Scheduling requires social account setup.

---

## 13. Analytics Review

```
Home → Sidebar: Analytics → Overview tab (default)
     → KPIs: Total Generations, GPU Hours, Spend, Assets
     → Chart: Generation History (30-day bar chart)
     → Switch views: Generation, Cost, Talent, Publishing
     → Talent view has per-talent dropdown
```

**Experience:** Structure is good but data is placeholder.
**Issue:** Charts use random data. Cost metrics are hardcoded.
**Fix Needed:** Wire to `/api/v1/infrastructure/cost` and `/api/v1/generation/history`.

---

## 14. Video Editing

```
Home → Sidebar: Editor → Timeline view
     → Transport controls: play/pause, scrub, prev/next frame
     → 3 tracks: Video, Audio, Text
     → Add Clip / Cut buttons
     → Export button (calls cinematic/render)
```

**Experience:** UI is complete and interactive (scrubbing, cutting clips).
**Limitation:** Preview area is placeholder. No real video rendering yet.
