"""Tests for the TTS service (cache + offline degradation)."""

import subprocess
import wave

import pytest

from app.services.tts import TTSService


def test_md5_key_is_deterministic():
    from app.services import tts

    assert tts._md5_key("hello", "voice") == tts._md5_key("hello", "voice")
    assert tts._md5_key("hello", "voice") != tts._md5_key("hello", "other")


def test_find_bell_locates_the_bundled_asset():
    from app.services import tts

    assert tts._find_bell() is not None
    assert tts._find_bell().exists()


def test_silent_wav_fallback_writes_a_valid_file(tmp_path):
    target = tmp_path / "silent.wav"
    result = TTSService._silent_wav(2.0, target)
    assert result == target
    assert target.exists() and target.stat().st_size > 0


def test_generate_cta_audio_returns_a_cached_path(monkeypatch, tmp_path):
    """Identical inputs reuse the cached file instead of synthesising again."""
    from app.services import tts

    monkeypatch.setattr(tts, "_cache_dir", lambda: tmp_path)
    speech = tmp_path / "speech.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(speech),
        ],
        capture_output=True,
        check=True,
    )
    calls = {"n": 0}

    def synthesize(*args, **kwargs):
        calls["n"] += 1
        return speech

    monkeypatch.setattr(TTSService, "synthesize_speech_sync", staticmethod(synthesize))

    first = TTSService.generate_cta_audio(
        "Subscribe and tap the bell.", include_bell=False
    )
    assert first is not None and first.exists()
    second = TTSService.generate_cta_audio(
        "Subscribe and tap the bell.", include_bell=False
    )
    assert second == first
    assert calls["n"] == 1


def test_offline_fallback_does_not_poison_the_cache(monkeypatch, tmp_path):
    """A silent placeholder must not become a permanent cache hit."""
    from app.services import tts

    monkeypatch.setattr(tts, "_cache_dir", lambda: tmp_path)
    calls = {"n": 0}

    def offline(*args, **kwargs):
        calls["n"] += 1
        return None

    monkeypatch.setattr(TTSService, "synthesize_speech_sync", staticmethod(offline))
    placeholder = TTSService.generate_cta_audio(
        "a fresh script", include_bell=False, max_seconds=3.0
    )
    assert placeholder is not None
    assert placeholder.name.endswith(".fallback.wav")
    assert not (tmp_path / placeholder.name.replace(".fallback.wav", ".wav")).exists()

    speech = tmp_path / "speech.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(speech),
        ],
        capture_output=True,
        check=True,
    )

    def online(*args, **kwargs):
        calls["n"] += 1
        return speech

    monkeypatch.setattr(TTSService, "synthesize_speech_sync", staticmethod(online))
    recovered = TTSService.generate_cta_audio(
        "a fresh script", include_bell=False, max_seconds=3.0
    )

    assert calls["n"] == 2, "synthesis was not retried after the offline render"
    assert recovered.name.endswith("_cta.wav")
    with wave.open(str(recovered)) as wav:
        duration = wav.getnframes() / wav.getframerate()
    assert duration == pytest.approx(3.0, abs=0.05)
