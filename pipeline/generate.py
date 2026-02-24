"""Generate diagram code from technical scenes using Claude."""

import os
import subprocess
import tempfile
from pathlib import Path

import anthropic

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

    for scene in scenes:
        dsl = _CONTENT_TYPE_TO_DSL.get(scene.content_type, "mermaid")
        diagram = _generate_with_retry(client, scene, dsl)
        if diagram:
            diagrams.append(diagram)

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
            return Diagram(scene=scene, diagram_dsl=dsl, code=code)

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
