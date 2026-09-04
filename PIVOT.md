# Hermes Creative Studio — Pivot Contract

**Status:** ACTIVE DIRECTION · **Owner:** Gary (Chinwe) · **Intelligence layer:** Hermes
**Preserved:** original commercial/SaaS product frozen on branch `ai-studio-commercial`

This is the single source of truth for the pivot. If the docs and this conflict, this wins.

---

## 1. The Vision (end state)

**"I describe what I want. Hermes figures out how to make it."**

The flow:

```
USER
  ↓
HERMES  (director: picks models, workflows, LoRAs, params, recipes)
  ↓
MCP / TOOL / API LAYER
  ↓
HERMES CREATIVE STUDIO  (projects, characters, storyboards, kanban, assets, review)
  ↓
GENERATION ORCHESTRATION  (job queue)
  ↓
COMFYUI / LOCAL MODELS / GPU  (on-demand)
  ↓
STORAGE (B2) → REVIEW / APPROVAL → FINAL ASSETS → PUBLISH/EXPORT
```

Hermes is the creative director, not a prompt-forwarder. The user never manually
operates ComfyUI or researches checkpoints unless they choose to.

---

## 2. Hard Boundaries (non-negotiable)

1. **NO CSAM. Ever.** Illegal, zero tolerance, no engineering around it.
2. **No real person's likeness without explicit consent.** Deepfakes of real,
   identifiable people without consent = illegal and not built here.
   Fictional/original characters = fully supported. Real people = only with consent
   + likeness rights.
3. **Kim is 100% separate from this system.** Her face, her brand, her boutique, her
   LoRA never touch this studio. No cross-contamination.
4. When Kim gets her own Hermes, she gets the **same studio architecture** but a
   **clean, brand-safe lane** (no adult content, no anatomical LoRAs). Same engine,
   filtered surface. Architecture must not paint us into a corner on this.

---

## 3. The Model Matrix (initial registry)

**Sourcing rule:** HuggingFace + direct repos only. **CivitAI is RED** — never used.
All local models toggleable on/off (VRAM) + worker up/down (cost).

### Images
| Lane | Model | Role |
|---|---|---|
| **PRIORITY — Uncensored (main thing)** | **FLUX.1-dev (fp8)** | best photorealism, trains excellent LoRAs, big uncensored fine-tune ecosystem |
| **PRIORITY — Clean / fast** | **FLUX.2 Klein** | 4-step speed, great quality — hardened, never touches adult lane |
| Quick idea testing | **SDXL-Turbo** | instant + cheap, sketching before the real render |
| Backup / alternative | **Lumina Image 2** | open (Apache), 4K-native, strong FLUX alternative |

### Video
| Lane | Model | Role |
|---|---|---|
| **PRIORITY — Uncensored video** | **Wan 2.2** | open weights, runs local — the adult-video workhorse |
| **PRIORITY — Uncensored alt** | **Hunyuan Video** | fully open, big community, uncensored fine-tunes exist |
| Clean / premium | **MiniMax H3 (API)** | best hosted quality — licensed for US via API only. Open weights EXCLUDE US/EU/UK/Korea from self-hosting. |
| Fast clean tests | **LTX-Video** | cheap/fast, SFW-leaning, quick tests only |

**MODEL PRIORITY (owner directive):** **Flux, Wan, Hunyuan are the priorities.**
These three get built/wired/tested first — Flux for images (both lanes), Wan 2.2 +
Hunyuan for video (uncensored lane). Everything else (SDXL-Turbo, Lumina, LTX, Klein,
MiniMax) is secondary or utility until the trio is proven. MiniMax and any paid API
stay LAST, per the cost principle.

### Voice (TTS)
| Use case | Engine | Why |
|---|---|---|
| **Character voices / cloning (main)** | **XTTS-v3** or **F5-TTS** | real cloning, no content filter, local, uncensored |
| Narration / clean voiceover | **MOSS-TTS** | already in repo (port 18083), solid, free |
| Utility / quick lines | **Kokoro** | tiny, instant, free |
| Singing / intimate tones | **RVC** (conversion layer) | vocal conversion on top of any voice |
| Clean premium (last resort) | ElevenLabs / MiniMax Speech API | best polish, gated, clean lane only |

### Music
| Lane | Engine | Why |
|---|---|---|
| Background tunes | **Suno** | the ONE paid exception (explicitly requested) — background music lane |

---

## 4. Cost Engineering Principle

**Paid/API = LAST option. Local = first. Low-tier = utility only.**

- Local GPU = **flat cost per hour**, marginal cost ~zero per extra generation.
- API (MiniMax, ElevenLabs, etc.) = **per-drip cost**, bleeds on retry loops.
- The recipe system + local-first routing is *the* cost-correct architecture for a
  content producer who iterates a lot.
