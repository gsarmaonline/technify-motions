"""Generate visual slide content from technical scenes using Claude."""

import json
import os
from pathlib import Path

import anthropic
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from .models import TechnicalScene, Diagram

_GRAPH_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "generate_graph.txt"
_GRAPH_PROMPT_TEMPLATE = _GRAPH_PROMPT_PATH.read_text()

_MODEL = "claude-sonnet-4-6"
_MAX_RETRIES = 3


def generate_diagrams(scenes: list[TechnicalScene]) -> list[Diagram]:
    """Generate one or more visual slides per technical scene."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    diagrams: list[Diagram] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Generating slides...", total=len(scenes))
        for scene in scenes:
            progress.update(
                task,
                description=f"[cyan]Scene {scene.start:.1f}s–{scene.end:.1f}s ({scene.content_type})",
            )
            slides = _generate_slides(client, scene)
            diagrams.extend(slides)
            progress.advance(task)

    print(f"[generate] Generated {len(diagrams)} slides across {len(scenes)} scenes")
    return diagrams


def _generate_slides(client: anthropic.Anthropic, scene: TechnicalScene) -> list[Diagram]:
    """Ask the LLM for an array of typed slides; return one Diagram per slide."""
    prompt = _GRAPH_PROMPT_TEMPLATE.replace("{transcript_text}", scene.text)
    last_error = ""

    for attempt in range(1, _MAX_RETRIES + 1):
        p = prompt
        if last_error:
            p += f"\n\nYour previous attempt was invalid: {last_error}\nPlease fix it."

        print(f"[generate] Scene {scene.start:.1f}s-{scene.end:.1f}s ({scene.content_type}), attempt {attempt}...")

        message = client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": p}],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

        try:
            slides = json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            print(f"[generate] JSON parse failed (attempt {attempt}): {e}")
            continue

        if not isinstance(slides, list) or len(slides) == 0:
            last_error = "response must be a non-empty JSON array"
            continue

        errors = []
        for idx, slide in enumerate(slides):
            ok, err = _validate_slide(slide, idx)
            if not ok:
                errors.append(err)
        if errors:
            last_error = "; ".join(errors)
            print(f"[generate] Slide validation failed (attempt {attempt}): {last_error}")
            continue

        # Time-slice the scene evenly across slides
        n = len(slides)
        slice_dur = scene.duration / n
        result = []
        for idx, slide in enumerate(slides):
            result.append(Diagram(
                scene=scene,
                diagram_dsl="remotion",
                code=json.dumps(slide),
                graph_data=slide,
                slide_start=scene.start + idx * slice_dur,
                slide_end=scene.start + (idx + 1) * slice_dur,
            ))
        return result

    print(f"[generate] Failed to generate slides for scene {scene.start:.1f}s after {_MAX_RETRIES} attempts")
    return []


def _validate_slide(slide: dict, idx: int) -> tuple[bool, str]:
    """Validate one slide object depending on its type."""
    if not isinstance(slide, dict):
        return False, f"slides[{idx}] is not an object"
    slide_type = slide.get("type")
    if slide_type == "graph":
        return _validate_graph(slide, idx)
    elif slide_type == "bullets":
        return _validate_bullets(slide, idx)
    elif slide_type == "code":
        return _validate_code(slide, idx)
    else:
        return False, f"slides[{idx}] has unknown type '{slide_type}'"


def _validate_graph(slide: dict, idx: int) -> tuple[bool, str]:
    nodes = slide.get("nodes")
    if not isinstance(nodes, list) or len(nodes) == 0:
        return False, f"slides[{idx}] graph: 'nodes' must be a non-empty array"
    valid_shapes = {"box", "diamond", "circle", "rounded"}
    node_ids = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            return False, f"slides[{idx}] nodes[{i}] is not an object"
        if not isinstance(n.get("id"), str) or not n["id"].strip():
            return False, f"slides[{idx}] nodes[{i}] missing string 'id'"
        if not isinstance(n.get("label"), str):
            return False, f"slides[{idx}] nodes[{i}] missing string 'label'"
        if n.get("shape", "box") not in valid_shapes:
            return False, f"slides[{idx}] nodes[{i}] unknown shape '{n.get('shape')}'"
        node_ids.add(n["id"])
    edges = slide.get("edges", [])
    if not isinstance(edges, list):
        return False, f"slides[{idx}] graph: 'edges' must be an array"
    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            return False, f"slides[{idx}] edges[{i}] is not an object"
        if e.get("from") not in node_ids:
            return False, f"slides[{idx}] edges[{i}].from '{e.get('from')}' is not a known node id"
        if e.get("to") not in node_ids:
            return False, f"slides[{idx}] edges[{i}].to '{e.get('to')}' is not a known node id"
    return True, ""


def _validate_bullets(slide: dict, idx: int) -> tuple[bool, str]:
    if not isinstance(slide.get("title"), str):
        return False, f"slides[{idx}] bullets: missing string 'title'"
    points = slide.get("points")
    if not isinstance(points, list) or len(points) == 0:
        return False, f"slides[{idx}] bullets: 'points' must be a non-empty array"
    for i, p in enumerate(points):
        if not isinstance(p, str):
            return False, f"slides[{idx}] points[{i}] is not a string"
    return True, ""


def _validate_code(slide: dict, idx: int) -> tuple[bool, str]:
    if not isinstance(slide.get("title"), str):
        return False, f"slides[{idx}] code: missing string 'title'"
    if not isinstance(slide.get("code"), str):
        return False, f"slides[{idx}] code: missing string 'code'"
    valid_langs = {"python", "sql", "bash", "javascript", "go", "yaml", "text"}
    if slide.get("language", "text") not in valid_langs:
        return False, f"slides[{idx}] code: unknown language '{slide.get('language')}'"
    return True, ""
