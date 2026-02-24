"""CLI entrypoint for the technify-motions pipeline."""

import argparse
import json
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from .extract import extract_audio
from .transcribe import transcribe, segments_to_text
from .classify import classify_scenes
from .generate import generate_diagrams
from .models import Diagram
from .render import render_diagrams
from .compose import compose_video

_console = Console()


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        _console.print(f"[red]Error:[/] input file not found: {input_path}")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        _console.print("[red]Error:[/] ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    output_path = args.output or str(input_path.parent / f"{input_path.stem}_technified.mp4")

    _console.print(Panel.fit(
        f"[bold]Input:[/]    {input_path}\n"
        f"[bold]Output:[/]   {output_path}\n"
        f"[bold]Mode:[/]     {args.mode}\n"
        f"[bold]Work dir:[/] {work_dir}",
        title="[bold cyan]technify-motions pipeline[/]",
    ))
    _console.print()

    # ── Stage 1: Extract audio ──────────────────────────────────────────────
    with _console.status("[cyan][1/6] Extracting audio...[/]"):
        audio_path = extract_audio(str(input_path), str(work_dir / "audio"))
    _console.print("[green]✓[/] [bold][1/6][/] Audio extraction complete")

    # ── Stage 2: Transcribe ─────────────────────────────────────────────────
    transcript_cache = work_dir / "transcript.json"

    if args.use_cache and transcript_cache.exists():
        with _console.status("[cyan][2/6] Loading cached transcript...[/]"):
            from .models import TranscriptSegment
            data = json.loads(transcript_cache.read_text())
            segments = [TranscriptSegment(**s) for s in data]
        _console.print(f"[green]✓[/] [bold][2/6][/] Transcript loaded from cache ({len(segments)} segments)")
    else:
        _console.print("[cyan][2/6] Transcribing audio...[/]")
        segments = transcribe(audio_path, model_size=args.whisper_model, language=args.language)
        transcript_cache.write_text(json.dumps([vars(s) for s in segments], indent=2))
        _console.print(f"[green]✓[/] [bold][2/6][/] Transcription complete ({len(segments)} segments)")

    if args.dump_transcript:
        _console.print("\n── Transcript ──")
        _console.print(segments_to_text(segments))
        if args.dump_transcript == "only":
            return

    # ── Stage 3: Classify technical scenes ─────────────────────────────────
    scenes_cache = work_dir / "scenes.json"

    if args.use_cache and scenes_cache.exists():
        with _console.status("[cyan][3/6] Loading cached scenes...[/]"):
            from .models import TechnicalScene, TranscriptSegment
            raw_scenes = json.loads(scenes_cache.read_text())
            scenes = []
            for rs in raw_scenes:
                scene_segs = [TranscriptSegment(**s) for s in rs.pop("segments")]
                scenes.append(TechnicalScene(segments=scene_segs, **rs))
        _console.print(f"[green]✓[/] [bold][3/6][/] Scenes loaded from cache ({len(scenes)} scenes)")
    else:
        with _console.status("[cyan][3/6] Classifying technical scenes...[/]"):
            scenes = classify_scenes(segments)
            serializable = []
            for sc in scenes:
                d = {"start": sc.start, "end": sc.end, "content_type": sc.content_type,
                     "description": sc.description, "segments": [vars(s) for s in sc.segments]}
                serializable.append(d)
            scenes_cache.write_text(json.dumps(serializable, indent=2))
        _console.print(f"[green]✓[/] [bold][3/6][/] Scene classification complete ({len(scenes)} scenes)")

    for sc in scenes:
        _console.print(f"  [dim][{sc.start:.1f}s - {sc.end:.1f}s] {sc.content_type}: {sc.description}[/]")

    if not scenes:
        _console.print("\n[yellow]No technical scenes detected — nothing to visualize.[/]")
        return

    # ── Stage 4: Generate diagram code ─────────────────────────────────────
    diagrams_dir = work_dir / "diagrams"
    diagrams_dir.mkdir(exist_ok=True)
    diagrams_cache = work_dir / "diagrams.json"

    if args.use_cache and diagrams_cache.exists():
        with _console.status("[cyan][4/6] Loading cached diagrams...[/]"):
            raw = json.loads(diagrams_cache.read_text())
            diagrams = []
            for entry in raw:
                scene = scenes[entry["scene_index"]]
                code_path = diagrams_dir / entry["code_file"]
                code = code_path.read_text() if code_path.exists() else entry["code"]
                diagrams.append(Diagram(
                    scene=scene,
                    diagram_dsl=entry["dsl"],
                    code=code,
                    graph_data=entry.get("graph_data"),
                    slide_start=entry.get("slide_start"),
                    slide_end=entry.get("slide_end"),
                ))
        _console.print(f"[green]✓[/] [bold][4/6][/] Diagrams loaded from cache ({len(diagrams)} diagrams)")
    else:
        _console.print("[cyan][4/6] Generating diagram code...[/]")
        diagrams = generate_diagrams(scenes)
        cache_entries = []
        for i, d in enumerate(diagrams):
            code_file = f"diagram_{i:03d}.json"
            (diagrams_dir / code_file).write_text(d.code)
            entry: dict = {
                "scene_index": scenes.index(d.scene),
                "dsl": d.diagram_dsl,
                "code_file": code_file,
                "code": d.code,
            }
            if d.graph_data is not None:
                entry["graph_data"] = d.graph_data
            if d.slide_start is not None:
                entry["slide_start"] = d.slide_start
            if d.slide_end is not None:
                entry["slide_end"] = d.slide_end
            cache_entries.append(entry)
        diagrams_cache.write_text(json.dumps(cache_entries, indent=2))
        _console.print(f"[green]✓[/] [bold][4/6][/] Diagram generation complete ({len(diagrams)} slides across {len(scenes)} scenes)")

    # ── Stage 5: Render diagrams ────────────────────────────────────────────
    _console.print("[cyan][5/6] Rendering diagrams...[/]")
    diagrams = render_diagrams(diagrams, str(diagrams_dir), use_cache=args.use_cache)

    rendered = [d for d in diagrams if d.video_path]
    _console.print(f"[green]✓[/] [bold][5/6][/] Rendering complete ({len(rendered)}/{len(diagrams)} succeeded)")

    if not rendered:
        _console.print("\n[yellow]No diagrams rendered successfully. Check that mmdc/d2 are installed.[/]")
        return

    # ── Stage 6: Compose final video ────────────────────────────────────────
    _console.print("[cyan][6/6] Composing final video...[/]")
    compose_video(
        source_video=str(input_path),
        diagrams=rendered,
        output_path=output_path,
        mode=args.mode,
    )
    _console.print(f"[green]✓[/] [bold][6/6][/] Video composition complete")

    _console.print(f"\n[bold green]✓ Done![/] Output: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="technify-motions: auto-generate diagram overlays for technical videos"
    )
    parser.add_argument("input", help="Input video or audio file")
    parser.add_argument("-o", "--output", help="Output video path (default: <input>_technified.mp4)")
    parser.add_argument(
        "--mode",
        choices=["pip", "side_by_side", "replace"],
        default="pip",
        help="Diagram overlay mode (default: pip)",
    )
    parser.add_argument(
        "--whisper-model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        help="Whisper model size (default: small)",
    )
    parser.add_argument("--language", help="Force transcript language (e.g. 'en'). Auto-detect if omitted.")
    parser.add_argument("--work-dir", default="./work", help="Directory for intermediate files (default: ./work)")
    parser.add_argument("--dump-transcript", choices=["print", "only"], help="Print the transcript after stage 2")
    parser.add_argument("--use-cache", action="store_true", help="Reuse cached transcript/scenes from a previous run")

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
