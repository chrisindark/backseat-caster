"""Tests for White Fox hero addition, title/description adjective variety, and clip duration configuration."""

from app.config import settings
from app.services.highlight.cluster_engine import (
    ClusterEngine,
    generate_suggested_title,
)
from app.services.highlight.visual_matcher import VisualDetectionEvent
from app.services.llm_metadata import get_known_heroes, infer_hero_name
from app.services.settings_manager import SettingsManager
from app.services.upload_metadata import (
    TIER_HIGH_ADJECTIVES,
    TIER_PEAK_ADJECTIVES,
    TIER_PRECISION_ADJECTIVES,
    build_description,
    build_title,
    pick_adjective,
)


def test_white_fox_in_known_heroes():
    """Verify White Fox is recognized in Marvel Rivals hero roster and text inference."""
    heroes = get_known_heroes()
    assert "White Fox" in heroes

    # Text inference
    matched = infer_hero_name(
        "Crazy 5K clutch with White Fox holding point B in overtime"
    )
    assert matched == "White Fox"


def test_adjective_pools_have_variety():
    """Verify rich variety beyond just 'Insane', 'Unreal', 'Crazy'."""
    assert len(TIER_PEAK_ADJECTIVES) >= 8
    assert "Godlike" in TIER_PEAK_ADJECTIVES
    assert "Legendary" in TIER_PEAK_ADJECTIVES
    assert "Flawless" in TIER_PEAK_ADJECTIVES

    assert len(TIER_HIGH_ADJECTIVES) >= 8
    assert "Wild" in TIER_HIGH_ADJECTIVES
    assert "Savage" in TIER_HIGH_ADJECTIVES
    assert "Masterclass" in TIER_HIGH_ADJECTIVES

    assert len(TIER_PRECISION_ADJECTIVES) >= 8
    assert "Clean" in TIER_PRECISION_ADJECTIVES
    assert "Crisp" in TIER_PRECISION_ADJECTIVES
    assert "Clinical" in TIER_PRECISION_ADJECTIVES

    # Pick adjective is deterministic
    adj1 = pick_adjective(TIER_PEAK_ADJECTIVES, "cand_test_123", "peak")
    adj2 = pick_adjective(TIER_PEAK_ADJECTIVES, "cand_test_123", "peak")
    assert adj1 == adj2


def test_suggested_title_uses_varied_adjectives():
    """Verify generated titles use varied adjectives depending on seed."""
    titles = set()
    for seed_id in [
        "cand_1",
        "cand_2",
        "cand_3",
        "cand_4",
        "cand_5",
        "cand_6",
        "cand_7",
        "cand_8",
    ]:
        t = generate_suggested_title(
            event_type="team_wipe",
            kill_count=6,
            character_name="White Fox",
            is_team_wipe=True,
            seed=seed_id,
        )
        assert "White Fox" in t
        assert "Team Wipe" in t
        first_word = t.split()[0]
        titles.add(first_word)

    # Should produce multiple distinct adjectives across different seeds
    assert len(titles) > 1


def test_hero_prefix_insertion_supports_extended_adjectives():
    """Verify hero prefix insertion works when suggested title starts with any new adjective."""
    for adj in ["Godlike", "Legendary", "Wild", "Savage", "Flawless", "Masterclass"]:
        raw_sugg = f"{adj} Team Wipe Ultimate! 💥 #MarvelRivals"
        cand = {"suggested_title": raw_sugg}
        title = build_title(candidate=cand, hero_name="White Fox")
        assert title.startswith(f"{adj} White Fox Team Wipe")
        assert "#MarvelRivals" in title


def test_build_description_uses_varied_adjectives():
    """Verify description hook lines use diverse exciting adjectives."""
    adjectives_seen = set()
    for i in range(10):
        cand = {"id": f"cand_desc_test_{i}", "event_type": "team_wipe"}
        desc = build_description(
            candidate=cand, hero_name="White Fox", game="Marvel Rivals"
        )
        first_line = desc.split("\n")[0]
        assert "White Fox" in first_line
        # Extract adjective from hook line: "🔥 {adj} White Fox Team Wipe..."
        words = first_line.replace("🔥 ", "").split()
        adjectives_seen.add(words[0])

    assert len(adjectives_seen) > 1


