"""FFprobe media inspector and metadata extraction."""
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MediaProbeResult(BaseModel):
    """Metadata extracted from media file via ffprobe."""
    file_path: str
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    has_audio: bool
    audio_codec: Optional[str] = None
    audio_sample_rate: Optional[int] = None
    audio_channels: Optional[int] = None
    file_size_bytes: int


def parse_fps(r_frame_rate: str) -> float:
    """Parse rational frame rate string like '60/1' or '30000/1001' to float."""
    try:
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            den_val = float(den)
            return round(float(num) / den_val, 2) if den_val != 0 else 0.0
        return round(float(r_frame_rate), 2)
    except Exception:
        return 30.0  # Safe fallback default


def probe_media(file_path: Path | str) -> MediaProbeResult:
    """Inspect local media file using ffprobe."""
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Media file not found: {path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json",
        str(path)
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(proc.stdout)
    except subprocess.CalledProcessError as e:
        logger.error("FFprobe execution failed on %s: %s", path, e.stderr)
        raise RuntimeError(f"FFprobe failed to inspect {path}: {e.stderr.strip()}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse FFprobe JSON output for {path}") from e

    format_info = data.get("format", {})
    streams = data.get("streams", [])

    duration = float(format_info.get("duration") or 0.0)
    file_size = int(format_info.get("size") or path.stat().st_size)

    video_stream: Optional[Dict[str, Any]] = None
    audio_stream: Optional[Dict[str, Any]] = None

    for s in streams:
        c_type = s.get("codec_type")
        if c_type == "video" and not video_stream:
            video_stream = s
        elif c_type == "audio" and not audio_stream:
            audio_stream = s

    if not video_stream:
        raise ValueError(f"No video stream found in media file: {path}")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    fps = parse_fps(video_stream.get("r_frame_rate", "30/1"))
    video_codec = str(video_stream.get("codec_name") or "unknown")

    has_audio = audio_stream is not None
    audio_codec = str(audio_stream.get("codec_name")) if audio_stream else None
    audio_sample_rate = int(audio_stream.get("sample_rate")) if audio_stream and audio_stream.get("sample_rate") else None
    audio_channels = int(audio_stream.get("channels")) if audio_stream and audio_stream.get("channels") else None

    return MediaProbeResult(
        file_path=str(path),
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        video_codec=video_codec,
        has_audio=has_audio,
        audio_codec=audio_codec,
        audio_sample_rate=audio_sample_rate,
        audio_channels=audio_channels,
        file_size_bytes=file_size,
    )
