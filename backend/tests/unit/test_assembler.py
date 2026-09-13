"""Tests for the real ffmpeg assembler.

These tests generate tiny real clips with ffmpeg and stitch them through
the actual assembly pipeline (normalize -> concat). Skipped if ffmpeg is
unavailable on the host.
"""

from __future__ import annotations

import subprocess

import pytest

from backend.video.assembler import (
    assemble_shots,
    find_ffmpeg,
    loudnorm_pass,
    normalize_clip,
    probe_media,
)

pytestmark = pytest.mark.skipif(
    not __import__("shutil").which("ffmpeg")
    and not __import__("os").path.exists("/opt/homebrew/bin/ffmpeg"),
    reason="ffmpeg not available on this host",
)

# 768x1152 with audio, 24fps, 2s — mirrors an H3 clip spec
CLIP_SPEC = (
    "color=c=0x336699:s=768x1152:d=2:r=24,format=yuv420p,"
    "sine=frequency=440:sample_rate=32000:duration=2"
)


def _make_clip(path: str, color: str = "0x336699", freq: int = 440) -> None:
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=768x1152:d=2:r=24,format=yuv420p",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=32000:duration=2",
        "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast",
        "-c:a", "aac", "-ar", "32000",
        "-shortest",
        path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-500:]


def test_probe_media_reports_h3_spec(tmp_path) -> None:
    clip = str(tmp_path / "clip.mp4")
    _make_clip(clip)
    info = probe_media(clip)
    assert info["width"] == 768
    assert info["height"] == 1152
    assert info["fps"] == pytest.approx(24, abs=0.5)
    assert info["has_audio"] is True
    assert info["audio_sample_rate"] == 32000  # H3 native
    assert info["duration_seconds"] == pytest.approx(2.0, abs=0.3)


def test_normalize_clip_converts_to_48k_stereo(tmp_path) -> None:
    clip = str(tmp_path / "clip.mp4")
    norm = str(tmp_path / "norm.mp4")
    _make_clip(clip)
    info = normalize_clip(clip, norm)
    assert info["width"] == 768
    assert info["height"] == 1152
    assert info["fps"] == pytest.approx(24, abs=0.5)
    assert info["audio_sample_rate"] == 48000  # aresampled from 32k
    assert info["has_audio"] is True


def test_assemble_cut_mode_hard_concats(tmp_path) -> None:
    c1 = str(tmp_path / "c1.mp4")
    c2 = str(tmp_path / "c2.mp4")
    _make_clip(c1, "0x336699", 440)
    _make_clip(c2, "0xCC4444", 660)
    out = str(tmp_path / "final.mp4")
    result = assemble_shots([c1, c2], out, mode="cut")
    assert result["duration_seconds"] == pytest.approx(4.0, abs=0.5)
    assert result["frames"] == pytest.approx(96, abs=16)
    assert result["width"] == 768
    assert result["height"] == 1152
    assert result["audio_sample_rate"] == 48000
    assert result["clip_count"] == 2
    assert result["mode"] == "cut"


def test_assemble_dip_to_black(tmp_path) -> None:
    c1 = str(tmp_path / "c1.mp4")
    c2 = str(tmp_path / "c2.mp4")
    _make_clip(c1, "0x336699", 440)
    _make_clip(c2, "0xCC4444", 660)
    out = str(tmp_path / "final_dip.mp4")
    result = assemble_shots([c1, c2], out, mode="dip_to_black", dip_duration=0.4)
    assert result["mode"] == "dip_to_black"
    assert result["duration_seconds"] == pytest.approx(4.0, abs=0.6)


def test_assemble_lcut_video_cut_audio_crossfade(tmp_path) -> None:
    c1 = str(tmp_path / "c1.mp4")
    c2 = str(tmp_path / "c2.mp4")
    _make_clip(c1, "0x336699", 440)
    _make_clip(c2, "0xCC4444", 660)
    out = str(tmp_path / "final_lcut.mp4")
    result = assemble_shots([c1, c2], out, mode="lcut", lcut_crossfade=0.3)
    assert result["mode"] == "lcut"
    assert result["has_audio"] is True
    # Video keeps full duration (hard cuts); audio crossfade shortens slightly.
    assert result["duration_seconds"] == pytest.approx(3.7, abs=0.6)


def test_assemble_loudnorm_pass(tmp_path) -> None:
    c1 = str(tmp_path / "c1.mp4")
    c2 = str(tmp_path / "c2.mp4")
    _make_clip(c1)
    _make_clip(c2)
    out = str(tmp_path / "final_ln.mp4")
    result = assemble_shots([c1, c2], out, mode="cut", loudnorm=True)
    assert result["duration_seconds"] == pytest.approx(4.0, abs=0.6)
    assert result["audio_sample_rate"] == 48000


def test_assemble_raises_on_missing_source(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        assemble_shots([str(tmp_path / "nope.mp4")], str(tmp_path / "x.mp4"))


def test_loudnorm_pass_keeps_video(tmp_path) -> None:
    clip = str(tmp_path / "clip.mp4")
    out = str(tmp_path / "ln.mp4")
    _make_clip(clip)
    info = loudnorm_pass(clip, out)
    assert info["width"] == 768
    assert info["has_audio"] is True
    assert info["audio_sample_rate"] == 48000
