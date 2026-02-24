"""Transcription with word-level timestamps using faster-whisper."""

from faster_whisper import WhisperModel
from .models import TranscriptSegment


# Model sizes: tiny, base, small, medium, large-v2, large-v3
# large-v3 = best quality, needs ~6GB VRAM or runs slowly on CPU
# small = good balance for CPU-only
_DEFAULT_MODEL = "small"


def transcribe(
    audio_path: str,
    model_size: str = _DEFAULT_MODEL,
    language: str | None = None,
    device: str = "auto",
) -> list[TranscriptSegment]:
    """
    Transcribe audio and return segments with timestamps.

    Args:
        audio_path: Path to a WAV/MP3/etc. audio file.
        model_size: Whisper model size to use.
        language: Force a language code (e.g. "en"), or None to auto-detect.
        device: "auto", "cpu", or "cuda".

    Returns:
        List of TranscriptSegment with start/end in seconds.
    """
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    compute_type = "float16" if device == "cuda" else "int8"

    print(f"[transcribe] Loading Whisper model '{model_size}' on {device}...")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    print(f"[transcribe] Transcribing {audio_path}...")
    segments_iter, info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        vad_filter=True,          # skip silence
        vad_parameters={"min_silence_duration_ms": 500},
    )

    print(f"[transcribe] Detected language: {info.language} ({info.language_probability:.0%})")

    segments: list[TranscriptSegment] = []
    for seg in segments_iter:
        segments.append(TranscriptSegment(
            start=seg.start,
            end=seg.end,
            text=seg.text.strip(),
        ))

    print(f"[transcribe] {len(segments)} segments extracted")
    return segments


def segments_to_text(segments: list[TranscriptSegment]) -> str:
    return "\n".join(f"[{s.start:.1f}s - {s.end:.1f}s] {s.text}" for s in segments)
