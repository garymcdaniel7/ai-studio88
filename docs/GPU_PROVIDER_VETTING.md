# GPU Provider Vetting — Decision Matrix (v1, Aug 29 2026)

**Purpose:** Thoroughly vet GPU providers for Hermes Creative Studio before committing.
**Goal:** Vast-level prices + data persistence + reliability, for the Remix NSFW / Wan 2.2 stack.
**Sources:** Provider pricing pages + live Vast API queries + community reports (Reddit), verified today.

---

## 1. The Requirement

The production stack needs:
- **RTX 3090/4090-class** (24GB) or **A6000/A100** (48-80GB) for Wan 2.2 14B fp8
- **Persistent model storage** — the ~40GB Remix NSFW stack should download ONCE, never re-download
- **Reliable uptime** — no "instance died, re-provision" pain
- **API/SSH control** — Hermes must be able to provision, run jobs, shut down programmatically

---

## 2. Head-to-Head Pricing (verified today)

| Provider | RTX 3090 (24GB) | RTX 4090 (24GB) | A6000 (48GB) | A100 80GB | Billing |
|---|---|---|---|---|---|
| **Vast.ai** | **$0.10-0.13/hr** | $0.28-0.34/hr | varies | $0.80-1.00/hr | per-sec |
| **RunPod** | $0.50/hr | $0.74/hr | $0.53/hr | $1.39/hr | per-sec |
| **Thunder Compute** | not listed | not listed | **$0.35/hr** | **$1.09/hr** | per-min |
| **TensorDock** | ~$0.12/hr+ | from $0.12/hr | varies | $0.90/hr | per-hr |
| **Lambda** | n/a (no consumer) | n/a | ~$1.30 | $2.79/hr | per-min |
| **Spheron** | n/a | $0.58/hr | n/a | $0.72/hr | per-min |

*Vast prices are live marketplace quotes (lowest verified); others are published rates.*

---

## 3. Scoring by Factor (1-5, higher = better)

| Factor | Vast | RunPod | Thunder | TensorDock | Lambda |
|---|---|---|---|---|---|
| **Price** | 5 | 3 | 4 | 4 | 2 |
| **Persistence** | 1 | 5 | 5 | 3 | 4 |
| **Reliability** | 2 | 4 | 4 | 2 | 5 |
| **Availability/stock** | 3 | 5 | 3 | 3 | 1 |
| **API/automation** | 3 | 5 | 3 | 3 | 3 |
| **Consumer GPUs (3090/4090)** | 5 | 4 | 1 | 4 | 1 |
| **Ease of setup** | 3 | 4 | 4 | 3 | 3 |
| **Community track record** | 3 | 5 | 2 | 2 | 4 |
| **TOTAL** | **25** | **35** | **26** | **24** | **23** |

---

## 4. The Verdicts

### 🏆 RunPod — Best overall for this use case
- **Why:** Best balance of everything. Per-second billing, reliable pods, **network volumes** = models survive restarts forever, strong API/automation, always in stock, huge community.
- **Cost:** ~$360/mo always-on 3090, or ~$50/mo storage if you stop/start pods. Scoped API keys now available (Aug 2026).
- **Risk:** Slightly pricier per hour. Reddit mixed on pod boot times but API is solid.

### 🥈 Thunder Compute — Best "cheap + persistence" newcomer
- **Why:** Genuinely low prices (A6000 48GB @ $0.35/hr — great for 14B fp8!), **snapshots** = exact environment restores, per-minute billing, no egress fees, enterprise DCs (not a marketplace).
- **Cost:** A6000 always-on ~$250/mo, or snapshot-based start/stop for much less.
- **Risk:** **Newer company** — less battle-tested, no consumer 3090/4090 listed, API less proven. Worth a trial.

### 🥉 Vast.ai — Keep as burst capacity only
- **Why:** Cheapest raw 3090s. But persistence is the pain you named — keep it for parallel bursts, never the home base.
- **Risk:** Marketplace hosts vanish; state loss; the A100 bricked today.

### ❌ TensorDock — Avoid
- Acquired by Voltage Park (Mar 2025), leadership turnover, reliability issues reported. Marketplace model = same structural risk as Vast but with worse track record.

### ❌ Lambda — Avoid for this
- No consumer GPUs, constantly out of stock, pricier. Great for research, wrong for this.

---

## 5. Recommended Architecture

**Primary (persistent home): RunPod**
- One **RTX 3090 or 4090 pod** + **network volume** (~100GB)
- Remix NSFW 14B high/low + nsfw CLIP + LoRAs live on the volume — **downloaded once, survive restarts**
- Hermes worker polls Supabase jobs → ComfyUI generates → B2 upload
- Shut down pod when idle (pay only storage ~$5-10/mo)

**Secondary (burst): Vast.ai**
- Spin up cheap 3090s for parallel/content days
- Same worker code, same job queue — no code changes
- Shut down when done

**Alternative (try first, 1 week): Thunder Compute**
- A6000 48GB @ $0.35/hr is the best $/VRAM for the 14B fp8 stack
- Test snapshot persistence with the actual model stack
- If solid → could become primary (cheaper than RunPod)

---

## 6. Decision Needed

1. **Primary provider:** RunPod (proven) vs Thunder Compute (cheaper, needs trial)?
2. **GPU:** 3090 ($0.50) vs 4090 ($0.74) vs A6000-48GB ($0.35 on Thunder)?
3. **Immediate action:** Set up RunPod scoped key + provision, OR trial Thunder first?

**My recommendation:** Set up **RunPod 4090** as primary NOW (get the Remix stack running — it's already downloaded, just needs a home). In parallel, open a **Thunder Compute trial** with an A6000 to see if the cheaper path holds up. If Thunder proves reliable in a week, migrate primary there and keep RunPod as the backup.
