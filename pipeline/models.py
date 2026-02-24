from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranscriptSegment:
    start: float  # seconds
    end: float
    text: str


@dataclass
class TechnicalScene:
    start: float
    end: float
    segments: list[TranscriptSegment]
    content_type: str  # "flowchart", "sequence", "architecture", "state", "er", "class"
    description: str   # brief description of what this scene explains

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Diagram:
    scene: TechnicalScene
    diagram_dsl: str   # "mermaid" or "d2"
    code: str
    rendered_path: Optional[str] = None   # path to PNG/SVG after rendering
    video_path: Optional[str] = None      # path to duration-matched MP4 clip
    graph_data: Optional[dict] = None     # parsed {nodes, edges} for Remotion animation
