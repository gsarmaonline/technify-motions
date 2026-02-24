"""Render diagram code to PNG, then to a duration-matched video clip."""

import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from .models import Diagram

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg)


def render_diagrams(diagrams: list[Diagram], output_dir: str, max_workers: int = 4, use_cache: bool = False) -> list[Diagram]:
    """
    Render each diagram to a PNG and then a duration-matched MP4 clip.
    Diagrams are rendered in parallel to avoid sequential Chrome launches.
    With use_cache=True, skips diagrams whose MP4 already exists on disk.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(diagrams)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Rendering diagrams...", total=total)

        def render_one(args: tuple) -> None:
            i, diagram = args
            stem = f"diagram_{i:03d}_{diagram.scene.start:.1f}s"
            png_path = output_dir / f"{stem}.png"
            mp4_path = output_dir / f"{stem}.mp4"

            if use_cache and mp4_path.exists():
                diagram.rendered_path = str(png_path) if png_path.exists() else None
                diagram.video_path = str(mp4_path)
                progress.advance(task)
                return

            progress.update(task, description=f"[cyan]Rendering {i+1}/{total} ({diagram.diagram_dsl})")

            if diagram.diagram_dsl == "mermaid":
                ok = _render_mermaid(diagram.code, str(png_path))
            elif diagram.diagram_dsl == "d2":
                ok = _render_d2(diagram.code, str(png_path))
            else:
                ok = False

            if not ok:
                _log(f"[render] Failed to render diagram {i+1}, skipping")
                progress.advance(task)
                return

            diagram.rendered_path = str(png_path)

            duration = diagram.scene.duration
            ok = _png_to_video(str(png_path), str(mp4_path), duration)
            if ok:
                diagram.video_path = str(mp4_path)
                _log(f"[render] Diagram {i+1} done → {mp4_path.name} ({duration:.1f}s)")

            progress.advance(task)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(render_one, (i, d)) for i, d in enumerate(diagrams)]
            for f in as_completed(futures):
                f.result()  # re-raise any exceptions

    return diagrams


_MERMAID_CONFIG = '{"fontSize":20,"wrap":true}'


def _render_mermaid(code: str, output_png: str) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".mmd", mode="w", delete=False) as f:
        f.write(code)
        input_path = f.name

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as cf:
        cf.write(_MERMAID_CONFIG)
        config_path = cf.name

    try:
        result = subprocess.run(
            [
                "mmdc",
                "-i", input_path,
                "-o", output_png,
                "--backgroundColor", "white",
                "--width", "3840",   # render at 4K width so fonts stay large after downscale
                "--configFile", config_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            _log(f"[render] mmdc error: {result.stderr}")
            return False
        if not Path(output_png).exists():
            _log("[render] mmdc exited 0 but produced no output file")
            return False
        return True
    except FileNotFoundError:
        _log("[render] mmdc not found — install with: npm install -g @mermaid-js/mermaid-cli")
        return False
    except subprocess.TimeoutExpired:
        return False
    finally:
        Path(input_path).unlink(missing_ok=True)
        Path(config_path).unlink(missing_ok=True)


def _find_bin(name: str) -> str:
    """Find a binary on PATH or common Homebrew locations."""
    found = shutil.which(name)
    if found:
        return found
    for candidate in [f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"]:
        if Path(candidate).exists():
            return candidate
    return name  # fall back to bare name; subprocess will raise FileNotFoundError


def _render_d2(code: str, output_png: str) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".d2", mode="w", delete=False) as f:
        f.write(code)
        input_path = f.name

    d2_bin = _find_bin("d2")

    # --target '' forces d2 to render only the root board as a single file,
    # preventing directory output when reserved keywords (steps/layers/scenarios)
    # appear in the generated code.
    try:
        result = subprocess.run(
            [d2_bin, "--pad", "40", "--scale", "4", "--target", "", input_path, output_png],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            _log(f"[render] d2 error: {result.stderr}")
            return False
        if not Path(output_png).exists():
            _log("[render] d2 exited 0 but produced no output file")
            return False
        return True
    except FileNotFoundError:
        _log(f"[render] d2 not found (tried: {d2_bin}) — install from https://d2lang.com")
        return False
    except subprocess.TimeoutExpired:
        _log("[render] d2 timed out")
        return False
    finally:
        Path(input_path).unlink(missing_ok=True)


def _png_to_video(png_path: str, output_mp4: str, duration: float) -> bool:
    """Convert a static PNG into a video clip of the given duration."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-framerate", "1",          # 1 fps input — only one unique frame anyway
            "-i", png_path,
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",     # fastest encode
            "-tune", "stillimage",      # optimise for static content
            "-r", "5",                  # 5 fps output is plenty for a static diagram
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=white",
            output_mp4,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        _log(f"[render] ffmpeg PNG→video failed: {result.stderr}")
        return False
    return True
