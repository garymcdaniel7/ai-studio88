"""Real ffmpeg video assembly — normalize + stitch shot clips into a final video.

Replaces simulation-mode assembly with REAL stitching driven by ffmpeg
subprocesses. This is the lesson-locked path for human-content edits:

- HARD CUTS are the default. NEVER xfade human content — crossfade
  transparency overlap creates ghost / third-body artifacts.
- Optional dip-to-black: each clip fades out/in 0.3-0.5s, then concat.
- Optional L-cut: video concatenated with hard cuts, audio crossfaded
  (acrossfade) while video stays clean.

Normalization spec (all clips):
    scale=768:1152:flags=lanczos, fps=24, format=yuv420p,
    libx264 crf 18, aac 48kHz stereo (H3 native audio is 32kHz -> aresample 48000)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 1152
DEFAULT_FPS = 24
DEFAULT_CRF = 18
NORM_AUDIO_RATE = 48000
NORM_AUDIO_CHANNELS = 2
LOUDNORM_SPEC = "I=-16:TP=-1.5:LRA=11"

# The assembled-video spec — everything normalizes to this.
VIDEO_FILTER = (
    f"scale={DEFAULT_WIDTH}:{DEFAULT_HEIGHT}:flags=lanczos,"
    f"fps={DEFAULT_FPS},format=yuv420p"
)
AUDIO_FILTER = (
    f"aresample={NORM_AUDIO_RATE},"
    f"aformat=sample_fmts=fltp:channel_layouts=stereo"
)


# =============================================================================
# ffmpeg discovery
# =============================================================================


def find_ffmpeg() -> str:
    """Locate an ffmpeg binary: venv > PATH > homebrew fallback."""
    candidates = [
        os.environ.get("FFMPEG_BINARY", ""),
        str(Path(__file__).resolve().parents[1] / ".venv" / "bin" / "ffmpeg"),
        str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "ffmpeg"),
        shutil.which("ffmpeg") or "",
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError(
        "ffmpeg not found. Install it (brew install ffmpeg) or set FFMPEG_BINARY."
    )


def find_ffprobe() -> str:
    """Locate ffprobe alongside the chosen ffmpeg."""
    ffmpeg = find_ffmpeg()
    ffprobe = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
    if os.path.isfile(ffprobe) and os.access(ffprobe, os.X_OK):
        return ffprobe
    for candidate in ("/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe", "/usr/bin/ffprobe"):
        if os.path.isfile(candidate):
            return candidate
    raise RuntimeError("ffprobe not found next to ffmpeg.")


# =============================================================================
# Media probing
# =============================================================================


def probe_media(path: str) -> dict[str, Any]:
    """Probe a media file and return duration/stream info via ffprobe."""
    ffprobe = find_ffprobe()
    cmd = [
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {proc.stderr[-500:]}")
    data = json.loads(proc.stdout or "{}")

    duration = 0.0
    width = height = fps = 0
    audio_rate = 0
    has_audio = False
    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video":
            width = int(stream.get("width", 0) or 0)
            height = int(stream.get("height", 0) or 0)
            fps = _parse_fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
            if not duration:
                duration = float(stream.get("duration", 0) or 0)
        elif codec_type == "audio":
            has_audio = True
            audio_rate = int(stream.get("sample_rate", 0) or 0)
    if not duration:
        duration = float(data.get("format", {}).get("duration", 0) or 0)

    return {
        "path": str(path),
        "duration_seconds": round(duration, 3),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "has_audio": has_audio,
        "audio_sample_rate": audio_rate,
        "size_bytes": os.path.getsize(str(path)),
    }


def _parse_fps(rate: str) -> float:
    try:
        if "/" in rate:
            num, den = rate.split("/")
            return float(num) / float(den) if float(den) else 0.0
        return float(rate)
    except (ValueError, ZeroDivisionError):
        return 0.0


# =============================================================================
# Clip normalization
# =============================================================================


def normalize_clip(
    src: str,
    dst: str,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_FPS,
    crf: int = DEFAULT_CRF,
    fade_out: float = 0.0,
    fade_in: float = 0.0,
    audio_rate: int = NORM_AUDIO_RATE,
) -> dict[str, Any]:
    """Normalize one clip to the assembly spec (libx264 crf18, aac 48k stereo).

    Optionally applies fade-out at the tail and fade-in at the head
    (dip-to-black) — both default to 0 (no fade).
    """
    ffmpeg = find_ffmpeg()
    vf = f"scale={width}:{height}:flags=lanczos,fps={fps},format=yuv420p"
    af = f"aresample={audio_rate},aformat=sample_fmts=fltp:channel_layouts=stereo"

    probe = probe_media(src)
    dur = probe["duration_seconds"]
    filters: list[str] = [f"[0:v]{vf}"]

    if fade_out > 0 and dur > fade_out:
        filters.append(f"fade=t=out:st={max(0.0, dur - fade_out):.3f}:d={fade_out:.3f}")
    if fade_in > 0:
        filters.append(f"fade=t=in:st=0:d={fade_in:.3f}")

    vf_full = ",".join(filters)
    cmd = [
        ffmpeg, "-y", "-i", src,
        "-vf", vf_full,
        "-af", af,
        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        dst,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg normalize failed on {src}: {proc.stderr[-800:]}")

    return probe_media(dst)


# =============================================================================
# Assembly modes
# =============================================================================


def _concat_demuxer(clip_paths: list[str], dst: str) -> dict[str, Any]:
    """Concat normalized clips with the demuxer (-c copy — no re-encode)."""
    ffmpeg = find_ffmpeg()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as lst:
        for p in clip_paths:
            lst.write(f"file '{p}'\n")
        lst_path = lst.name
    try:
        cmd = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0",
            "-i", lst_path,
            "-c", "copy",
            "-movflags", "+faststart",
            dst,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {proc.stderr[-800:]}")
    finally:
        os.unlink(lst_path)
    return probe_media(dst)


def _concat_filter(clip_paths: list[str], dst: str) -> dict[str, Any]:
    """Concat clips via filter_complex (re-encodes; used by L-cut)."""
    ffmpeg = find_ffmpeg()
    n = len(clip_paths)
    inputs: list[str] = []
    for p in clip_paths:
        inputs += ["-i", p]
    filter_complex = "".join(
        f"[{i}:v][{i}:a]" for i in range(n)
    ) + f"concat=n={n}:v=1:a=1[outv][outa]"
    cmd = [
        ffmpeg, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-crf", str(DEFAULT_CRF), "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        dst,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat filter failed: {proc.stderr[-800:]}")
    return probe_media(dst)


def _lcut(clip_paths: list[str], dst: str, crossfade: float = 0.3) -> dict[str, Any]:
    """L-cut: video hard cuts + audio crossfade (acrossfade chain).

    Video is concatenated with the concat filter (hard cuts — no xfade on
    human content). Audio streams are chained through acrossfade so the
    soundtrack overlaps while the picture cuts cleanly.
    """
    ffmpeg = find_ffmpeg()
    n = len(clip_paths)
    inputs: list[str] = []
    for p in clip_paths:
        inputs += ["-i", p]

    parts: list[str] = []
    for i in range(n):
        parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")
    vconcat = "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[outv]"

    # Audio: chain acrossfade pairs.
    a_parts: list[str] = []
    for i in range(n):
        a_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
    cur = "a0"
    for i in range(1, n):
        out = f"ac{i}" if i < n - 1 else "outa"
        a_parts.append(f"[{cur}][a{i}]acrossfade=d={crossfade:.2f}[{out}]")
        cur = out

    filter_complex = ";".join(parts + a_parts + [vconcat])

    cmd = [
        ffmpeg, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-crf", str(DEFAULT_CRF), "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        dst,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg L-cut failed: {proc.stderr[-800:]}")
    return probe_media(dst)


def loudnorm_pass(src: str, dst: str) -> dict[str, Any]:
    """Optional loudnorm audio pass: I=-16:TP=-1.5:LRA=11, aresample=48000."""
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y", "-i", src,
        "-af", f"loudnorm={LOUDNORM_SPEC},aresample={NORM_AUDIO_RATE}",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        dst,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg loudnorm failed: {proc.stderr[-800:]}")
    return probe_media(dst)


# =============================================================================
# Orchestration
# =============================================================================


def assemble_shots(
    clip_sources: list[str],
    out_path: str,
    *,
    mode: str = "cut",
    dip_duration: float = 0.4,
    lcut_crossfade: float = 0.3,
    loudnorm: bool = False,
    workdir: str | None = None,
) -> dict[str, Any]:
    """Assemble ordered clips into one video.

    Args:
        clip_sources: Ordered list of local file paths (or http(s) URLs, which
            are downloaded first).
        out_path: Destination path for the final mp4.
        mode: 'cut' (hard cuts, default), 'dip_to_black', or 'lcut'.
        dip_duration: Fade seconds for dip_to_black (0.3-0.5 recommended).
        lcut_crossfade: Audio crossfade seconds for L-cut.
        loudnorm: Apply loudnorm audio pass (I=-16:TP=-1.5:LRA=11).
        workdir: Scratch dir for normalized intermediates (default: tempdir).

    Returns:
        dict with path, duration_seconds, frames, size_bytes, width, height,
        fps, has_audio, audio_sample_rate, clips (per-clip probe info).
    """
    if mode not in ("cut", "dip_to_black", "lcut"):
        raise ValueError(f"Unknown assembly mode '{mode}'. Use cut, dip_to_black, or lcut.")
    if len(clip_sources) < 1:
        raise ValueError("At least one clip source is required.")

    scratch = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="h3_asm_"))
    scratch.mkdir(parents=True, exist_ok=True)

    resolved: list[str] = []
    for src in clip_sources:
        if str(src).startswith(("http://", "https://")):
            local = _download(src, scratch)
            resolved.append(local)
        else:
            if not os.path.isfile(str(src)):
                raise FileNotFoundError(f"Clip source not found: {src}")
            resolved.append(str(src))

    clips: list[dict[str, Any]] = []
    normalized: list[str] = []
    for i, src in enumerate(resolved):
        probe = probe_media(src)
        if not probe["has_audio"]:
            raise RuntimeError(
                f"Clip {i} ({src}) has no audio stream. H3 clips carry native audio; "
                "silent clips must be muxed with a silent track before assembly."
            )
        dst = str(scratch / f"norm_{i:03d}.mp4")
        if mode == "dip_to_black":
            # Fade out of the previous clip and into the next.
            fade_out = dip_duration if i < len(resolved) - 1 else 0.0
            fade_in = dip_duration if i > 0 else 0.0
            info = normalize_clip(
                src, dst,
                fade_out=min(fade_out, 0.5),
                fade_in=min(fade_in, 0.5),
            )
        else:
            info = normalize_clip(src, dst)
        clips.append(info)
        normalized.append(dst)

    if mode == "lcut":
        assembled = _lcut(normalized, out_path, crossfade=lcut_crossfade)
    elif mode == "dip_to_black":
        assembled = _concat_demuxer(normalized, out_path)
    else:
        assembled = _concat_demuxer(normalized, out_path)

    if loudnorm:
        tmp = str(scratch / "loudnorm_tmp.mp4")
        os.replace(out_path, tmp)
        assembled = loudnorm_pass(tmp, out_path)
        os.unlink(tmp)

    assembled["frames"] = int(round(assembled["duration_seconds"] * assembled.get("fps") or DEFAULT_FPS))
    assembled["mode"] = mode
    assembled["clip_count"] = len(clips)
    assembled["clips"] = clips
    return assembled


def _download(url: str, workdir: Path) -> str:
    """Download a remote clip into the scratch dir."""
    import requests

    filename = url.rsplit("/", 1)[-1].split("?")[0] or f"clip_{abs(hash(url))}.mp4"
    local = workdir / filename
    resp = requests.get(url, timeout=600)
    resp.raise_for_status()
    local.write_bytes(resp.content)
    return str(local)


def upload_video_to_b2(file_bytes: bytes, filename: str, project_id: str | None = None) -> tuple[str, str]:
    """Upload assembled video bytes to B2 via the repo's storage helper.

    Returns (storage_key, public_url).
    """
    from backend.storage import compute_checksum, generate_storage_key, upload_file

    storage_key = generate_storage_key(filename, "video", project_id=project_id)
    public_url = upload_file(file_bytes, storage_key, "video/mp4")
    logger.info("assembled_video_uploaded storage_key=%s size=%d", storage_key, len(file_bytes))
    return storage_key, public_url
