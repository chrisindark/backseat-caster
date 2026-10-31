"""Tests for the composed clip-length ceiling on the channel profile."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.video import Video
from app.schemas.channel import ChannelProfileUpdate
from app.schemas.render import RenderClipRequest
from app.services.channel_profile import ChannelProfileService
from app.services.renders import RenderService


def test_create_render_rejects_clips_over_the_ceiling(monkeypatch, tmp_path):
    """A clip that cannot fit under the ceiling is rejected, not silently trimmed."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        source = tmp_path / "source.mp4"
        source.write_bytes(b"dummy")
        monkeypatch.setattr(settings, "RENDERS_DIR", str(tmp_path / "renders"))
        monkeypatch.setattr(
            RenderService, "resolve_source_video_file", lambda db, video_id: source
        )

        video = Video(
            id="vid_ceiling",
            title="Demo",
            webpage_url="https://example.com",
            local_file_path=str(source),
        )
        session.add(video)
        session.commit()

        request = RenderClipRequest(
            video_id=video.id, start_seconds=0.0, duration_seconds=100.0
        )
        # Branding on -> bookends eat into the budget, so 100s is over.
        ChannelProfileService.update(
            session,
            ChannelProfileUpdate(
                branding_enabled=True,
                branding_intro_seconds=1.2,
                branding_outro_seconds=2.0,
            ),
        )

        import pytest

        with pytest.raises(RuntimeError) as exc:
            RenderService.create_render(db=session, request=request)
        assert "ceiling" in str(exc.value)
        assert "86.8s or less" in str(exc.value)
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
