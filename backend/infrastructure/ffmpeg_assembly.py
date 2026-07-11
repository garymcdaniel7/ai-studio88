"""FFmpeg Assembly — Build concat commands for video assembly on GPU workers.

Given a list of clips with transitions, generates the ffmpeg command
that concatenates them into a single output video.

This is dispatched to the GPU worker via SSH (same pattern as ComfyUI setup).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AssemblyClip:
    """A clip in the assembly pipeline."""

    file_path: str
    duration: float
    transition: str = "cut"  # cut, crossfade, fade_black, fade_white, wipe_left
    transition_duration: float = 0.5


def build_ffmpeg_concat_command(
    clips: list[AssemblyClip],
    output_path: str = "/workspace/output/assembled.mp4",
    resolution: str = "1920x1080",
    fps: int = 24,
) -> str:
    """Build an ffmpeg command to concatenate clips with transitions.

    For simple cuts, uses the concat demuxer (fast, no re-encode).
    For complex transitions, uses the filter_complex approach.

    Args:
        clips: List of AssemblyClip objects
        output_path: Where to write the final video
        resolution: Output resolution (WxH)
        fps: Output frame rate

    Returns:
        ffmpeg command string ready for SSH execution
    """
    if not clips:
        return ""

    # Check if all transitions are simple cuts
    all_cuts = all(c.transition == "cut" for c in clips)

    if all_cuts:
        return _build_concat_demuxer(clips, output_path, resolution, fps)
    else:
        return _build_filter_complex(clips, output_path, resolution, fps)


def _build_concat_demuxer(
    clips: list[AssemblyClip],
    output_path: str,
    resolution: str,
    fps: int,
) -> str:
    """Build ffmpeg concat demuxer command (fast, copy codec)."""
    # Create a concat list file content
    concat_list = "\\n".join(f"file '{c.file_path}'" for c in clips)
    width, height = resolution.split("x")

    cmd = (
        f'echo -e "{concat_list}" > /tmp/concat_list.txt && '
        f"ffmpeg -y -f concat -safe 0 -i /tmp/concat_list.txt "
        f'-vf "scale={width}:{height}:force_original_aspect_ratio=decrease,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2" '
        f"-r {fps} -c:v libx264 -preset fast -crf 23 "
        f"-c:a aac -b:a 128k "
        f'"{output_path}"'
    )
    return cmd


def _build_filter_complex(
    clips: list[AssemblyClip],
    output_path: str,
    resolution: str,
    fps: int,
) -> str:
    """Build ffmpeg filter_complex command for transitions."""
    width, height = resolution.split("x")
    n = len(clips)

    # Input files
    inputs = " ".join(f'-i "{c.file_path}"' for c in clips)

    # Build filter chain
    filter_parts = []

    # Scale all inputs
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},"
            f"setpts=PTS-STARTPTS[v{i}]"
        )

    # Apply transitions between consecutive clips
    prev = "v0"
    for i in range(1, n):
        clip = clips[i]
        td = clip.transition_duration
        out_label = f"vout{i}"

        if clip.transition == "crossfade":
            filter_parts.append(
                f"[{prev}][v{i}]xfade=transition=fade:duration={td}:offset="
                f"{clips[i - 1].duration - td}[{out_label}]"
            )
        elif clip.transition == "fade_black":
            filter_parts.append(
                f"[{prev}][v{i}]xfade=transition=fadeblack:duration={td}:offset="
                f"{clips[i - 1].duration - td}[{out_label}]"
            )
        elif clip.transition == "fade_white":
            filter_parts.append(
                f"[{prev}][v{i}]xfade=transition=fadewhite:duration={td}:offset="
                f"{clips[i - 1].duration - td}[{out_label}]"
            )
        elif clip.transition == "wipe_left":
            filter_parts.append(
                f"[{prev}][v{i}]xfade=transition=wipeleft:duration={td}:offset="
                f"{clips[i - 1].duration - td}[{out_label}]"
            )
        else:
            # Default: simple concat
            filter_parts.append(f"[{prev}][v{i}]concat=n=2:v=1:a=0[{out_label}]")

        prev = out_label

    filter_str = ";".join(filter_parts)
    final_label = prev

    cmd = (
        f"ffmpeg -y {inputs} "
        f'-filter_complex "{filter_str}" '
        f'-map "[{final_label}]" '
        f"-c:v libx264 -preset fast -crf 23 "
        f"-r {fps} "
        f'"{output_path}"'
    )
    return cmd


def build_ssh_assembly_command(
    clips: list[dict],
    output_filename: str = "assembled.mp4",
    resolution: str = "1920x1080",
    fps: int = 24,
) -> str:
    """Build the full SSH command to run assembly on a GPU worker.

    Args:
        clips: List of dicts with keys: file_path, duration, transition, transition_duration
        output_filename: Name of the output file
        resolution: Output resolution
        fps: Frame rate

    Returns:
        Complete command string for SSH execution on the worker.
    """
    assembly_clips = [
        AssemblyClip(
            file_path=c.get("file_path", f"/workspace/clips/clip_{i}.mp4"),
            duration=float(c.get("duration", 3)),
            transition=c.get("transition", "cut"),
            transition_duration=float(c.get("transition_duration", 0.5)),
        )
        for i, c in enumerate(clips)
    ]

    output_path = f"/workspace/output/{output_filename}"
    return build_ffmpeg_concat_command(assembly_clips, output_path, resolution, fps)
