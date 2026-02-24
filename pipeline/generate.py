"""Generate diagram code from technical scenes using Claude."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import anthropic
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from .models import TechnicalScene, Diagram

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "generate.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()

_MODEL = "claude-sonnet-4-6"
_MAX_RETRIES = 3

# Which content types map to which DSL
_CONTENT_TYPE_TO_DSL: dict[str, str] = {
    "flowchart":    "mermaid",
    "sequence":     "mermaid",
    "state":        "mermaid",
    "er":           "mermaid",
    "class":        "mermaid",
    "architecture": "d2",
}


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
            dsl = _CONTENT_TYPE_TO_DSL.get(scene.content_type, "mermaid")
            diagram = _generate_with_retry(client, scene, dsl)
            if diagram:
                diagrams.append(diagram)
            progress.advance(task)

    print(f"[generate] Generated {len(diagrams)}/{len(scenes)} diagrams successfully")
    return diagrams


def _generate_with_retry(
    client: anthropic.Anthropic,
    scene: TechnicalScene,
    dsl: str,
    error_feedback: str = "",
) -> Diagram | None:
    last_error = ""
    for attempt in range(1, _MAX_RETRIES + 1):
        prompt = _PROMPT_TEMPLATE.replace("{transcript_text}", scene.text)
        prompt = prompt.replace("{diagram_dsl}", dsl)

        if last_error:
            prompt += f"\n\nYour previous attempt failed validation with this error:\n{last_error}\nPlease fix it."

        print(f"[generate] Scene {scene.start:.1f}s-{scene.end:.1f}s ({scene.content_type}), attempt {attempt}...")

        message = client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        code = message.content[0].text.strip()
        # Strip markdown fences if present
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

        valid, error = _validate_diagram(dsl, code)
        if valid:
            graph_data = None
            if dsl == "mermaid" and _is_flowchart(code):
                graph_data = _parse_mermaid_to_graph(code)
            return Diagram(scene=scene, diagram_dsl=dsl, code=code, graph_data=graph_data)

        last_error = error
        print(f"[generate] Validation failed (attempt {attempt}): {error}")

    print(f"[generate] Failed to generate valid diagram for scene {scene.start:.1f}s after {_MAX_RETRIES} attempts")
    return None


def _validate_diagram(dsl: str, code: str) -> tuple[bool, str]:
    """Try to render the diagram code to validate syntax. Returns (ok, error_message)."""
    if dsl == "mermaid":
        return _validate_mermaid(code)
    elif dsl == "d2":
        return _validate_d2(code)
    return True, ""


def _validate_mermaid(code: str) -> tuple[bool, str]:
    """Validate Mermaid code by attempting a dry-run render with mmdc."""
    with tempfile.NamedTemporaryFile(suffix=".mmd", mode="w", delete=False) as f:
        f.write(code)
        input_path = f.name

    output_path = input_path.replace(".mmd", "_check.png")
    try:
        result = subprocess.run(
            ["mmdc", "-i", input_path, "-o", output_path, "--quiet"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout).strip()
        return True, ""
    except FileNotFoundError:
        # mmdc not installed — skip validation, trust the LLM
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "render timed out"
    finally:
        Path(input_path).unlink(missing_ok=True)
        Path(output_path).unlink(missing_ok=True)


def _validate_d2(code: str) -> tuple[bool, str]:
    """Validate D2 code by attempting a dry-run render."""
    with tempfile.NamedTemporaryFile(suffix=".d2", mode="w", delete=False) as f:
        f.write(code)
        input_path = f.name

    output_path = input_path.replace(".d2", "_check.svg")
    try:
        result = subprocess.run(
            ["d2", input_path, output_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout).strip()
        return True, ""
    except FileNotFoundError:
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "render timed out"
    finally:
        Path(input_path).unlink(missing_ok=True)
        Path(output_path).unlink(missing_ok=True)


# ── Mermaid flowchart → graph JSON ───────────────────────────────────────────

_FLOWCHART_HEADER = re.compile(r"^\s*(flowchart|graph)\s+", re.IGNORECASE)

# Lines to skip outright
_SKIP_LINE = re.compile(
    r"^\s*(?:%%|subgraph|end\s*$|style\s|classDef\s|class\s|click\s|linkStyle)",
    re.IGNORECASE,
)

# Shapes: order matters — check longer patterns first
_SHAPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(\w+)\(\((.+)\)\)$", re.DOTALL), "circle"),      # A((label))
    (re.compile(r"^(\w+)\(\[(.+)\]\)$", re.DOTALL), "box"),          # A([label])
    (re.compile(r"^(\w+)\{(.+)\}$", re.DOTALL), "diamond"),          # A{label}
    (re.compile(r"^(\w+)\[(.+)\]$", re.DOTALL), "box"),              # A[label]
    (re.compile(r"^(\w+)\((.+)\)$", re.DOTALL), "rounded"),          # A(label)
    (re.compile(r"^(\w+)$"), "box"),                                   # A
]

# Arrow separators (various Mermaid styles)
_ARROW_RE = re.compile(r"\s*(?:-->|--[^>]*->|-\.->|==>|---)\s*")

# Label inside arrow: -- some text -->
_ARROW_LABEL_RE = re.compile(r"--([^>-]+)-->")


def _is_flowchart(code: str) -> bool:
    return bool(_FLOWCHART_HEADER.match(code))


def _parse_node_token(token: str) -> tuple[str, str, str] | None:
    """Return (id, label, shape) for a node token, or None if unrecognised."""
    token = token.strip()
    if not token:
        return None
    for pattern, shape in _SHAPE_PATTERNS:
        m = pattern.match(token)
        if m:
            nid = m.group(1).strip()
            label = m.group(2).strip() if pattern.groups >= 2 else nid  # type: ignore[attr-defined]
            return nid, label, shape
    return None


def _parse_mermaid_to_graph(code: str) -> dict:
    """
    Parse a Mermaid flowchart into {nodes, edges} suitable for Remotion.
    Handles: A --> B, A[x] --> B{y}, A -- label --> B, chained A-->B-->C.
    """
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def ensure_node(token: str) -> str | None:
        result = _parse_node_token(token)
        if result:
            nid, label, shape = result
            if nid not in nodes:
                nodes[nid] = {"id": nid, "label": label, "shape": shape}
            return nid
        return None

    for raw_line in code.splitlines():
        line = raw_line.strip()
        if not line or _SKIP_LINE.match(line) or _FLOWCHART_HEADER.match(line):
            continue

        # Normalise |label| variant: A -->|yes| B  →  A -- yes --> B
        line = re.sub(r"(-->|---)\s*\|([^|]*)\|", r"-- \2 -->", line)

        # Split on any arrow to get node-token pieces
        parts = _ARROW_RE.split(line)
        if len(parts) < 2:
            ensure_node(line)
            continue

        # Extract edge labels from the arrows between parts
        arrow_labels = [m.group(1).strip("- ").strip() for m in _ARROW_LABEL_RE.finditer(line)]

        node_ids: list[str | None] = [ensure_node(p) for p in parts]
        for i in range(len(node_ids) - 1):
            frm, to = node_ids[i], node_ids[i + 1]
            if frm and to:
                label = arrow_labels[i] if i < len(arrow_labels) else ""
                edges.append({"from": frm, "to": to, "label": label})

    return {"nodes": list(nodes.values()), "edges": edges}
