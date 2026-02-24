"""Audio extraction from video/audio files using ffmpeg."""

import subprocess
import os
from pathlib import Path


def extract_audio(input_path: str, output_dir: str) -> str:
    """
    Extract audio from a video or audio file, normalized for Whisper.

    Returns path to the extracted 16kHz mono WAV file.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{input_path.stem}_audio.wav"

    # If input is already audio, still normalize it (sample rate, channels, format)
    cmd = [
        "ffmpeg",
        "-y",                    # overwrite output
        "-i", str(input_path),
        "-vn",                   # no video
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", "16000",          # 16kHz sample rate (Whisper's preferred)
        "-ac", "1",              # mono
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed:\n{result.stderr}")

    print(f"[extract] Audio saved to {output_path}")
    return str(output_path)


def get_video_duration(input_path: str) -> float:
    """Return duration of a media file in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{result.stderr}")
    return float(result.stdout.strip())
