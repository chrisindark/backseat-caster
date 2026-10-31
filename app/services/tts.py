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

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-ChristopherNeural"
DEFAULT_SPEECH_TEXT = "Subscribe to the channel and tap the bell for more clips."

#: Bell chime bundled with the app (independent of the process working directory).
BUNDLED_BELL = Path(__file__).resolve().parent.parent / "assets" / "audio" / "bell_chime.wav"


def _cache_dir() -> Path:
    path = settings.channel_assets_path / "tts_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _md5_key(text: str, voice: str) -> str:
    return hashlib.md5(f"{voice}::{text}".encode()).hexdigest()


def _find_bell() -> Path | None:
    """Prefer a creator-supplied chime, then the bundled asset."""
    candidates = (
        settings.channel_assets_path / "bell_chime.wav",
        BUNDLED_BELL,
    )
    for candidate in candidates:
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
    def _assemble_wav(
        cls,
        output: Path,
        speech_path: Path,
        bell_path: Path | None,
        *,
        bell_offset_seconds: float,
        bell_volume: float,
        max_seconds: float | None,
    ) -> bool:
        """Transcode/mix speech (+bell) into ``output``; return True on success."""
        args = ["ffmpeg", "-y", "-i", str(speech_path)]
        if bell_path is not None:
            args.extend(["-i", str(bell_path)])
            delay_ms = int(round(bell_offset_seconds * 1000))
            limit = max_seconds or 6.0
            filter_complex = (
                f"[1:a]adelay={delay_ms}|{delay_ms},volume={bell_volume:.2f}[bell];"
                f"[0:a][bell]amix=inputs=2:duration=longest:dropout_transition=2,"
                f"apad=pad_dur={limit:.3f},atrim=duration={limit:.3f},"
                f"loudnorm=I=-14:TP=-1.5:LRA=11[a_out]"
            )
            args.extend(["-filter_complex", filter_complex, "-map", "[a_out]"])
        elif max_seconds:
            args.extend(["-t", f"{max_seconds:.3f}"])
        args.extend(["-ar", "48000", "-ac", "2", str(output)])
        try:
            subprocess.run(
                args,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return False
        return output.exists() and output.stat().st_size > 0

    @classmethod
    def generate_cta_audio(
        cls,
        speech_text: str,
        voice: str = DEFAULT_VOICE,
        include_bell: bool = True,
        bell_offset_seconds: float = 1.5,
        bell_volume: float = 0.7,
        max_seconds: float | None = None,
    ) -> Path | None:
        """Return a ready-to-mux WAV combining speech and the bell chime.

        ``max_seconds`` caps the mix to the window the video gives the CTA
        (overlay duration or outro card length). Returns ``None`` when synthesis
        is unavailable; callers should then skip CTA audio rather than fail the
        render.
        """
        speech_text = (speech_text or "").strip() or DEFAULT_SPEECH_TEXT
        limit = float(max_seconds) if max_seconds and max_seconds > 0 else None
        cache_dir = _cache_dir()
        key_input = f"{speech_text}|bell={include_bell}|{bell_offset_seconds}"
        if limit is not None:
            key_input += f"|max={limit:.3f}"
        key = _md5_key(key_input, voice)
        cached = cache_dir / f"{key}_cta.wav"
        # Silent placeholders never live at a cache path, so an offline render
        # cannot make every later render permanently silent.
        fallback = cache_dir / f"{key}_cta.fallback.wav"
        working = cache_dir / f"{key}_cta.partial.wav"
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
            return cls._silent_wav(min(estimated, limit) if limit else estimated, fallback)

        assembled = cls._assemble_wav(
            working,
            speech_path,
            bell_path if include_bell else None,
            bell_offset_seconds=bell_offset_seconds,
            bell_volume=bell_volume,
            max_seconds=limit,
        )
        if not assembled and bell_path is not None and include_bell:
            logger.warning("CTA audio mix failed; falling back to speech only")
            assembled = cls._assemble_wav(
                working,
                speech_path,
                None,
                bell_offset_seconds=bell_offset_seconds,
                bell_volume=bell_volume,
                max_seconds=limit,
            )
        if not assembled:
            working.unlink(missing_ok=True)
            return cls._silent_wav(min(3.0, limit) if limit else 3.0, fallback)

        working.replace(cached)
        logger.info("Assembled CTA audio -> %s", cached)
        cls._warn_if_window_filled(cached, limit)
        return cached

    @staticmethod
    def _warn_if_window_filled(path: Path, limit: float | None) -> None:
        """Flag a CTA whose speech runs into the configured window cap."""
        if not limit:
            return
        try:
            import wave

            with wave.open(str(path), "rb") as wav:
                duration = wav.getnframes() / wav.getframerate()
        except Exception:  # pragma: no cover - defensive
            return
        if duration >= limit - 0.05:
            logger.warning(
                "CTA voiceover fills its %.1fs window; lengthen the CTA/outro "
                "duration or shorten the speech script.",
                limit,
            )
