# MiniMax H3 — Operational Runbook

**Story:** 144  
**Adapter:** `backend/video/adapters/minimax_h3_adapter.py`  
**Registry:** `backend/video/registry.py` → `setup_video_providers()`  
**Tests:** `tests/unit/test_minimax_h3_adapter.py` (57 tests)

---

## Enabling the Provider

### 1. Obtain API Key

1. Create account at [platform.minimax.io](https://platform.minimax.io)
2. Navigate to API Keys section
3. Generate a new key with video generation permissions
4. Note: H3 uses pay-as-you-go billing (not video packages)

### 2. Configure Environment

Add to `.env`:

```bash
VIDEO_PROVIDER_MINIMAX_H3_ENABLED=true
VIDEO_PROVIDER_MINIMAX_H3_API_KEY=your-api-key-here
```

Optional tuning:

```bash
VIDEO_PROVIDER_MINIMAX_H3_BASE_URL=https://api.minimax.io    # or api.minimaxi.com for CN
VIDEO_PROVIDER_MINIMAX_H3_PRIORITY=30                         # Lower = preferred
VIDEO_PROVIDER_MINIMAX_H3_POLL_INTERVAL=5                     # Seconds between polls
VIDEO_PROVIDER_MINIMAX_H3_POLL_TIMEOUT=600                    # Max wait (seconds)
VIDEO_PROVIDER_MINIMAX_H3_ENABLE_2K=false                     # 2K regeneration (extra cost)
VIDEO_PROVIDER_MINIMAX_H3_PROMPT_OPTIMIZER=true                # MiniMax prompt enhancement
VIDEO_PROVIDER_MINIMAX_H3_MAX_CONCURRENT=5                    # Parallel job limit
VIDEO_PROVIDER_MINIMAX_H3_RPM=20                              # Requests per minute
```

### 3. Verify

```bash
# Check provider appears in registry
curl -s http://localhost:8000/api/v1/video/providers | python -m json.tool

# Check health
curl -s http://localhost:8000/api/v1/video/providers/minimax-h3
```

---

## Supported Operations

| Operation | Canonical Mode | Provider Options |
|-----------|---------------|------------------|
| Text-to-Video | `text_to_video` | `aspect_ratio`, `prompt_optimizer` |
| Image-to-Video (first frame) | `image_to_video` | `first_frame_image`, `last_frame_image` |
| Reference-to-Video | `text_to_video` + options | `reference_images[]`, `reference_videos[]`, `reference_audio[]` |

### Example: Text-to-Video Request

```json
{
  "mode": "text_to_video",
  "prompt": "A spaceship flying through an asteroid field, cinematic lighting",
  "model": "minimax-h3",
  "duration_seconds": 10,
  "provider_options": {
    "aspect_ratio": "16:9",
    "prompt_optimizer": true
  }
}
```

### Example: Image-to-Video Request

```json
{
  "mode": "image_to_video",
  "prompt": "The character begins walking forward slowly",
  "model": "minimax-h3",
  "input_image_url": "https://your-cdn.com/first-frame.jpg",
  "duration_seconds": 6,
  "provider_options": {
    "last_frame_image": "https://your-cdn.com/last-frame.jpg"
  }
}
```

### Example: Reference-to-Video Request

```json
{
  "mode": "text_to_video",
  "prompt": "Use Image 1 for the character, Video 1 for camera motion",
  "model": "minimax-h3",
  "duration_seconds": 8,
  "provider_options": {
    "reference_images": ["https://cdn.com/character.jpg"],
    "reference_videos": ["https://cdn.com/motion-ref.mp4"],
    "reference_audio": ["https://cdn.com/voice.wav"],
    "aspect_ratio": "16:9"
  }
}
```

---

## Cost Management

| Resolution | Rate | 5s Cost | 10s Cost | 15s Cost |
|-----------|------|---------|----------|----------|
| 768P | $0.10/sec | $0.50 | $1.00 | $1.50 |
| 2K | $0.14/sec | $0.70 | $1.40 | $2.10 |

- Cost is committed at submission (no cancellation)
- Budget checks should run BEFORE calling `submit()`
- Use `estimate_cost()` to get per-request estimates
- Reference video duration may also contribute to billing

---

## Monitoring and Troubleshooting

### Health States

| Status | Meaning | Action |
|--------|---------|--------|
| `available` | API reachable, key valid | Normal operation |
| `degraded` | Network issues, slow responses | Check connectivity; may self-resolve |
| `unavailable` | Auth failed or not configured | Check API key; verify account has credits |

### Common Errors

| Error Code | Cause | Resolution |
|-----------|-------|------------|
| `PROVIDER_AUTH_FAILED` | Invalid or expired API key | Regenerate key at platform.minimax.io |
| `PROVIDER_RATE_LIMITED` | Too many requests | Reduce concurrency; increase RPM tier |
| `PROVIDER_TIMEOUT` | Task exceeded poll timeout | Increase `POLL_TIMEOUT`; check if MiniMax has service issues |
| `DURATION_EXCEEDED` | Requested > 15 seconds | Keep duration 4–15s |
| `INVALID_INPUT` | Bad prompt, missing image, etc. | Check request validation rules |
| `INPUT_TOO_LARGE` | Too many references or prompt > 7000 chars | Reduce input size |
| `OUTPUT_MISSING` | Task succeeded but no video URL | Likely API format change; check adapter |
| `UNSUPPORTED_MODE` | video_to_video requested | Use text_to_video or image_to_video |

### Log Messages

```
minimax_h3_initialized     — Provider started successfully
minimax_h3_task_submitted  — Generation task created (includes task_id, mode, org_id)
minimax_h3_rate_limited    — Rate limit hit (retryable)
minimax_h3_timeout         — Poll timeout exceeded
minimax_h3_api_error       — API returned an error
minimax_h3_cancel_unsupported — Cancel attempted (always fails)
minimax_h3_unexpected_error — Unhandled exception
```

---

## Constraints and Limitations

1. **No cancellation** — Once submitted, tasks cannot be cancelled. Cost is committed.
2. **Integer duration only** — 4, 5, 6... 15 seconds. No fractional values.
3. **Fixed 24 FPS** — Not configurable.
4. **No seed control** — Results are non-deterministic.
5. **No negative prompts** — Not part of H3 API contract.
6. **Result URLs expire in 24 hours** — Adapter downloads immediately.
7. **Audio is always generated** — Cannot produce silent video.
8. **2K requires separate API call** — H3-Regenerate-2K is an additional step (not yet integrated in adapter).

---

## Decisions Required

| # | Decision | Owner | Status | Impact |
|---|----------|-------|--------|--------|
| 1 | Accept China NI Law data-sovereignty risk for hosted API? | Platform Owner / Legal | **OPEN** | All prompts, images, videos route through MiniMax (Chinese entity) infrastructure |
| 2 | Display "MiniMax H3" attribution per license? | Product / Legal | **OPEN** | Required for commercial use under Community License |
| 3 | Implement H3-Regenerate-2K integration? | Product / Engineering | **OPEN** | Extra API call + cost for 2K output; 768P is current default |
| 4 | Add `REFERENCE_TO_VIDEO` as canonical VideoMode? | Architecture | **OPEN** | Currently routed through `provider_options`; cleaner as first-class mode |
| 5 | Implement H3-Context-IR for prompt enhancement? | Product / Engineering | **OPEN** | Better results but extra API latency and cost |
| 6 | Self-hosted mode (requires individual license)? | Legal / Ops | **DEFERRED** | Territory-restricted; requires legal negotiation with MiniMax |

---

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Data sovereignty** — NI Law exposure | High | Document risk; consider for regulated clients; offer alternative providers |
| **Copyright litigation** — H3 built on Hailuo platform in active US lawsuit | Medium | Monitor Disney/Universal/WBD case; no redistribution of outputs as training data |
| **No cancellation** — cost committed at submit | Medium | Pre-validate and estimate cost before submission; budget gate |
| **Result URL expiry (24h)** — data loss if not downloaded | Low | Adapter downloads immediately; B2 upload in job finalization |
| **Pricing instability** — H3 pricing is new | Low | Cost estimates are approximate; log actual costs; alert on drift |
| **API format changes** — MiniMax is rapidly iterating | Low | `_extract_video_url()` handles multiple response formats |
| **No distillation clause** — cannot use outputs to train models | Medium | Enforce in governance policy; document in content provenance |

---

## Files Modified (Story 144)

| File | Change |
|------|--------|
| `backend/video/adapters/minimax_h3_adapter.py` | New — full adapter implementation |
| `backend/video/registry.py` | Added MiniMax H3 registration in `setup_video_providers()` |
| `.env.example` | Added 10 `VIDEO_PROVIDER_MINIMAX_H3_*` variables |
| `docs/providers/MINIMAX_H3_EVIDENCE.md` | New — verified capability/license evidence table |
| `docs/providers/MINIMAX_H3_RUNBOOK.md` | New — this document |
| `tests/unit/test_minimax_h3_adapter.py` | New — 57 unit tests |

---

## Follow-ups

- **Story 145**: Provider comparison and intelligent routing with MiniMax H3
- Implement H3-Context-IR preprocessing for enhanced prompts
- Implement H3-Regenerate-2K for 2K output pipeline
- Add `REFERENCE_TO_VIDEO` canonical mode to contract.py
- Integration tests with live API (requires funded account)
- Cost ledger integration for actual spend tracking
- Governance policy update for NI Law disclosure to users
