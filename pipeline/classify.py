"""Classify transcript segments into technical scenes using Claude."""

import json
import os
import re
from pathlib import Path

import anthropic

from .models import TranscriptSegment, TechnicalScene

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "classify.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()

_MODEL = "claude-sonnet-4-6"


def _extract_json(text: str) -> list | None:
    """Extract a JSON array from Claude's response, tolerating surrounding prose or fences."""
    # 1. Try parsing the whole response directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract content inside ```...``` fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Find the first [...] array in the response
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def classify_scenes(segments: list[TranscriptSegment]) -> list[TechnicalScene]:
    """
    Identify technical scenes in the transcript using Claude.

    Returns a list of TechnicalScene objects, sorted by start time.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    transcript_text = "\n".join(
        f"[{i}] [{s.start:.1f}s - {s.end:.1f}s] {s.text}"
        for i, s in enumerate(segments)
    )

    prompt = _PROMPT_TEMPLATE.replace("{transcript}", transcript_text)

    print("[classify] Sending transcript to Claude for technical scene detection...")

    message = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    scenes_data = _extract_json(raw)
    if scenes_data is None:
        print(f"[classify] Could not parse Claude response as JSON. Raw response:\n{raw}")
        return []

    scenes: list[TechnicalScene] = []
    for s in scenes_data:
        scene_segments = [segments[i] for i in s["segment_indices"] if i < len(segments)]
        if not scene_segments:
            continue
        scenes.append(TechnicalScene(
            start=s["start"],
            end=s["end"],
            segments=scene_segments,
            content_type=s["content_type"],
            description=s["description"],
        ))

    scenes.sort(key=lambda s: s.start)
    print(f"[classify] Found {len(scenes)} technical scenes")
    return scenes
