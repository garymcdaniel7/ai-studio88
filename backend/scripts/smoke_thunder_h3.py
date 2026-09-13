"""Real end-to-end smoke test: Thunder H3 I2V against Gary's box.

Usage: COMFYUI_BASE_URL=http://localhost:18188 backend/.venv/bin/python \
    backend/scripts/smoke_thunder_h3.py

Submits ONE tiny H3 generation (length=226, steps=8), polls ComfyUI,
downloads the video, uploads it to B2 via the repo storage helper, and
prints the actual prompt_id, duration, size, and public URL.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.video.adapters.thunder_h3_adapter import (
    ThunderH3VideoAdapter,
    build_h3_prompt,
)
from backend.video.contract import VideoGenerationRequest, VideoMode

IMAGE = "/tmp/h3_smoke/tsq_frame.png"
LENGTH = 226  # 17k+5 grid minimum
STEPS = 8
SEED = int(os.getenv("SMOKE_SEED", "424242"))


def main() -> None:
    with open(IMAGE, "rb") as fh:
        image_bytes = fh.read()
    print(f"first frame: {IMAGE} ({len(image_bytes)} bytes)")

    prompt = build_h3_prompt(
        "Live-action, cinematic. The tall muscular Black man with very deep "
        "dark skin, wearing only fitted waist beads, crawls forward on the wet "
        "pavement in Times Square at night with slow confident seductive energy, "
        "then slowly rises to a kneeling position facing the camera with direct "
        "eye contact. LED billboards and yellow taxis remain consistent in the "
        "background; facial identity, skin tone and body proportions stay "
        "exactly as in <Picture 1> throughout.",
        overall_soundscape="Times Square night ambience, distant traffic, city murmur, low confident breaths.",
    )

    request = VideoGenerationRequest(
        mode=VideoMode.IMAGE_TO_VIDEO,
        prompt=prompt,
        negative_prompt="",
        input_image_bytes=image_bytes,
        model="thunder-h3",
        duration_seconds=round(LENGTH / 24, 3),
        fps=24,
        width=768,
        height=1152,
        seed=SEED,
        steps=STEPS,
        provider_options={"length": LENGTH, "out_prefix": "video/smoke_tsq"},
    )

    adapter = ThunderH3VideoAdapter()
    from backend.video.contract import VideoProviderConfig

    adapter.initialize(
        VideoProviderConfig(
            name="thunder-h3",
            enabled=True,
            priority=40,
            settings={
                "base_url": os.getenv("COMFYUI_BASE_URL", "http://localhost:8188"),
                "timeout_seconds": int(os.getenv("COMFYUI_API_TIMEOUT", "1800")),
            },
        )
    )

    def on_progress(p) -> None:
        print(f"  progress: {p.percent}% {p.message}", flush=True)

    t0 = time.time()
    result = adapter.submit(request, on_progress=on_progress)
    elapsed = time.time() - t0

    print("\n=== SMOKE RESULT ===")
    print(f"success: {result.success}")
    print(f"provider_job_id (prompt_id): {result.provider_job_id}")
    print(f"elapsed_wall: {elapsed:.1f}s")
    print(f"generation_time_seconds: {result.generation_time_seconds}")
    if not result.success:
        print(f"error_code: {result.error_code}")
        print(f"error_message: {result.error_message}")
        sys.exit(1)

    print(f"filename: {result.filename}")
    print(f"duration_seconds: {result.duration_seconds}")
    print(f"width x height: {result.width}x{result.height}")
    print(f"fps: {result.fps}")
    print(f"size_bytes: {len(result.output_bytes or b'')}")
    print(f"metadata: {result.metadata}")

    out_path = "/tmp/h3_smoke/smoke_out.mp4"
    with open(out_path, "wb") as fh:
        fh.write(result.output_bytes)
    print(f"saved: {out_path}")

    # Verify the B2 upload path (TASK A step 6: storage_key + public URL)
    try:
        from backend.storage import compute_checksum, generate_storage_key, upload_file

        storage_key = generate_storage_key(result.filename, "video")
        checksum = compute_checksum(result.output_bytes)
        public_url = upload_file(result.output_bytes, storage_key, "video/mp4")
        print(f"\nB2 upload OK")
        print(f"storage_key: {storage_key}")
        print(f"public_url: {public_url}")
        print(f"checksum: {checksum}")
    except Exception as exc:
        print(f"\nB2 upload FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
