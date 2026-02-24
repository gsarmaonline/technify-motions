"""Generate diagram code from technical scenes using Claude."""

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
    """Generate diagram code for each technical scene."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    diagrams: list[Diagram] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Generating diagrams...", total=len(scenes))
        for scene in scenes:
            progress.update(
                task,
                description=f"[cyan]Scene {scene.start:.1f}s–{scene.end:.1f}s ({scene.content_type})",
            )
            diagram = _generate_graph_json(client, scene)
            if diagram:
                diagrams.append(diagram)
            progress.advance(task)

    print(f"[generate] Generated {len(diagrams)}/{len(scenes)} diagrams successfully")
    return diagrams


# ── Remotion-native JSON path ─────────────────────────────────────────────────

def _generate_graph_json(client: anthropic.Anthropic, scene: TechnicalScene) -> Diagram | None:
    """Ask the LLM to output {nodes, edges, title} JSON directly for Remotion."""
    prompt = _GRAPH_PROMPT_TEMPLATE.replace("{transcript_text}", scene.text)
    last_error = ""

    for attempt in range(1, _MAX_RETRIES + 1):
        p = prompt
        if last_error:
            p += f"\n\nYour previous attempt was invalid: {last_error}\nPlease fix it."

        print(f"[generate] Scene {scene.start:.1f}s-{scene.end:.1f}s ({scene.content_type}), attempt {attempt} [remotion JSON]...")

        message = client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": p}],
        )

        raw = message.content[0].text.strip()
        # Strip markdown fences if the model adds them despite instructions
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

        try:
            graph_data = json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            print(f"[generate] JSON parse failed (attempt {attempt}): {e}")
            continue

        ok, error = _validate_graph_data(graph_data)
        if ok:
            return Diagram(
                scene=scene,
                diagram_dsl="remotion",
                code=json.dumps(graph_data),
                graph_data=graph_data,
            )
        last_error = error
        print(f"[generate] Graph validation failed (attempt {attempt}): {error}")

    print(f"[generate] Failed to generate valid graph JSON for scene {scene.start:.1f}s after {_MAX_RETRIES} attempts")
    return None


def _validate_graph_data(data: dict) -> tuple[bool, str]:
    """Validate the {nodes, edges} structure the LLM returned."""
    if not isinstance(data, dict):
        return False, "top-level value is not an object"
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or len(nodes) == 0:
        return False, "'nodes' must be a non-empty array"
    valid_shapes = {"box", "diamond", "circle", "rounded"}
    node_ids = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            return False, f"nodes[{i}] is not an object"
        if not isinstance(n.get("id"), str) or not n["id"].strip():
            return False, f"nodes[{i}] missing string 'id'"
        if not isinstance(n.get("label"), str):
            return False, f"nodes[{i}] missing string 'label'"
        if n.get("shape", "box") not in valid_shapes:
            return False, f"nodes[{i}] has unknown shape '{n.get('shape')}'"
        node_ids.add(n["id"])
    edges = data.get("edges", [])
    if not isinstance(edges, list):
        return False, "'edges' must be an array"
    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            return False, f"edges[{i}] is not an object"
        if e.get("from") not in node_ids:
            return False, f"edges[{i}].from '{e.get('from')}' is not a known node id"
        if e.get("to") not in node_ids:
            return False, f"edges[{i}].to '{e.get('to')}' is not a known node id"
    return True, ""


