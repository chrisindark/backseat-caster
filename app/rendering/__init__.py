"""BackseatCaster Rendering Engine package."""

from app.rendering.config import RenderConfig, default_render_config
from app.rendering.engine import RenderEngine, RenderResult, detect_available_encoders
from app.rendering.manifest import write_manifest
from app.rendering.probe import MediaProbeResult, probe_media
from app.rendering.validator import ValidationError, validate_render_parameters

__all__ = [
    "MediaProbeResult",
    "RenderConfig",
    "RenderEngine",
    "RenderResult",
    "ValidationError",
    "default_render_config",
    "detect_available_encoders",
    "probe_media",
    "validate_render_parameters",
    "write_manifest",
]
