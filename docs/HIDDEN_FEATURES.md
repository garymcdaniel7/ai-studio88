# Hidden Features — Backend Capabilities Not Yet Surfaced in UI

Generated: July 4, 2026

These features exist as complete backend API endpoints but have NO corresponding frontend UI yet. They represent significant untapped value in the platform.

---

## Tier 1: High Value, Easy to Surface (has data model + endpoints)

### 1. Publishing Engine (15 endpoints)
**Router:** `backend/publishing/router.py`
- Create/approve/reject/schedule/publish posts
- Multi-platform packaging (auto-format for IG, TikTok, YouTube, etc.)
- Content repurposing (convert one piece to multiple formats)
- Publishing calendar with scheduling
- Analytics per-post (simulated)
- Platform health checks

**Frontend currently:** Just shows a list of posts from DB. No scheduling UI, no approval workflow, no repurposing.

### 2. Cinematic Studio (18 endpoints)
**Router:** `backend/cinematic/router.py`
- Full timeline management (create timelines, tracks, items)
- Storyboard generation (AI-generated shot breakdowns)
- Editing operations (color grades, transitions, effects)
- Export/render pipeline
- Sequence management
- Continuity checking

**Frontend currently:** Storyboard sequencer handles shot planning. The cinematic endpoints offer much more (timelines, tracks, color grading, continuity).

### 3. Autonomous Studio (AI Departments) (19 departments)
**Router:** `backend/autonomous_studio/router.py`
- 19 AI departments (Creative Director, Script Writer, Music Supervisor, etc.)
- Briefing system — submit a creative brief, departments collaborate
- Auto-recommendations based on project context

**Frontend currently:** Not surfaced at all.

### 4. Company OS (20+ endpoints)
**Router:** `backend/company/router.py`
- Organizations, studios, brands
- Campaign management (create/update campaigns with budgets)
- Team management (invite members, assign roles)
- Approval workflows (submit content for client approval)
- Client management
- License tracking

**Frontend currently:** Not surfaced. Would be the "business layer" — managing clients, brands, campaigns as business entities.

---

## Tier 2: Medium Value, Requires UI Design

### 5. Object Intelligence (25+ endpoints)
**Router:** `backend/object_intelligence/router.py`
- Object DNA (tag objects in images with AI descriptions)
- Product DNA (detailed product attributes for e-commerce)
- Digital Twins (3D versions of products)
- Virtual Try-On (composite product on model)
- 360° Renders
- Scene DNA (describe scenes for recreation)
- Scene Composer (combine talent + product + background)
- Material analysis
- Product commercial templates

**Frontend currently:** Not surfaced. This is a powerful product photography/e-commerce feature set.

### 6. Asset Intelligence (20+ endpoints)
**Router:** `backend/asset_intelligence/router.py`
- Visual DNA (AI-analyzed properties of any image)
- Collections (group assets together)
- Relationships (link related assets)
- Wardrobe system (outfit combinations)
- Scene templates
- Camera presets
- Lighting presets
- Pose presets
- AI recommendations based on asset analysis
- Cross-asset search

**Frontend currently:** Assets page just shows a grid. The intelligence layer (visual DNA, presets, recommendations) is fully backend-ready.

### 7. Performance Engine (20+ endpoints)
**Router:** `backend/performance/router.py`
- Voice training datasets + jobs
- Voice DNA (voice characteristics analysis)
- Music generation (songs with mood/genre/BPM)
- Performance memory (remember acting style per character)
- Performance DNA (body language, expressions)
- Series management (multi-episode productions)

**Frontend currently:** Voice/Music generation exists on the Create page. But the voice DNA, performance memory, and series features are hidden.

### 8. Creator OS (18+ endpoints)
**Router:** `backend/creator_os/router.py`
- Content calendar (schedule across platforms)
- Campaigns (track content campaigns)
- Analytics per campaign
- Brand voice management
- Team collaboration
- Notifications system
- Content repurposing
- Multi-platform management
- Operational recommendations

**Frontend currently:** Not surfaced. Overlaps with publishing but adds campaign-level organization.

### 9. Production Intelligence (backend)
**Router:** `backend/production_intelligence/router.py`
- Production analytics (cost per asset, time per generation)
- Quality scoring
- Performance benchmarks

**Frontend currently:** Analytics page exists but doesn't use these endpoints.

---

## Tier 3: Infrastructure Features (Working but Background)

### 10. Diagnostic Agent
- Auto-diagnoses known error patterns
- Suggests fixes with success rates
- Can attempt auto-resolution
- Learns from interactions

### 11. Provider Reputation Engine
- Tracks reliability per GPU host
- Auto-blacklists unreliable hosts
- Recommends best offers based on history

### 12. Connection Race Mode
- Launches N instances simultaneously
- First to SSH wins, others destroyed
- Learns from boot times per region/host

### 13. Render Fleet
- Multiple parallel GPU workers
- Job routing by specialty (image/video/training)
- Priority queue management

### 14. Cost Intelligence
- Real-time session cost tracking
- Daily/monthly budget limits
- Cost breakdown by GPU/provider
- Budget warnings

### 15. AI Auto-Fix (Code Fixer)
- Pattern-based deterministic fixes
- LLM-assisted complex fixes
- POST /api/v1/brain/fix endpoint

---

## What This Means for the Product

The backend has **310+ endpoints** across 15 routers. The frontend currently uses maybe **40-50** of them. The biggest untapped areas are:

1. **Company OS** — client/brand/campaign management (B2B features)
2. **Autonomous Studio** — AI departments that auto-collaborate on briefs
3. **Object Intelligence** — product photography, virtual try-on, digital twins
4. **Asset Intelligence** — visual DNA, presets, smart recommendations
5. **Publishing Engine** — full scheduling + approval + multi-platform workflow
6. **Performance Engine** — voice DNA, series, performance memory

These represent the platform's differentiation vs competitors. KLING/Runway just generate media. AI Studio can manage the entire production lifecycle — from brief to publish.
