# technify-motions

Automatically generate synced diagram overlays for technical videos and lectures.

Takes a video or audio file, transcribes it, identifies engineering/technical content, generates diagrams (flowcharts, sequence diagrams, architecture diagrams), and composes them back into the video — perfectly synced to the timestamp where each concept is explained.

## Pipeline

```
Video/Audio → Audio Extraction → Transcription → Technical Scene Detection
    → Diagram Code Generation → Rendering → Video Composition
```

1. **Extract** — strip audio from video, normalize to 16kHz mono WAV (ffmpeg)
2. **Transcribe** — speech-to-text with timestamps (faster-whisper, runs locally, free)
3. **Classify** — detect technical segments and group into scenes (Claude API)
4. **Generate** — produce Mermaid or D2 diagram code per scene (Claude API)
5. **Render** — render diagram code to PNG, then to a duration-matched video clip (mmdc / d2 / ffmpeg)
6. **Compose** — overlay diagram clips on the original video at exact timestamps (ffmpeg)

## Requirements

### System tools

```bash
brew install ffmpeg d2 python@3.12
npm install -g @mermaid-js/mermaid-cli
```

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

## Supported diagram types

| Content type | DSL |
|---|---|
| Flowcharts, algorithms, decision trees | Mermaid |
| Service interactions, API flows | Mermaid (sequence) |
| State machines, lifecycles | Mermaid (state) |
| Data models, database schemas | Mermaid (ER) |
| Class hierarchies | Mermaid (class) |
| System/infrastructure architecture | D2 |
