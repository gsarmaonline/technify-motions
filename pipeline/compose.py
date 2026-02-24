"""Compose the final video by overlaying diagram clips at their timestamps."""

import json
import subprocess
import os
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from .models import Diagram

_console = Console()


def compose_video(
    source_video: str,
    diagrams: list[Diagram],
    output_path: str,
    mode: str = "pip",  # "pip" | "side_by_side" | "replace"
) -> str:
    """
    Compose the final video with diagram overlays synced to timestamps.

    Args:
        source_video: Path to the original video file.
        diagrams: List of Diagram objects with video_path and scene timestamps.
        output_path: Where to write the final video.
        mode: Composition mode.
            - "pip": diagram as picture-in-picture (bottom-right corner)
            - "side_by_side": source left, diagram right
            - "replace": show diagram instead of source video during scene

    Returns:
        Path to the composed output video.
    """
    renderable = [d for d in diagrams if d.video_path and Path(d.video_path).exists()]
    if not renderable:
        print("[compose] No rendered diagrams to overlay — copying source unchanged")
        subprocess.run(["cp", source_video, output_path], check=True)
        return output_path

    if mode == "pip":
        return _compose_pip(source_video, renderable, output_path)
    elif mode == "side_by_side":
        return _compose_side_by_side(source_video, renderable, output_path)
    elif mode == "replace":
        return _compose_replace(source_video, renderable, output_path)
    else:
        raise ValueError(f"Unknown mode: {mode}")


def _compose_pip(source_video: str, diagrams: list[Diagram], output_path: str) -> str:
    """
    Overlay each diagram as a PIP in the bottom-right corner during its time window.
    Chains overlays sequentially using ffmpeg filter_complex.
    """
    # Build filter_complex for chained overlays
    # Each diagram is overlaid on the result of the previous overlay
    inputs = ["-i", source_video]
    for d in diagrams:
        inputs += ["-i", d.video_path]

    filter_parts = []
    prev = "[0:v]"

    for i, diagram in enumerate(diagrams):
        start = diagram.start
        end = diagram.end
        # Scale PIP to 40% of screen width, preserve aspect ratio
        pip_label = f"[pip{i}]"
        scale_filter = f"[{i+1}:v]scale=iw*0.4:-1{pip_label}"
        filter_parts.append(scale_filter)

        out_label = f"[v{i}]" if i < len(diagrams) - 1 else "[vout]"
        overlay_filter = (
            f"{prev}{pip_label}overlay=W-w-20:H-h-20"
            f":enable='between(t,{start},{end})'"
            f"{out_label}"
        )
        filter_parts.append(overlay_filter)
        prev = f"[v{i}]"

    filter_complex = ";".join(filter_parts)

    cmd = (
        ["ffmpeg", "-y"]
        + inputs
        + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a?",       # carry original audio
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            output_path,
        ]
    )

    with _console.status(f"[cyan]PIP compositing {len(diagrams)} diagram(s)...[/]"):
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg compose failed:\n{result.stderr}")

    print(f"[compose] Output saved to {output_path}")
    return output_path


