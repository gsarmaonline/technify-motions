# technify-motions

Automatically generate synced visual overlays for technical videos and lectures.

Takes a video or audio file, transcribes it, identifies engineering/technical content, generates animated slides (flowcharts, bullet-point summaries, code snippets), and composes them back into the video — perfectly synced to the timestamp where each concept is explained. Complex scenes get multiple slides, each covering a distinct aspect.

## Pipeline

```
Video/Audio → Audio Extraction → Transcription → Technical Scene Detection
    → Diagram Code Generation → Rendering → Video Composition
```

1. **Extract** — strip audio from video, normalize to 16kHz mono WAV (ffmpeg)
2. **Transcribe** — speech-to-text with timestamps (faster-whisper, runs locally, free)
3. **Classify** — detect technical segments and group into scenes (Claude API)
4. **Generate** — the LLM outputs 1–3 typed slides per scene: flowcharts, bullet-point summaries, or code snippets (Claude API)
5. **Render** — all slides are animated via Remotion (nodes spring in, bullets slide in, code reveals line-by-line)
6. **Compose** — overlay diagram clips on the original video at exact timestamps (ffmpeg)

## Requirements

### System tools

```bash
brew install ffmpeg python@3.12 node
```

> **Note:** Node.js is required for [Remotion](https://www.remotion.dev/), which renders all animated diagram videos. npm dependencies inside `pipeline/remotion_render/` are installed automatically on the first run.

### Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### API key

```bash
export ANTHROPIC_API_KEY=your-key-here
```

Get a key at [console.anthropic.com](https://console.anthropic.com). New accounts include $5 free credit (~25 full 30-minute videos).

## Usage

```bash
source .venv/bin/activate

# Basic — diagram PIP overlay in bottom-right corner
python -m pipeline.main lecture.mp4

# Side-by-side layout
python -m pipeline.main lecture.mp4 --mode side_by_side

# Replace source with diagram during technical segments
python -m pipeline.main lecture.mp4 --mode replace

# Inspect transcript before generating diagrams
python -m pipeline.main lecture.mp4 --dump-transcript only

# Re-use cached transcript and scenes (faster iteration)
python -m pipeline.main lecture.mp4 --use-cache

# Use a larger Whisper model for better accuracy
python -m pipeline.main lecture.mp4 --whisper-model large-v3
```

Intermediate files (transcript JSON, scene JSON, diagram code, rendered PNGs) are saved to `./work/` for inspection.

## Overlay modes

| Mode | Description |
|---|---|
| `pip` | Diagram as picture-in-picture in the bottom-right corner (default) |
| `side_by_side` | Source video left, diagram right |
| `replace` | Diagram replaces the source video during each technical scene |

## Cost

~$0.20 per 30-minute video (Claude API only — all other tools are free and run locally).

## Slide types

Each technical scene can generate 1–3 slides, each of a different type:

| Slide type | When used | Animation |
|---|---|---|
| **Graph** | Flowcharts, architectures, system relationships | Nodes spring into view, edges draw progressively |
| **Bullets** | Key points, trade-offs, summaries, comparisons | Points slide in from the left one by one |
| **Code** | Code snippets, SQL, config, CLI commands | Lines reveal top-to-bottom with syntax highlighting |
