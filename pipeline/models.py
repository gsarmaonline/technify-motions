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
    diagram_dsl: str   # "remotion"
    code: str
    rendered_path: Optional[str] = None   # path to PNG/SVG after rendering
    video_path: Optional[str] = None      # path to duration-matched MP4 clip
    graph_data: Optional[dict] = None     # slide payload for Remotion
    slide_start: Optional[float] = None  # overrides scene.start when scene is split
    slide_end: Optional[float] = None    # overrides scene.end when scene is split

    @property
    def start(self) -> float:
        return self.slide_start if self.slide_start is not None else self.scene.start

    @property
    def end(self) -> float:
        return self.slide_end if self.slide_end is not None else self.scene.end

    @property
    def duration(self) -> float:
        return self.end - self.start
