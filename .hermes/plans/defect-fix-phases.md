# AI Studio — Defect Fix Phases

Source: `.hermes/plans/ui-defect-report.md` (~30 findings) + infrastructure findings from fleet test.
Status key: ✅ done · 🔄 in progress · ⏳ queued

## Phase 0 — Foundation (mostly DONE)
- ✅ CORS on Railway backend allows `https://ai-studio88.vercel.app` (G1)
- ✅ Auth enabled: Supabase envs fixed (corrupted vars), login works (G2, G3, F4)
- ✅ Landing CTAs reach working login (G4, F1)
- 🔄 Test-isolation leak fix (in flight)

## Phase 1 — Dead buttons & connectivity (HIGHEST remaining value)
Goal: no silent no-ops. Either wire buttons to real actions or disable with "connectivity required" feedback.
- F9 /create mode buttons (Image/Video/Voice) dead
- F5 /pricing "Join waitlist" + "Request invite" dead
- F13 /projects "New Project" dead
- F14 /assets "Upload Asset" / "Export All" dead
- F15 /story "New Universe" dead
- F16 /editor "Add Shot/Save/Load/Generate All/Assemble Video" dead (+ "Assemble" enabled with 0 shots)
- F20 /training "Start Training" dead
- F21 /publish "Schedule Post" dead
- G6 (umbrella): render disabled + tooltip when backend unreachable

## Phase 2 — Loading states & error fallbacks
Goal: no indefinite spinners.
- F17 /talent "Loading talent…" forever → add error + retry state
- F23 /admin "Loading services…" forever → add error + retry
- F11 /brain dead action buttons w/ no feedback → disable or wire

## Phase 3 — Data integrity & honesty
Goal: real data, not fabricated.
- F10 /brain placeholder/demo content presented as real → gate behind real session
- F20 /training estimate contradicts selected tier
- F6 /pricing free tier behind waitlist contradicts landing "Create Free Account"
- G5/F2/F8 pricing story reconciliation (landing vs /pricing)
- F18 /training quality selector labels merged/confusing

## Phase 4 — Polish (cosmetic)
- F7 /pricing "Hefner" tier rename (branding)
- F12 /brain "Hermes — Offline" label
- G7/F3 hero image alt text
- F19 /training estimate format

## Phase 5 — Deep capability (fleet-proven)
Goal: real end-to-end generation via fleet.
- Verify video → ComfyUI/WAN produces real artifact (handler wired, needs GPU workflow verified)
- Verify LoRA training produces real .safetensors (handler wired, needs GPU training verified)
- Verify image/voice/music/editing handlers wired to real providers
- Page-level test: drive each /create mode → job → fleet worker → real output
