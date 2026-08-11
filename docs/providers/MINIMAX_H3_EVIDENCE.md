# MiniMax H3 — Verified Evidence Table

**Story:** 144  
**Research date:** 2026-08-05  
**Sources:** platform.minimax.io official docs, HuggingFace model card (MiniMaxAI/MiniMax-H3), MiniMax H3 Community License Agreement, TechTimes license analysis (2026-08-04), AtlasCloud pricing review (2026-07-30)

---

## Deployment Modes

| Mode | Available | Territory Restriction | Notes |
|------|-----------|----------------------|-------|
| Hosted API | Yes | None (globally available) | `api.minimax.io` (Global) / `api.minimaxi.com` (CN) |
| Self-hosted (open-weight) | Yes (with restrictions) | **Excludes US, EU, UK, South Korea** | MiniMax H3 Community License, effective 2026-08-02 |

**DECISION-REQUIRED:** Self-hosted mode is NOT available for US/EU/UK/Korea users under the Community License. Individual licenses may be negotiated. For this adapter, **only the hosted API mode is implemented** given our likely user base.

---

## Model Specifications

| Attribute | Verified Value | Source |
|-----------|---------------|--------|
| Model name (API) | `MiniMax-H3` | platform.minimax.io/docs/guides/video-generation |
| Architecture | 33.1B dense single-stream omni-transformer | HuggingFace model card |
| Text encoder | Qwen3-VL-32B (layer 50 hidden states) | HuggingFace model card |
| Output resolution | 768P (native), 2K (via H3-Regenerate-2K API) | Official docs |
| Output duration | 4–15 seconds, integer values only | Official docs |
| Output FPS | 24 FPS | Official docs |
| Output audio | 32 kHz native stereo | Official docs |
| Supported dialogue languages | 11 (Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian, Spanish) | HuggingFace model card |
| Aspect ratios | 21:9, 16:9, 4:3, 1:1, 3:4, 9:16, adaptive | Official docs |

---

## Supported Generation Modes (Hosted API)

| Mode | Model Variant | Required Input | Optional Input |
|------|--------------|----------------|----------------|
| Text-to-Video | MiniMax-H3 | prompt | aspect_ratio, duration |
| First/Last-Frame Image-to-Video | MiniMax-H3 | prompt + first_frame and/or last_frame image | duration |
| Reference-to-Video | MiniMax-H3 | prompt + reference images/videos/audio | duration, aspect_ratio |

---

## Input Limits (Hosted API)

| Input Type | Constraint | Value |
|-----------|------------|-------|
| Prompt length | Max characters | 7,000 |
| First/last-frame images | Count | 0, 1, or 2 |
| Image dimensions | Width/height | 256–5,760 px |
| Image aspect ratio | Width/height | 2:5 to 5:2 |
| Image file size | Per file | ≤ 30 MB |
| Image formats | Accepted | JPG, JPEG, PNG, WEBP, HEIC, HEIF |
| Reference images | Max count | 9 |
| Reference videos | Max count | 3 clips |
| Reference video duration | Per clip / total | 2–15s each; total ≤ 15s |
| Reference video formats | Codec | H.264/AVC, H.265/HEVC |
| Reference video file size | Per file | ≤ 50 MB |
| Reference audio | Max count | 3 clips (must accompany image/video) |
| Reference audio duration | Per clip / total | 2–15s each; total ≤ 15s |
| Reference audio formats | Accepted | WAV, MP3 |
| Reference audio file size | Per file | ≤ 15 MB |
| Mixed references | Total files | ≤ 12 |
| API request body | Max size | ≤ 64 MB |

---

## API Endpoints (Hosted)

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Create generation task | POST | `https://api.minimax.io/v1/video_generation` |
| Create H3-Context-IR task | POST | (v2 endpoint for prompt enhancement) |
| Create Regeneration (2K) task | POST | (v2 endpoint for 768P→2K) |
| Query task status | GET | `https://api.minimax.io/v1/query/video_generation?task_id={id}` |
| Cancel/Delete task | POST | (v2 endpoint) |

**Authentication:** `Authorization: Bearer <token>`

---

## Async Task Lifecycle

| Status | Meaning |
|--------|---------|
| `Processing` / `processing` | Task in progress |
| `Success` / `success` | Completed; video URL available |
| `Failed` / `failed` | Generation failed |

**Callback:** Optional `callback_url` parameter. MiniMax pushes status updates via POST.

---

## Cancellation