def test_build_title_upgrades_overused_adjectives():
    """Verify build_title upgrades repetitive adjectives ('Insane', 'Unreal', 'Crazy') to diverse ones."""
    titles = set()
    for i in range(10):
        cand = {
            "id": f"cand_wipe_{i}",
            "suggested_title": "Insane Team Wipe Ultimate! 💥 #MarvelRivals",
            "event_type": "team_wipe",
        }
        title = build_title(candidate=cand, hero_name="White Fox", game="Marvel Rivals")
        assert "White Fox" in title
        assert "Team Wipe" in title
        assert "#MarvelRivals" in title
        first_word = title.split()[0]
        titles.add(first_word)

    # Should have replaced "Insane" with multiple varied adjectives from TIER_PEAK_ADJECTIVES
    assert len(titles) > 1
    # Check that at least some titles used peak adjectives like Godlike, Legendary, etc.
    assert any(adj in titles for adj in TIER_PEAK_ADJECTIVES if adj != "Insane")


def test_build_title_adds_dynamic_adjective_to_unadorned_titles():
    """Verify build_title prepends a dynamic adjective to titles like 'Magneto Penta Kill'."""
    cand = {
        "id": "cand_mag_penta",
        "suggested_title": "Magneto Penta Kill",
        "event_type": "penta_ko",
    }
    title = build_title(candidate=cand, hero_name="Magneto", game="Marvel Rivals")
    words = title.split()
    # First word should be a dynamic adjective, followed by Magneto Penta Kill
    assert words[0] in TIER_PEAK_ADJECTIVES
    assert words[1] == "Magneto"
    assert "Penta Kill" in title
    assert "#MarvelRivals" in title


def test_build_title_upgrades_all_caps_adjective():
    """Verify uppercase adjectives like 'UNREAL' are replaced with uppercase dynamic adjectives."""
    cand = {
        "id": "cand_fg_crown_1",
        "suggested_title": "UNREAL FALL GUYS CROWN VICTORY! 👑 #FallGuys #Shorts",
        "event_type": "crown_victory",
    }
    title = build_title(candidate=cand, game="Fall Guys")
    first_word = title.split()[0]
    assert first_word.isupper()
    assert "FALL GUYS CROWN VICTORY" in title


def test_fall_guys_and_generic_detector_titles_have_variety():
    """Verify Fall Guys and Generic detectors produce varied adjectives across seeds."""
    from app.services.highlight.detectors.fall_guys import FallGuysDetector
    from app.services.highlight.detectors.generic import GenericHighlightDetector

    fg_detector = FallGuysDetector()
    fg_titles = set()
    for i in range(8):
        t, _ = fg_detector._generate_title_and_tags(
            "crown_victory", 1.0, seed=f"seed_fg_{i}"
        )
        fg_titles.add(t.split()[0])
    assert len(fg_titles) > 1

    gen_detector = GenericHighlightDetector(game_name="Cyberpunk 2077")
    gen_titles = set()
    for i in range(8):
        t, _ = gen_detector._generate_title_and_tags(
            "epic_climax", 0.9, seed=f"seed_gen_{i}"
        )
        gen_titles.add(t.split()[0])
    assert len(gen_titles) > 1


def test_cluster_duration_defaults_and_longer_clipping():
    """Verify ClusterConfig min duration defaults to 45s (making clips longer)."""
    engine = ClusterEngine()
    assert engine.config.min_clip_duration == 45.0
    assert engine.config.max_clip_duration == 60.0

    # Short 2-second action event at 30s
    events = [
        VisualDetectionEvent(
            timestamp=30.0,
            roi_name="center_ko",
            event_type="double_ko",
            label="DOUBLE KO",
            confidence=0.90,
            kill_count=2,
            score_weight=0.70,
        )
    ]
    cand = engine.cluster_events(events, total_duration=120.0, video_id="vod_long")[0]
    # Because min_clip_duration is 45.0, the candidate duration is clamped to 45.0s
    assert cand.duration_seconds == 45.0
    assert cand.start_seconds <= 30.0 <= cand.end_seconds


def test_settings_manager_persists_clip_duration(tmp_path, monkeypatch):
    """Verify highlight min and max clip duration can be customized at runtime."""
    test_file = tmp_path / "settings.json"
    monkeypatch.setattr(
        SettingsManager, "get_persisted_settings_path", lambda: test_file
    )

    old_min = settings.HIGHLIGHT_MIN_CLIP_DURATION
    old_max = settings.HIGHLIGHT_MAX_CLIP_DURATION
    try:
        SettingsManager.save_persisted_settings(
            {
                "highlight_min_clip_duration": 52.0,
                "highlight_max_clip_duration": 75.0,
            }
        )
        assert settings.HIGHLIGHT_MIN_CLIP_DURATION == 52.0
        assert settings.HIGHLIGHT_MAX_CLIP_DURATION == 75.0

        # ClusterEngine picks up the updated settings
        engine = ClusterEngine()
        assert engine.config.min_clip_duration == 52.0
        assert engine.config.max_clip_duration == 75.0
    finally:
        settings.HIGHLIGHT_MIN_CLIP_DURATION = old_min
        settings.HIGHLIGHT_MAX_CLIP_DURATION = old_max
