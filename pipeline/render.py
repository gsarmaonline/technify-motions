"""Render diagram code to PNG, then to a duration-matched video clip.

Flowchart diagrams with parsed graph data are rendered via Remotion for a live
"drawing" animation.  All other diagram types fall back to the original
PNG → ffmpeg static-video path.
"""

import json
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
                should_use_remotion = bool(diagram.graph_data and diagram.graph_data.get("nodes"))
                # Remotion renders have no accompanying PNG; static renders do.
                # If a PNG exists alongside the mp4, it was rendered statically and
                # should be re-rendered with Remotion now that graph_data is available.
                already_remotion = should_use_remotion and not png_path.exists()
                if not should_use_remotion or already_remotion:
                    diagram.rendered_path = str(png_path) if png_path.exists() else None
                    diagram.video_path = str(mp4_path)
                    progress.advance(task)
                    return
                # else: has graph_data but was previously rendered statically — fall through to re-render

            duration = diagram.scene.duration

            # ── Try Remotion for flowcharts with parsed graph data ─────────
            if diagram.graph_data and diagram.graph_data.get("nodes"):
                progress.update(
                    task,
                    description=f"[cyan]Remotion {i+1}/{total} ({len(diagram.graph_data['nodes'])} nodes)",
                )
                ok = _render_with_remotion(diagram.graph_data, str(mp4_path), duration)
                if ok:
                    diagram.video_path = str(mp4_path)
                    _log(f"[render] Diagram {i+1} animated via Remotion → {mp4_path.name} ({duration:.1f}s)")
                    progress.advance(task)
                    return
                _log(f"[render] Remotion failed for diagram {i+1}, falling back to static render")

            # ── Static PNG → video fallback ────────────────────────────────
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


# ── Remotion renderer ─────────────────────────────────────────────────────────

_REMOTION_DIR = Path(__file__).parent / "remotion_render"
_remotion_deps_ready: bool = False
_remotion_lock = threading.Lock()


def _ensure_remotion_deps() -> bool:
    """Install npm dependencies for the Remotion project (once per process)."""
    global _remotion_deps_ready
    with _remotion_lock:
        if _remotion_deps_ready:
            return True
        node_modules = _REMOTION_DIR / "node_modules"
        if node_modules.exists():
            _remotion_deps_ready = True
            return True
        _log("[render] Installing Remotion dependencies (first run)…")
        result = subprocess.run(
            ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund"],
            cwd=str(_REMOTION_DIR),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            _log(f"[render] npm install failed:\n{result.stderr}")
            return False
        _remotion_deps_ready = True
        return True


def _render_with_remotion(graph_data: dict, output_mp4: str, duration: float) -> bool:
    """
    Render an animated flowchart video using Remotion.

    Nodes spring-scale into view one by one (top-to-bottom, dagre order).
    Edges are progressively drawn using SVG stroke-dashoffset.
    Duration matches the scene exactly via Remotion's calculateMetadata.
    """
    if not _ensure_remotion_deps():
        return False

    remotion_bin = _REMOTION_DIR / "node_modules" / ".bin" / "remotion"
    if not remotion_bin.exists():
        _log("[render] remotion binary not found after npm install")
        return False

    props = {**graph_data, "durationSeconds": duration}
    props_json = json.dumps(props)

    # Write props to a temp file to avoid shell-length limits on large graphs
    with tempfile.NamedTemporaryFile(
        suffix=".json", mode="w", delete=False, dir=str(_REMOTION_DIR)
    ) as pf:
        pf.write(props_json)
        props_file = pf.name

    abs_output = str(Path(output_mp4).absolute())

    try:
        result = subprocess.run(
            [
                str(remotion_bin),
                "render",
                "src/index.ts",
                "FlowchartAnimation",
                abs_output,
                f"--props={props_file}",
                "--log=error",
                "--concurrency=4",
            ],
            cwd=str(_REMOTION_DIR),
            capture_output=True,
            text=True,
            timeout=360,
        )
        if result.returncode != 0:
            _log(f"[render] Remotion render failed:\n{result.stderr[-2000:]}")
            return False
        if not Path(abs_output).exists():
            _log("[render] Remotion exited 0 but output file missing")
            return False
        return True
    except FileNotFoundError:
        _log("[render] Node.js / remotion binary not found")
        return False
    except subprocess.TimeoutExpired:
        _log("[render] Remotion render timed out")
        return False
    finally:
        Path(props_file).unlink(missing_ok=True)


# ── ffmpeg static fallback ────────────────────────────────────────────────────


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
