"""First-run setup wizard service: diagnostics, in-app settings, and instant demo project."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.highlight_candidate import HighlightCandidate
from app.models.render_job import RenderJob
from app.models.video import Video
from app.schemas.setup import (
    DemoProjectResponse,
    SetupCheckItem,
    SetupSettingsResponse,
    SetupStatusResponse,
    UpdateSetupSettingsRequest,
)
from app.services.auto_stage import AutoStageService
from app.services.llm_metadata import LLMMetadataService
from app.services.preflight import check_disk_space, check_ffmpeg, check_ffprobe
from app.services.renders import RenderService
from app.services.settings_manager import SettingsManager
from app.services.youtube_uploader import YouTubeUploaderService

logger = logging.getLogger(__name__)

DEMO_VIDEO_ID = "demo_marvel_rivals_60s"
DEMO_FILENAME = "demo_marvel_rivals_60s.mp4"


class SetupService:
    """Orchestrates first-run readiness checks, runtime settings, and demo seeding."""

    @classmethod
    def get_status(cls, db: Session) -> SetupStatusResponse:
        """Evaluate the 4 first-run health checks and return overall readiness."""
        ffmpeg_res = check_ffmpeg()
        ffprobe_res = check_ffprobe()
        disk_res = check_disk_space()
        yt_auth = YouTubeUploaderService.get_auth_status()
        llm_avail = LLMMetadataService.is_available()
        llm_cfg = LLMMetadataService.is_configured()

        checks: list[SetupCheckItem] = []

        # 1. FFmpeg & Media Engine Check (Required)
        ffmpeg_ok = ffmpeg_res.installed and ffprobe_res.installed
        checks.append(
            SetupCheckItem(
                name="ffmpeg",
                title="FFmpeg & Media Engine",
                status="ok" if ffmpeg_ok else "error",
                required=True,
                message=(
                    f"FFmpeg {ffmpeg_res.version or ''} & FFprobe detected"
                    if ffmpeg_ok
                    else (ffmpeg_res.error or ffprobe_res.error or "FFmpeg missing")
                ),
                remedy=ffmpeg_res.remedy or ffprobe_res.remedy,
                details={
                    "ffmpeg_version": ffmpeg_res.version,
                    "ffmpeg_path": ffmpeg_res.path,
                    "ffprobe_version": ffprobe_res.version,
                    "ffprobe_path": ffprobe_res.path,
                },
            )
        )

        # 2. Local Storage & Disk Check (Required)
        disk_status = disk_res.status  # ok, warning, error
        checks.append(
            SetupCheckItem(
                name="disk_space",
                title="Local Storage & Disk Space",
                status=disk_status,
                required=True,
                message=(
                    f"{disk_res.free_gb:.1f} GB free of {disk_res.total_gb:.1f} GB "
                    f"({disk_res.percent_used:.0f}% used)"
                ),
                remedy=disk_res.remedy,
                details={
                    "path": disk_res.path,
                    "free_gb": disk_res.free_gb,
                    "total_gb": disk_res.total_gb,
                    "min_required_gb": disk_res.min_required_gb,
                },
            )
        )

        # 3. AI Copy Engine Check (Optional)
        ai_enabled = bool(settings.LLM_METADATA_ENABLED)
        if ai_enabled and llm_cfg:
            ai_status_str = "ok"
            ai_msg = (
                f"Active using {settings.resolved_llm_model} "
                f"({settings.resolved_llm_base_url})"
            )
        elif ai_enabled and not llm_cfg:
            ai_status_str = "warning"
            ai_msg = "Enabled, but no API key or local base URL configured (will fall back to deterministic copy)"
        else:
            ai_status_str = "ok"
            ai_msg = "Deterministic Copy active (Offline & free; no API keys required)"

        checks.append(
            SetupCheckItem(
                name="ai_key",
                title="AI Copy Engine (Optional)",
                status=ai_status_str,
                required=False,
                message=ai_msg,
                remedy=(
                    "Configure LLM_BASE_URL (for Ollama/LM Studio) or LLM_API_KEY in "
                    "Settings below if you wish to use AI copy generation."
                ),
                details={
                    "enabled": ai_enabled,
                    "configured": llm_cfg,
                    "available": llm_avail,
                    "model": settings.resolved_llm_model,
                    "base_url": settings.resolved_llm_base_url,
                    "has_key": bool(settings.llm_api_key),
                },
            )
        )

        # 4. YouTube Publishing Connection (Optional)
        if yt_auth.is_authenticated:
            yt_status_str = "ok"
            channel_label = (
                f"@{yt_auth.channel_handle}"
                if yt_auth.channel_handle
                else yt_auth.channel_title or "Connected Channel"
            )
            yt_msg = f"Connected as {channel_label}"
        elif yt_auth.client_configured:
            yt_status_str = "warning"
            yt_msg = "Client credentials loaded; click Connect to authorize YouTube"
        else:
            yt_status_str = "warning"
            yt_msg = "Not connected — export clips locally or connect YouTube via OAuth below"

        checks.append(
            SetupCheckItem(
                name="youtube",
                title="YouTube Publishing (Optional)",
                status=yt_status_str,
                required=False,
                message=yt_msg,
                remedy="Paste your Google OAuth client_secrets.json below to enable 1-click publishing.",
                details=yt_auth.model_dump(),
            )
        )

        # 5. Zero-click ingest pipeline (Optional)
        watch_path = settings.watch_path
        if watch_path is None:
            watch_status_str = "ok"
            watch_msg = (
                "Watch folder off — ingest via drag-and-drop or YouTube download"
            )
        elif not watch_path.exists():
            watch_status_str = "warning"
            watch_msg = f"Watch folder configured but not found: {watch_path}"
        else:
            watch_status_str = "ok"
            watch_msg = f"Watching {watch_path}"
            if settings.AUTO_MINE_ON_INGEST:
                mine_n = settings.auto_mine_top_n
                watch_msg += (
                    f" · auto-mine on ingest ({mine_n} clip(s) auto-staged)"
                    if mine_n
                    else " · auto-mine on ingest (review before staging)"
                )

        checks.append(
            SetupCheckItem(
                name="watch_folder",
                title="Zero-Click Ingest (Optional)",
                status=watch_status_str,
                required=False,
                message=watch_msg,
                remedy=(
                    "Point the watch folder at your OBS recording directory to ingest "
                    "recordings automatically, then enable auto-mine to clip them without touching anything."
                ),
                details={
                    "watch_dir": str(watch_path) if watch_path else None,
                    "poll_interval_minutes": settings.WATCH_POLL_INTERVAL_MINUTES,
                    "auto_mine_on_ingest": bool(settings.AUTO_MINE_ON_INGEST),
                    "auto_stage_clips_per_ingest": settings.auto_mine_top_n,
                },
            )
        )

        # Sample project status
        demo_vid = db.query(Video).filter(Video.id == DEMO_VIDEO_ID).first()
        demo_renders = (
            db.query(RenderJob).filter(RenderJob.video_id == DEMO_VIDEO_ID).count()
            if demo_vid
            else 0
        )
        sample_info = {
            "is_loaded": demo_vid is not None,
            "video_id": DEMO_VIDEO_ID if demo_vid else None,
            "rendered_count": demo_renders,
        }

        ready = ffmpeg_ok and (disk_status != "error")

        return SetupStatusResponse(
            ready=ready,
            checks=checks,
            ai_status={
                "enabled": ai_enabled,
                "configured": llm_cfg,
                "available": llm_avail,
                "model": settings.resolved_llm_model,
                "base_url": settings.resolved_llm_base_url,
                "has_api_key": bool(settings.llm_api_key),
            },
            youtube_status=yt_auth.model_dump(),
            sample_project=sample_info,
        )

    @classmethod
    def get_settings(cls) -> SetupSettingsResponse:
        """Return current in-app settings."""
        return SetupSettingsResponse(
            llm_enabled=bool(settings.LLM_METADATA_ENABLED),
            llm_base_url=settings.LLM_BASE_URL,
            llm_model=settings.LLM_MODEL,
            llm_has_api_key=bool(settings.llm_api_key),
            default_clipping_mode=getattr(
                settings, "AUTO_STAGE_CLIPPING_MODE", "third_person"
            ),
            auto_stage_top_n=getattr(settings, "AUTO_STAGE_TOP_N", 3),
            auto_stage_min_score=getattr(settings, "AUTO_STAGE_MIN_SCORE", 0.6),
            auto_cleanup_uploaded_renders=getattr(
                settings, "AUTO_CLEANUP_UPLOADED_RENDERS", True
            ),
            auto_cleanup_vod=getattr(settings, "AUTO_CLEANUP_VOD", False),
            youtube_redirect_uri=settings.YOUTUBE_REDIRECT_URI,
            auto_mine_on_ingest=bool(settings.AUTO_MINE_ON_INGEST),
            watch_dir=settings.WATCH_DIR,
            watch_poll_interval_minutes=int(settings.WATCH_POLL_INTERVAL_MINUTES),
            watch_delete_after_ingest=bool(settings.WATCH_DELETE_AFTER_INGEST),
        )

    @classmethod
    def update_settings(
        cls, request: UpdateSetupSettingsRequest
    ) -> SetupSettingsResponse:
        """Update runtime settings and persist them to data/settings.json."""
        payload = request.model_dump(exclude_unset=True)
        SettingsManager.save_persisted_settings(payload)
        return cls.get_settings()

    @classmethod
    def generate_demo_video_file(cls) -> Path:
        """Generate a 60-second synthetic gameplay highlight clip via FFmpeg."""
        settings.ensure_directories()
        demo_path = Path(settings.DOWNLOADS_DIR) / DEMO_FILENAME

        if demo_path.exists() and demo_path.stat().st_size > 500_000:
            return demo_path

        logger.info("Generating synthetic 60s demo gameplay clip at %s...", demo_path)
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=duration=60:size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=60",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-b:v",
            "900k",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(demo_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg demo generation failed: {proc.stderr}")

        return demo_path

    @classmethod
    def load_demo_project(
        cls,
        db: Session,
        *,
        auto_render: bool = True,
        sync: bool = True,
        background_tasks: Any = None,
    ) -> DemoProjectResponse:
        """Seed the 60-second Marvel Rivals highlight demo and render 3 Shorts."""
        demo_file = cls.generate_demo_video_file()
        file_size = demo_file.stat().st_size

        # 1. Seed or get Demo Video
        video = db.query(Video).filter(Video.id == DEMO_VIDEO_ID).first()
        if not video:
            video = Video(
                id=DEMO_VIDEO_ID,
                title="Marvel Rivals: 5K Clutch Overtime Point Hold (Demo)",
                description=(
                    "Instant 60-second sample VOD with 3 high-intensity highlight candidates. "
                    "Demonstrates auto-highlight mining, vertical cropping, and YouTube Shorts staging."
                ),
                duration=60,
                duration_formatted="1:00",
                channel_name="BackseatCaster Highlights",
                channel_id="UC_demo_backseatcaster",
                channel_url="https://youtube.com/@backseatcaster",
                webpage_url="https://local.backseatcaster/demo",
                is_downloaded=True,
                download_status="completed",
                local_file_path=str(demo_file),
                file_size_bytes=file_size,
                highlight_status="completed",
                highlight_progress=100.0,
            )
            db.add(video)
            db.commit()
            db.refresh(video)
        else:
            video.is_downloaded = True
            video.local_file_path = str(demo_file)
            video.download_status = "completed"
            video.highlight_status = "completed"
            db.commit()

        # 2. Seed 3 Known-Good Highlight Candidates
        demo_candidates_data = [
            {
                "id": f"{DEMO_VIDEO_ID}_cand_1",
                "start": 4.0,
                "end": 18.0,
                "score": 0.96,
                "event_type": "team_wipe",
                "game": "Marvel Rivals",
                "hero_name": "Magneto",
                "details": {
                    "hero_name": "Magneto",
                    "kill_count": 5,
                    "multi_kill_chain": "penta_kill",
                    "streak_count": 5,
                    "has_ultimate": True,
                    "is_team_wipe": True,
                    "game_phase": "overtime",
                    "abilities_used": ["Meteor M", "Iron Curtain"],
                    "clip_context": "Magneto 5K clutch team wipe holding point in overtime",
                },
            },
            {
                "id": f"{DEMO_VIDEO_ID}_cand_2",
                "start": 22.0,
                "end": 36.0,
                "score": 0.89,
                "event_type": "ultimate_shutdown",
                "game": "Marvel Rivals",
                "hero_name": "Luna Snow",
                "details": {
                    "hero_name": "Luna Snow",
                    "kill_count": 3,
                    "multi_kill_chain": "triple_kill",
                    "streak_count": 3,
                    "has_ultimate": True,
                    "is_team_wipe": False,
                    "game_phase": "midgame",
                    "abilities_used": ["Fate of Both Worlds", "Ice Arts"],
                    "clip_context": "Luna Snow idol dance counter-ult freezing the dive",
                },
            },
            {
                "id": f"{DEMO_VIDEO_ID}_cand_3",
                "start": 40.0,
                "end": 56.0,
                "score": 0.84,
                "event_type": "objective_steal",
                "game": "Marvel Rivals",
                "hero_name": "Spider-Man",
                "details": {
                    "hero_name": "Spider-Man",
                    "kill_count": 2,
                    "multi_kill_chain": "double_kill",
                    "streak_count": 4,
                    "has_ultimate": False,
                    "is_team_wipe": False,
                    "game_phase": "final_push",
                    "abilities_used": ["Web-Cluster", "Amazing Combo"],
                    "clip_context": "Spider-Man backcap overtime contest holding choke",
                },
            },
        ]

        cand_ids: list[str] = []
        for cd in demo_candidates_data:
            existing_c = (
                db.query(HighlightCandidate)
                .filter(HighlightCandidate.id == cd["id"])
                .first()
            )
            cand_ids.append(cd["id"])
            if not existing_c:
                cand = HighlightCandidate(
                    id=cd["id"],
                    video_id=DEMO_VIDEO_ID,
                    start_seconds=cd["start"],
                    end_seconds=cd["end"],
                    duration_seconds=cd["end"] - cd["start"],
                    score=cd["score"],
                    event_type=cd["event_type"],
                    game=cd["game"],
                    details_json=json.dumps(cd["details"]),
                    peak_timestamp=(cd["start"] + cd["end"]) / 2,
                    suggested_title=f"{cd['hero_name']} {cd['details']['multi_kill_chain'].replace('_', ' ').title()}",
                )
                db.add(cand)

        db.commit()

        # 3. Stage the Candidates as Vertical Shorts
        staged_result = AutoStageService.stage_selected_candidates(
            db=db,
            video_id=DEMO_VIDEO_ID,
            candidate_ids=cand_ids,
            clipping_mode="third_person",
            schedule=True,
            same_day_catchup=True,
        )

        staged_jobs = staged_result.get("staged_jobs") or []
        clip_ids = [j["clip_id"] for j in staged_jobs if "clip_id" in j]

        # 4. Render the 3 Shorts
        rendered_count = 0
        if auto_render and clip_ids:
            if sync:
                for j in staged_jobs:
                    job_id = j.get("job_id")
                    if job_id:
                        try:
                            RenderService.execute_render(job_id)
                            rendered_count += 1
                        except Exception as e:
                            logger.error("Failed rendering demo job %s: %s", job_id, e)
            elif background_tasks:
                for j in staged_jobs:
                    job_id = j.get("job_id")
                    if job_id:
                        background_tasks.add_task(RenderService.execute_render, job_id)
                        rendered_count += 1

        return DemoProjectResponse(
            success=True,
            message=(
                f"Demo project ready! 3 Shorts staged and rendered in {demo_file.name}. "
                "Explore the clips in Studio or review staged metadata in Staging."
            ),
            video_id=DEMO_VIDEO_ID,
            video_title=video.title,
            candidates_count=len(cand_ids),
            staged_jobs_count=len(staged_jobs),
            rendered_jobs_count=rendered_count,
            clip_ids=clip_ids,
        )
