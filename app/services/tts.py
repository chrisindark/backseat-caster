"""Text-to-speech synthesis and CTA audio assembly for branded outros.

Uses ``edge-tts`` for neural voice synthesis. Every result is cached by an
MD5 key (voice + text) under ``data/channel/tts_cache/`` so repeated renders
never hit the network twice. Offline or failed synthesis degrades to a silent
placeholder so a render never breaks because of TTS.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-ChristopherNeural"
DEFAULT_SPEECH_TEXT = "Subscribe to the channel and tap the bell for more clips."
BELL_SEARCH_PATHS = (
    Path("data/bell_chime.wav"),
    Path("data/audio/bell_chime.wav"),
    Path("app/assets/audio/bell_chime.wav"),
)


def _cache_dir() -> Path:
    path = Path("data/channel/tts_cache")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _md5_key(text: str, voice: str) -> str:
    return hashlib.md5(f"{voice}::{text}".encode()).hexdigest()


def _find_bell() -> Path | None:
    for candidate in BELL_SEARCH_PATHS:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


class TTSService:
    """Neural TTS with deterministic caching and bell-chime mixing."""

    @classmethod
    async def synthesize_speech(
        cls, text: str, voice: str = DEFAULT_VOICE
    ) -> Path | None:
        """Synthesise ``text`` to a cached MP3, returning its path or None."""
        text = (text or "").strip()
        if not text:
            return None

        cache_dir = _cache_dir()
        key = _md5_key(text, voice)
        cached = cache_dir / f"{key}.mp3"
        if cached.exists() and cached.stat().st_size > 0:
            return cached

        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(cached))
            if cached.exists() and cached.stat().st_size > 0:
                logger.info("Synthesised TTS clip -> %s", cached)
                return cached
        except Exception as exc:  # network, quota, or library failure
            logger.warning("TTS synthesis failed (%s); degrading to silence", exc)
            try:
                cached.unlink(missing_ok=True)
            except OSError:
                pass
        return None

    @classmethod
    def synthesize_speech_sync(
        cls, text: str, voice: str = DEFAULT_VOICE
    ) -> Path | None:
        """Synchronous wrapper around :meth:`synthesize_speech`."""
        try:
            return asyncio.run(cls.synthesize_speech(text, voice))
        except RuntimeError:
            # Already inside an event loop; run in a fresh loop on a thread.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, cls.synthesize_speech(text, voice))
                return future.result()

    @classmethod
    def _silent_wav(cls, duration_seconds: float, target: Path) -> Path:
        """Write a silent WAV placeholder so renders never break offline."""
        import wave

        frames = int(max(0.5, duration_seconds) * 48000)
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            wav.writeframes(b"\x00\x00" * frames * 2)
        return target

    @classmethod
    def generate_cta_audio(
        cls,
        speech_text: str,
        voice: str = DEFAULT_VOICE,
        include_bell: bool = True,
        bell_offset_seconds: float = 1.5,
        bell_volume: float = 0.7,
    ) -> Path | None:
        """Return a ready-to-mux WAV combining speech and the bell chime.

        Returns ``None`` when synthesis is unavailable; callers should then
        skip CTA audio rather than fail the render.
        """
        speech_text = (speech_text or "").strip() or DEFAULT_SPEECH_TEXT
        cache_dir = _cache_dir()
        key = _md5_key(
            f"{speech_text}|bell={include_bell}|{bell_offset_seconds}", voice
        )
        cached = cache_dir / f"{key}_cta.wav"
        if cached.exists() and cached.stat().st_size > 0:
            return cached

        speech_path = cls.synthesize_speech_sync(speech_text, voice)
        bell_path = _find_bell() if include_bell else None

        # Offline / failure fallback: a silent placeholder of a sensible length.
        if speech_path is None:
            estimated = max(2.0, len(speech_text) / 14.0)
            if include_bell:
                estimated = max(estimated, bell_offset_seconds + 1.5)
            logger.warning("TTS unavailable; writing silent CTA placeholder")
            return cls._silent_wav(estimated, cached)

        # No bell available: just transcode the speech to WAV.
        if bell_path is None or not include_bell:
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(speech_path),
                        "-ar",
                        "48000",
                        "-ac",
                        "2",
                        str(cached),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if cached.exists() and cached.stat().st_size > 0:
                    return cached
            except Exception as exc:
                logger.warning("Speech transcode failed (%s)", exc)
            return cls._silent_wav(3.0, cached)

        # Mix speech + bell chime (bell delayed by bell_offset_seconds).
        try:
            delay_ms = int(round(bell_offset_seconds * 1000))
            filter_complex = (
                f"[1:a]adelay={delay_ms}|{delay_ms},volume={bell_volume:.2f}[bell];"
                f"[0:a][bell]amix=inputs=2:duration=longest:dropout_transition=2,"
                f"apad=pad_dur=6,atrim=duration=6,"
                f"loudnorm=I=-14:TP=-1.5:LRA=11[a_out]"
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(speech_path),
                    "-i",
                    str(bell_path),
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[a_out]",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    str(cached),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if cached.exists() and cached.stat().st_size > 0:
                logger.info("Assembled CTA audio -> %s", cached)
                return cached
        except Exception as exc:
            logger.warning(
                "CTA audio mix failed (%s); falling back to speech only", exc
            )
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(speech_path),
                        "-ar",
                        "48000",
                        "-ac",
                        "2",
                        str(cached),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if cached.exists() and cached.stat().st_size > 0:
                    return cached
            except Exception:
                pass
        return cls._silent_wav(3.0, cached)
