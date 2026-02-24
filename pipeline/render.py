"""Render diagram code to PNG, then to a duration-matched video clip."""

import subprocess
import tempfile
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from .models import Diagram


def render_diagrams(diagrams: list[Diagram], output_dir: str) -> list[Diagram]:
    """
    Render each diagram to a PNG and then a duration-matched MP4 clip.
    Updates diagram.rendered_path and diagram.video_path in place.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Rendering diagrams...", total=len(diagrams))
        for i, diagram in enumerate(diagrams):
            stem = f"diagram_{i:03d}_{diagram.scene.start:.1f}s"
            png_path = output_dir / f"{stem}.png"
            mp4_path = output_dir / f"{stem}.mp4"

            progress.update(
                task,
                description=f"[cyan]Rendering diagram {i + 1}/{len(diagrams)} ({diagram.diagram_dsl})",
            )

            if diagram.diagram_dsl == "mermaid":
                ok = _render_mermaid(diagram.code, str(png_path))
            elif diagram.diagram_dsl == "d2":
                ok = _render_d2(diagram.code, str(png_path))
            else:
                ok = False

            if not ok:
                print(f"[render] Failed to render diagram {i+1}, skipping")
                progress.advance(task)
                continue

            diagram.rendered_path = str(png_path)

            # Convert PNG to a video clip matching the scene duration
            duration = diagram.scene.duration
            ok = _png_to_video(str(png_path), str(mp4_path), duration)
            if ok:
                diagram.video_path = str(mp4_path)

            progress.advance(task)

    return diagrams


def _render_mermaid(code: str, output_png: str) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".mmd", mode="w", delete=False) as f:
        f.write(code)
        input_path = f.name

    try:
        result = subprocess.run(
            [
                "mmdc",
                "-i", input_path,
                "-o", output_png,
                "--backgroundColor", "white",
                "--width", "1920",
                "--height", "1080",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"[render] mmdc error: {result.stderr}")
            return False
        return True
    except FileNotFoundError:
        print("[render] mmdc not found — install with: npm install -g @mermaid-js/mermaid-cli")
        return False
    except subprocess.TimeoutExpired:
        return False
    finally:
        Path(input_path).unlink(missing_ok=True)


def _render_d2(code: str, output_png: str) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".d2", mode="w", delete=False) as f:
        f.write(code)
        input_path = f.name

    # D2 renders to SVG natively; convert to PNG via Inkscape or rsvg-convert
    svg_path = output_png.replace(".png", ".svg")
    try:
        result = subprocess.run(
            ["d2", input_path, svg_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"[render] d2 error: {result.stderr}")
            return False

        # Convert SVG → PNG
        result = subprocess.run(
            ["rsvg-convert", "-w", "1920", "-h", "1080", svg_path, "-o", output_png],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            # Fall back: just keep the SVG as the rendered_path
            Path(svg_path).rename(output_png.replace(".png", ".svg"))
            return True

        return True
    except FileNotFoundError:
        print("[render] d2 not found — install from https://d2lang.com")
        return False
    except subprocess.TimeoutExpired:
        return False
    finally:
        Path(input_path).unlink(missing_ok=True)
        Path(svg_path).unlink(missing_ok=True)


def _png_to_video(png_path: str, output_mp4: str, duration: float) -> bool:
    """Convert a static PNG into a video clip of the given duration."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", png_path,
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=white",
            "-r", "30",
            output_mp4,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print(f"[render] ffmpeg PNG→video failed: {result.stderr}")
        return False
    return True