- Routing decision order: **local available → local first. Uncensored → local only.**
  Paid API → only when no local option exists (e.g. Suno for music, H3 for premium
  clean video).

---

## 5. LoRA System (first-class)

- A LoRA is a trained weight file that locks a *consistent something*: a face, a
  style, an anatomy, an object.
- **LoRA manager:** train (from reference images + trigger word), version, weight,
  attach to characters/models, bake into recipes.
- Character LoRAs (consistency), style LoRAs, anatomical LoRAs (adult lane) — same
  pipeline, different trigger words. "Penis LoRA" is just another LoRA.
- LoRA training must be a REAL tool (job queue → GPU worker → real training), not a stub.

---

## 6. Model Manager

- Drop any model in from HuggingFace → it appears as an option.
- **Toggle per-model on/off** (VRAM control).
- **Worker up/down** (cost control — no idle GPU).
- Both controls exposed to Hermes and the UI.

---

## 7. Tool Surface — Fix ALL MCP Tools

Every existing MCP tool becomes REAL. No stubs. Current inventory (from
`backend/aios/mcp/`):

**Working already:** search_talent, get_talent_dna, create_talent, generate_image,
check_gpu_status, search_assets, search_knowledge

**To fix (stubs/fake):** generate_video (queues nothing), train_lora (no real job),
schedule_post (stub), continue_story, get_story_context, estimate_cost (hardcoded),
recommend_workflow (thin)

**Fix order:** generate_video first (flagship) → train_lora (real pipeline) → the rest
→ then add creative-studio tools (characters, storyboards, recipes, review/approve,
model manager, clip assembly) as the spine builds.

Clip assembly (patching short clips into a longer piece) is a real required tool.

### Three priority tools (must-have, all real)
1. **Simple Tuner** — the LoRA/tuning tool, dead simple on purpose:
   pick a folder of reference images → trigger word → base model → target strength →
   train on the worker → the finished LoRA appears in the LoRA manager ready to use.
   One tool handles face LoRAs, style LoRAs, and anatomical LoRAs ("penis LoRA" is
   just another LoRA — same pipeline, different trigger word). No ComfyUI knowledge
   required to use it.
2. **Image Editor** — a real `edit_image` tool: image-to-image, inpaint/outpaint,
   reference-guided edits, style/wardrobe/background changes, refinement passes.
   Runs on local ComfyUI workflows (FLUX.1-dev img2img / inpaint nodes, etc.).
3. **Lipsync** — real `lip_sync` tool: video + audio → mouth motion matches the
   audio. Local, self-hosted (MuseTalk / LatentSync / Wav2Lip-class), so it's
   uncensored-friendly and stays off paid APIs.

These three are part of the "fix all tools / everything works" mandate, not
stretch goals.

---

## 8. Recipe Intelligence (built on real usage)

- Every generation records: input, prompt, negative prompt, references, model,
  checkpoint, LoRA + weight, sampler, scheduler, steps, CFG, seed, denoise,
  resolution, ControlNet/IPAdapter, ref strengths, workflow, provider, GPU, VRAM,
  gen time, cost, asset, evaluation score, approve/reject, retry chain.
- Approved/rejected generations feed recipes. Hermes can say "this recipe
  historically produces the strongest identity fidelity for this character."
- Don't replace a superior recipe just because a newer model exists — benchmark first.

---

## 9. GPU Orchestration

- **Low-cost always-on host:** Hermes + app + orchestration + job queue.
- **On-demand GPU:** ComfyUI + generation models. Start → load → execute → save →
  report → stop. Avoid idle GPU cost.
- Providers: RunPod, Vast.ai, local hardware — selectable by VRAM/price/availability.

---

## 10. Kim's Clean Lane (parallel architecture)

When Kim gets her own Hermes (see `~/mom-hermes-setup/HANDOFF.md`), she gets the same
studio engine with a clean surface:
- Projects, characters (curated fashion models), LoRA consistency, review/approve,
  model manager — all present.
- **No adult content, no anatomical LoRAs, no uncensored lane.**
- Her own GPU worker, her own models, her own assistant. Fully separate.

---

## 11. Preservation

- Original commercial/SaaS vision preserved on branch `ai-studio-commercial` (frozen).
- Multi-user, tenant, marketplace, billing, subscription, account architecture all
  preserved there for possible future commercialization.
- Do not destroy or overwrite the original product vision.

---

## 12. Operating Principle

The target experience:
- I describe what I want.
- Hermes figures out how to make it.
- Hermes selects tools, models, LoRAs, parameters.
- Hermes executes through the studio.
- Hermes evaluates, learns, updates recipes.
- If a capability is missing, Hermes identifies the gap and proposes an approved
  engineering change.

**Runtime creative action** = use existing capabilities, no code changes.
**Engineering/product change** = requirement → repository reality → spec → plan →
approval → implement → test → migrate → deploy → verify.
