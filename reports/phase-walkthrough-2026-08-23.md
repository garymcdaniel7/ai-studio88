# AI Studio — Phase-by-Phase Walkthrough & Findings
**Date:** 2026-08-23 · **Method:** authenticated UAT walk of every page as a logged-in user + DB/endpoint verification

---

## The headline: your models were always there — they just weren't being served

**What I found:** Your DB has **21 model records** (FLUX, SDXL, Pony, Hunyuan, WAN, LTX, LoRA, upscalers). But `/api/v1/models` returned **0** — so the Models page showed empty/`unknown` entries and the Create page only showed a couple.

**Root cause:** The list endpoints called `get_models()` **without passing `org_id`**. The models are tenant-scoped (all in your founder org), and the query errored → swallowed → returned empty. Kiro added the models correctly; the serving layer was broken.

**Fixed:** `v1_list_models`, `v1_model_inventory`, and `v1_get_model` now pass `org_id` through. All 21 models now surface.

---

## Phase-by-phase walk results

### Phase 1 — Landing + auth ✅
- Landing page (marketing) renders clean for visitors.
- Login/signup works; session persists via cookie; deep links stay authenticated (no more bounce).
- **Note:** the landing page is a clean-but-generic SaaS page — no "whoa" creative showcase yet (see Vision gap).

### Phase 2 — Home dashboard ✅
- Renders authenticated shell, stats, model/talent counts.
- Assets + projects now load with auth (was raw fetch → 500).

### Phase 3 — Models page ✅ (fixed)
- **Now shows:** On GPU 4 / B2 Only 13 / Total Active 17 / Archived 4
- Full lineup renders: FLUX.1-dev (fp16/fp8), FLUX.2 Dev, Klein 4B/9B, SDXL, Pony, Hunyuan, LTX, WAN, 4x-UltraSharp, LoRA Melissa.
- **Data quality note:** models are duplicated (twins) and there's a junk "Test Model (Delete Me)" archived row.

### Phase 4 — Create/Studio ✅ (fixed)
- Image model list now shows the full FLUX/SDXL/Pony lineup + talent roster (Melissa, Shy, Michael, Darius, Latifah, Jasmine) + style presets.
- **Gap:** models show "Not Loaded" because none are deployed to a live GPU (all B2-only). Video models (WAN/Hunyuan/LTX) exist but the create page's `supported_tasks` logic may not surface them in the Video tab for the empty-tasks entries.

### Phase 5 — Talent/Library/Publish/Admin ✅
- **Talent:** 6 personas, 5 models, LoRA trained.
- **Assets:** real generated files (LoRA safetensors, MP4).
- **Admin:** 9 services / 8 connected / GPU balance $16.71.
- **Publish/Production/Story/Workflows:** clean empty states.
- **Remaining:** raw `fetch()` calls on several admin/projects/training pages → those data calls were hitting the backend without auth (CORS/500). Being swept now.

---

## 🎯 The real gap: code vs. your vision

You told me the product is an **AI talent agency + creator OS** where a **solo non-tech creator** walks in and goes **"whoa, I can make THAT?"** — with adult content behind login + verification, and MCP integrations (Seedance, Kiro).

Where the code actually is:

| Vision | Current state |
|---|---|
| "Whoa" landing page showing jaw-dropping work | Generic SaaS marketing page, no creative showcase |
| AI-talent-agency framing | It's a "studio" tool, not an agency — but Talent tab has the seed (personas, LoRA, voices) |
| Solo non-tech onboarding | Onboarding exists (persona picker) but no guided "make your first thing" flow |
| Full model lineup usable | Models surface now, but none deployed to GPU / not all categorized for video |
| Adult content + verification behind login | No age/agent verification, no legal-agent layer |
| Seedance / Kiro MCP | Not wired |
| Revenue (Stripe) | Billing router added earlier but no UI / not live |

---

## Recommended next decisions (from the earlier fork)

1. **Landing page (whoa) + finish model surfacing** — the front door. Highest leverage for a non-tech creator.
2. **Then MCP (Seedance video + Kiro bridge)** — makes the tool powerful for people already in.
3. **Then onboarding guided flow** — first-time creator makes their first asset in <60s.
4. **Compliance layer** (age/agent verification + legal-agent bot) — needed before adult goes live.

See the in-chat summary for the full recommended sequencing.
