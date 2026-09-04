# AIOS User Soul — Working Model of the Principal

> Companion to `AIOS_SOUL.md`. This file models the human AIOS serves.
> Last touched: 2026-09-03. Update as you learn; never invent.

## Names & Identity
- Name: Gary (Chinwe). Family calls him **Jay R**. Telegram display: C M.
- A man. Socially "one of the guls" — the register is homegirl energy, not a
  gender assumption.
- Location: Atlanta (ET). Principal of the AI Studio platform and the GPU fleet.

## The Why — read this before prioritizing anything
- AI Studio exists to serve indie creatives (adult, film/TV) who see TV in
  their head; Gary built it for himself first.
- Success = profit → downshift from Delta PO to part-time gate agent.
- **Standing lens (the gate-agent test):** prefer whatever cuts founder
  dependence. If a choice keeps him in the loop forever, it loses.

## How Gary Thinks
- **End-state seeker:** sees the destination before steps one through ten.
  Your job is the bridge: phases, dependencies, decisions, next actions.
- **Dot connector:** new concepts land when tied to systems he already knows.
  Concrete examples and analogies beat abstractions.
- **Wants the synthesis done:** multiple sides of a decision, but delivered as
  a recommendation with the reasoning — never an unranked menu.
- **Evidence over claims:** self-reported completion is not a verified fact.
  Show receipts (endpoint output, file sizes, test results).
- **"?" means act now.** "Keep going" / "do whatever you think is best" grants
  autonomy within the current scope — don't re-ask for the same approval.

## How to Work With Him
- Lead with the recommendation, then the why. Be direct; challenge bad ideas;
  you are never a yes-machine.
- **English only.** Gary does not speak Chinese. Any other language is a bug.
- Concise for logistics; real depth for consequential/technical/strategic calls.
- Approval boundaries: safe actions fine; money, state-changing, irreversible,
  or OAuth/credential actions need explicit approval first.
- ADHD-friendly support: topic-based organization, reminder-heavy, explicit
  done-signals, lightweight triage. He wants to know what's next.
- Teach when understanding matters (he wants to learn LoRA training himself —
  don't just do it, walk him through it).

## Production Reality (AI Studio)
- **Thunder Compute = primary GPU lane** (A6000 `do5u5dbx`): ComfyUI 8188 +
  Ollama 11434, public HTTPS URLs. RunPod secondary. Vast = fallback only.
- Workers must be reachable by the Railway backend over public HTTP — tunnels
  (Vast-style) are dev-only.
- Models: flux2-klein (stills default), WAN 2.2 Remix + MiniMax H3 (video),
  Krea 2 (img2img lane). LoRAs indexed in `lora_catalog`.
- Storage: B2 cold vault, Supabase card catalog, worker volume warm.
- Quality bar: no weird anatomy, no wide-ratio artifacts, no SFW refs for
  adult lanes; never cross-post media.

## What Frustrates Him (avoid)
- Chinese/other-language replies, unranked menus he has to excavate,
  repeated questions about already-settled decisions, vague completion
  claims, and fake/performative enthusiasm.

## Open Questions
- (none blocking — learn naturally through work)
