"""Presentation presets and defaults (Milestone 1).

Defines deterministic presets for vertical gameplay highlights:
- viral_kill (default): Gameplay begins immediately, subtle watermark, optional in-video subscribe overlay.
- cinematic_kill: Minimal text/branding, game audio focus, cinematic framing.
- multi_kill_montage: Event-aware pacing, kill notifications/counter, subtle subscribe overlay.

Settings explicitly configured in the channel profile override preset defaults.
No LLM is used to choose presets or generate presentation copy.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

PresentationPresetName = Literal["viral_kill", "cinematic_kill", "multi_kill_montage"]
DEFAULT_PRESENTATION_PRESET: PresentationPresetName = "viral_kill"


class PresentationPresetDefinition(BaseModel):
    """Specification of a deterministic presentation preset."""

    name: PresentationPresetName
    label: str
    description: str

    # Presentation & Cards
    branding_enabled: bool = False
    branding_intro: bool = False
    branding_outro: bool = False

    # Watermark
    watermark_enabled: bool = True
    watermark_position: str = "top_left"
    watermark_opacity: float = 0.70
    watermark_scale: float = 0.08
    watermark_margin: float = 0.03

    # CTA
    cta_enabled: bool = True
    cta_style: str = "overlay"  # "overlay" | "outro_card"
    cta_seconds: float = 3.0
    cta_speech_text: str | None = None  # None = no spoken audio by default (opt-in)

    # Framing & Quality
    default_framing_preset: str = "third_person"
    default_quality_preset: str = "high"

    # Hook Overlay
    hook_enabled: bool = False
    hook_position: str = "upper_third"
    hook_duration_seconds: float = 1.5

    # Kill Effects
    kill_effects_enabled: bool = False

    # Dynamic Reframing (Milestone 4)
    tracking_enabled: bool = False

    # Audio & Loop
    bg_music_volume: float = 0.30
    loop_optimization: bool = False

    def describe(self) -> dict[str, Any]:
        return self.model_dump()


PRESENTATION_PRESETS: dict[PresentationPresetName, PresentationPresetDefinition] = {
    "viral_kill": PresentationPresetDefinition(
        name="viral_kill",
        label="Viral Kill (Gameplay-First)",
        description=(
            "Gameplay begins immediately from the first frame. No full-screen intro or outro. "
            "Subtle watermark and an optional in-video subscribe overlay near the end."
        ),
        branding_enabled=False,
        branding_intro=False,
        branding_outro=False,
        watermark_enabled=True,
        watermark_position="top_left",
        watermark_opacity=0.70,
        watermark_scale=0.08,
        watermark_margin=0.03,
        cta_enabled=True,
        cta_style="overlay",
        cta_seconds=3.0,
        cta_speech_text=None,
        default_framing_preset="third_person",
        default_quality_preset="high",
        hook_enabled=False,
        hook_position="upper_third",
        hook_duration_seconds=1.5,
        kill_effects_enabled=False,
        tracking_enabled=False,
        bg_music_volume=0.30,
        loop_optimization=False,
    ),
    "cinematic_kill": PresentationPresetDefinition(
        name="cinematic_kill",
        label="Cinematic Kill",
        description=(
            "Gameplay begins immediately with minimal text and branding. Game audio is the focus, "
            "paired with cinematic balanced framing."
        ),
        branding_enabled=False,
        branding_intro=False,
        branding_outro=False,
        watermark_enabled=True,
        watermark_position="top_left",
        watermark_opacity=0.50,
        watermark_scale=0.06,
        watermark_margin=0.03,
        cta_enabled=False,
        cta_style="overlay",
        cta_seconds=2.5,
        cta_speech_text=None,
        default_framing_preset="cinematic",
        default_quality_preset="high",
        hook_enabled=False,
        hook_position="upper_third",
        hook_duration_seconds=1.5,
        kill_effects_enabled=False,
        tracking_enabled=True,
        bg_music_volume=0.20,
        loop_optimization=False,
    ),
    "multi_kill_montage": PresentationPresetDefinition(
        name="multi_kill_montage",
        label="Multi-Kill Montage",
        description=(
            "Fast-paced gameplay highlight driven by detected kill events. Optional restrained "
            "combo notifications and a subtle in-video subscribe overlay."
        ),
        branding_enabled=False,
        branding_intro=False,
        branding_outro=False,
        watermark_enabled=True,
        watermark_position="top_left",
        watermark_opacity=0.70,
        watermark_scale=0.08,
        watermark_margin=0.03,
        cta_enabled=True,
        cta_style="overlay",
        cta_seconds=3.0,
        cta_speech_text=None,
        default_framing_preset="third_person",
        default_quality_preset="high",
        hook_enabled=False,
        hook_position="upper_third",
        hook_duration_seconds=1.5,
        kill_effects_enabled=True,
        tracking_enabled=False,
        bg_music_volume=0.30,
        loop_optimization=False,
    ),
}


def get_presentation_preset(
    name: str | None,
) -> PresentationPresetDefinition:
    """Retrieve the presentation preset definition by name, falling back to viral_kill."""
    if not name:
        return PRESENTATION_PRESETS[DEFAULT_PRESENTATION_PRESET]
    token = str(name).strip().lower()
    return PRESENTATION_PRESETS.get(
        token, PRESENTATION_PRESETS[DEFAULT_PRESENTATION_PRESET]
    )