| Attribute | Value |
|-----------|-------|
| Supported | **No** (can_cancel: false per EvoLink docs) |
| Behavior | Tasks cannot be cancelled once submitted |

**UNVERIFIED:** Official MiniMax docs mention a "Cancel or Delete Task" endpoint for H3 tasks. This may only delete completed tasks, not cancel in-progress ones. The adapter returns `False` for cancel operations.

---

## Pricing (Hosted API)

| Resolution | Cost per second | Source |
|-----------|----------------|--------|
| 768P | ~$0.10/sec | AtlasCloud review (Jul 2026) |
| 2K | ~$0.14/sec | AtlasCloud review (Jul 2026) |
| CNY rate | ¥0.8/sec (2K) | OpenSourceForu (Aug 2026) |

**Note:** MiniMax pricing page states "Video packages support the Hailuo series. MiniMax H3 is not supported yet." — H3 uses pay-as-you-go token billing, not video packages.

---

## Self-Hosted Requirements (for reference — NOT implemented)

| Resource | Requirement |
|----------|-------------|
| GPUs | 4x (NVIDIA, 80GB+ VRAM each) |
| Model size | ~33B params, BF16 |
| Download size | ~42.5 GB minimum (pruned INT8); ~498 GB full |
| RAM | ~64 GB host RAM (for offloading) |
| CUDA | 11.8+ |
| Serving | SGLang or vLLM recommended |
| ComfyUI | Supported via PR #15224 (merged 2026-08-03) |

---

## License Constraints

| Constraint | Details |
|-----------|---------|
| Territory exclusion | US, EU, UK, South Korea excluded from local weight deployment |
| Revenue threshold | >$20M annual revenue requires written authorization (all territories) |
| Attribution | Commercial use must display "MiniMax H3" in UI |
| No distillation | Cannot use H3 or outputs to train other AI models (global, Section V.3) |
| Governing law | Hong Kong SAR |
| Copyright litigation | Disney/Universal/WBD vs MiniMax (US Central District CA, active) |

---

## Capabilities NOT Supported

| Capability | Status | Notes |
|-----------|--------|-------|
| Video-to-video editing | Not a distinct mode | Reference-to-video with base_video is "Regeneration" (2K upscale only) |
| LoRA training | Not supported | No fine-tuning API |
| 4K output | Not supported | Max is 2K |
| 60 FPS | Not supported | Fixed 24 FPS |
| Configurable bitrate/codec | Not supported | Not part of API contract |
| Seed control | Not documented | No seed parameter in H3 API |
| Negative prompt | Not documented | Not part of H3 API |
| Camera motion commands | Not documented for H3 | Was available for Hailuo 2.3, not confirmed for H3 |
| Real-time streaming | Not supported | Async task workflow only |

---

## Mapping to Canonical VideoMode

| Canonical Mode | H3 Support | Implementation |
|---------------|------------|----------------|
| TEXT_TO_VIDEO | Yes | Direct mapping to H3 text-to-video |
| IMAGE_TO_VIDEO | Yes | Maps to first/last-frame mode |
| VIDEO_TO_VIDEO | No | Not supported — reference-to-video is a different paradigm |

**Note:** Reference-to-video is a new mode not in the current VideoMode enum. It is exposed via `provider_options` until the canonical contract adds a REFERENCE_TO_VIDEO mode.

---

## Risks

1. **National Intelligence Law exposure:** All API calls route through MiniMax infrastructure (Chinese entity). Articles 7/14 of 2017 NI Law apply.
2. **Copyright litigation:** H3 built on Hailuo platform named in active US lawsuit.
3. **Result URL expiry:** Generated video URLs expire after 24 hours — must download immediately.
4. **No cancellation:** Cost committed at submission time.
5. **Pricing instability:** H3 pricing is new and not yet on video packages; may change.
6. **2K requires extra API call:** Full quality requires H3-Regenerate-2K (additional cost + latency).

---

## Decisions Required

| Decision | Owner | Impact |
|----------|-------|--------|
| Accept NI Law data-sovereignty risk for hosted API? | Platform owner | Required for any MiniMax API usage |
| Display "MiniMax H3" attribution in UI per license? | Product/Legal | Required for commercial use |
| Support 2K via Regenerate-2K (extra cost + API call)? | Product | Affects quality ceiling |
| Add REFERENCE_TO_VIDEO as canonical mode? | Architecture | Affects contract.py shared types |
| Implement self-hosted mode (requires individual license for US)? | Legal/Ops | Complex, restricted territories |