def _source_duration(source_video: str) -> float:
    """Return the duration of a video file in seconds via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", source_video],
        capture_output=True, text=True, timeout=30,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _compose_side_by_side(source_video: str, diagrams: list[Diagram], output_path: str) -> str:
    """
    Segment-based side-by-side: gaps between diagrams are stream-copied (fast),
    only diagram windows are composited and re-encoded (source left, diagram right).
    """
    diagrams = sorted(diagrams, key=lambda d: d.start)
    source_dur = _source_duration(source_video)

    # Build timeline: list of (t_start, t_end, diagram_or_None)
    segments: list[tuple[float, float, Diagram | None]] = []
    cursor = 0.0
    for d in diagrams:
        if d.start > cursor + 0.05:
            segments.append((cursor, d.start, None))
        segments.append((d.start, d.end, d))
        cursor = d.end
    if cursor < source_dur - 0.05:
        segments.append((cursor, source_dur, None))

    clip_paths: list[str] = []
    concat_path = output_path.replace(".mp4", "_concat.txt")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Compositing segments...", total=len(segments))

        for j, (t_start, t_end, diagram) in enumerate(segments):
            clip = output_path.replace(".mp4", f"_seg{j:03d}.mp4")
            clip_paths.append(clip)

            if diagram is None:
                # No diagram — stream copy (no re-encode, very fast)
                progress.update(task, description=f"[cyan]Copying segment {j+1}/{len(segments)} ({t_start:.0f}s–{t_end:.0f}s)")
                subprocess.run(
                    ["ffmpeg", "-y",
                     "-ss", str(t_start), "-to", str(t_end),
                     "-i", source_video,
                     "-c", "copy", clip],
                    capture_output=True, check=True, timeout=600,
                )
            else:
                # Diagram window — composite source (left) + diagram (right)
                progress.update(task, description=f"[cyan]Compositing segment {j+1}/{len(segments)} ({t_start:.0f}s–{t_end:.0f}s)")
                filter_complex = (
                    "[0:v]scale=960:1080:force_original_aspect_ratio=decrease,"
                    "pad=960:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
                    "pad=1920:1080:0:0:color=black[left];"
                    "[1:v]scale=960:1080:force_original_aspect_ratio=decrease,"
                    "pad=960:1080:(ow-iw)/2:(oh-ih)/2:color=white[right];"
                    "[left][right]overlay=960:0[out]"
                )
                subprocess.run(
                    ["ffmpeg", "-y",
                     "-ss", str(t_start), "-to", str(t_end), "-i", source_video,
                     "-i", diagram.video_path,
                     "-filter_complex", filter_complex,
                     "-map", "[out]", "-map", "0:a?",
                     "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
                     "-c:a", "aac", clip],
                    capture_output=True, check=True, timeout=600,
                )
            progress.advance(task)

    # Write concat list and stitch all segments together
    with open(concat_path, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{os.path.abspath(cp)}'\n")

    with _console.status("[cyan]Stitching segments into final video...[/]"):
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_path, "-c", "copy", output_path],
            capture_output=True, text=True, timeout=600,
        )

    for cp in clip_paths:
        Path(cp).unlink(missing_ok=True)
    Path(concat_path).unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr}")

    print(f"[compose] Output saved to {output_path}")
    return output_path


def _compose_replace(source_video: str, diagrams: list[Diagram], output_path: str) -> str:
    """
    Replace the source video with the diagram during each scene window.
    Uses ffmpeg trim + concat to splice diagram clips into the source.
    """
    # Build a list of segments: [(start, end, source|diagram_path), ...]
    events: list[tuple[float, str]] = [(0.0, source_video)]
    for d in diagrams:
        events.append((d.scene.start, d.video_path))
        events.append((d.scene.end, source_video))
    events.sort(key=lambda x: x[0])

    # Deduplicate and build segment list
    segments: list[tuple[float, float, str]] = []
    for i, (start, path) in enumerate(events):
        end = events[i + 1][0] if i + 1 < len(events) else None
        if end is None or end <= start:
            continue
        segments.append((start, end, path))

    # Extract each segment clip with a progress bar
    concat_list_path = output_path.replace(".mp4", "_concat.txt")
    clip_paths = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Extracting clips...", total=len(segments))
        for j, (start, end, path) in enumerate(segments):
            clip_path = output_path.replace(".mp4", f"_clip{j:03d}.mp4")
            progress.update(task, description=f"[cyan]Clip {j + 1}/{len(segments)} ({start:.1f}s–{end:.1f}s)")
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(start), "-to", str(end),
                    "-i", path,
                    "-c:v", "libx264", "-c:a", "aac",
                    "-pix_fmt", "yuv420p",
                    clip_path,
                ],
                capture_output=True,
                check=True,
                timeout=120,
            )
            clip_paths.append(clip_path)
            progress.advance(task)

    with open(concat_list_path, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{os.path.abspath(cp)}'\n")

    with _console.status("[cyan]Concatenating clips into final video...[/]"):
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list_path,
                "-c", "copy",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=7200,
        )

    # Clean up temp clips
    for cp in clip_paths:
        Path(cp).unlink(missing_ok=True)
    Path(concat_list_path).unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr}")

    print(f"[compose] Output saved to {output_path}")
    return output_path
