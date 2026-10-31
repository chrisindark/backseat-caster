"""Tests for the TTS service (cache + offline degradation)."""

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


def test_generate_cta_audio_returns_a_cached_path():
    # First call synthesises (or falls back) and caches.
    first = TTSService.generate_cta_audio(
        "Subscribe and tap the bell.", include_bell=True
    )
    assert first is not None and first.exists()
    # Second call with identical inputs must hit the cache (same path).
    second = TTSService.generate_cta_audio(
        "Subscribe and tap the bell.", include_bell=True
    )
    assert second == first
