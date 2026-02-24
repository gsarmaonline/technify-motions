"""CLI entrypoint for the technify-motions pipeline."""

import argparse
import json
import os
import sys
from pathlib import Path

from .extract import extract_audio
from .transcribe import transcribe, segments_to_text
from .classify import classify_scenes
from .generate import generate_diagrams
from .render import render_diagrams
from .compose import compose_video


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    output_path = args.output or str(input_path.parent / f"{input_path.stem}_technified.mp4")

    print(f"\n=== technify-motions pipeline ===")
    print(f"Input:   {input_path}")
    print(f"Output:  {output_path}")
    print(f"Mode:    {args.mode}")
    print(f"Work dir: {work_dir}\n")

    # ── Stage 1: Extract audio ──────────────────────────────────────────────
    print("── Stage 1: Audio extraction ──")
    audio_path = extract_audio(str(input_path), str(work_dir / "audio"))

    # ── Stage 2: Transcribe ─────────────────────────────────────────────────
    print("\n── Stage 2: Transcription ──")
    transcript_cache = work_dir / "transcript.json"

    if args.use_cache and transcript_cache.exists():
        print(f"[transcribe] Loading cached transcript from {transcript_cache}")
        from .models import TranscriptSegment
        data = json.loads(transcript_cache.read_text())
        segments = [TranscriptSegment(**s) for s in data]
    else:
        segments = transcribe(audio_path, model_size=args.whisper_model, language=args.language)
        transcript_cache.write_text(json.dumps([vars(s) for s in segments], indent=2))
        print(f"[transcribe] Transcript cached to {transcript_cache}")

    if args.dump_transcript:
        print("\n── Transcript ──")
        print(segments_to_text(segments))
        if args.dump_transcript == "only":
            return

    # ── Stage 3: Classify technical scenes ─────────────────────────────────
    print("\n── Stage 3: Technical scene classification ──")
    scenes_cache = work_dir / "scenes.json"

    if args.use_cache and scenes_cache.exists():
        print(f"[classify] Loading cached scenes from {scenes_cache}")
        from .models import TechnicalScene, TranscriptSegment
        raw_scenes = json.loads(scenes_cache.read_text())
        scenes = []
        for rs in raw_scenes:
            scene_segs = [TranscriptSegment(**s) for s in rs.pop("segments")]
            scenes.append(TechnicalScene(segments=scene_segs, **rs))
    else:
        scenes = classify_scenes(segments)
        serializable = []
        for sc in scenes:
            d = {"start": sc.start, "end": sc.end, "content_type": sc.content_type,
                 "description": sc.description, "segments": [vars(s) for s in sc.segments]}
            serializable.append(d)
        scenes_cache.write_text(json.dumps(serializable, indent=2))

    print(f"\nTechnical scenes found: {len(scenes)}")
    for sc in scenes:
        print(f"  [{sc.start:.1f}s - {sc.end:.1f}s] {sc.content_type}: {sc.description}")

    if not scenes:
        print("\nNo technical scenes detected — nothing to visualize.")
        return

    # ── Stage 4: Generate diagram code ─────────────────────────────────────
    print("\n── Stage 4: Diagram code generation ──")
    diagrams = generate_diagrams(scenes)

    # Save generated code for inspection
    diagrams_dir = work_dir / "diagrams"
    diagrams_dir.mkdir(exist_ok=True)
    for i, d in enumerate(diagrams):
        ext = "mmd" if d.diagram_dsl == "mermaid" else "d2"
        code_path = diagrams_dir / f"diagram_{i:03d}.{ext}"
        code_path.write_text(d.code)

    # ── Stage 5: Render diagrams ────────────────────────────────────────────
    print("\n── Stage 5: Rendering diagrams ──")
    diagrams = render_diagrams(diagrams, str(diagrams_dir))

    rendered = [d for d in diagrams if d.video_path]
    print(f"Successfully rendered: {len(rendered)}/{len(diagrams)}")

    if not rendered:
        print("\nNo diagrams rendered successfully. Check that mmdc/d2 are installed.")
        return

    # ── Stage 6: Compose final video ────────────────────────────────────────
    print("\n── Stage 6: Video composition ──")
    compose_video(
        source_video=str(input_path),
        diagrams=rendered,
        output_path=output_path,
        mode=args.mode,
    )

    print(f"\n✓ Done! Output: {output_path}")


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
