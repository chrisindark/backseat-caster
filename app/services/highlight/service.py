"""Highlight service containing database, Celery dispatch, and end-to-end highlight pipeline."""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_task_db_session
from app.models.highlight_candidate import HighlightCandidate
from app.models.highlight_run import HighlightRun
from app.models.video import Video
from app.schemas.highlight import (
    DeleteHighlightsResponse,
    DetectHighlightsRequest,
    DetectHighlightsResponse,
    HighlightCandidateListResponse,
    HighlightCandidateResponse,
    HighlightDetailsSchema,
    HighlightRunListResponse,
    HighlightRunResponse,
    HighlightStatusResponse,
    TriggerEventSchema,
)
from app.services.auto_stage import AutoStageService
from app.services.highlight.audio_scanner import scan_audio_energy
from app.services.highlight.cluster_engine import ClusterConfig, ClusterEngine
from app.services.highlight.detectors import DetectionMetrics, get_detector
from app.services.highlight.roi_extractor import extract_candidate_windows_rois
from app.services.highlight.visual_matcher import evaluate_batch_visuals
from app.services.renders import RenderService
from app.worker.celery_app import celery_app
from app.worker.helpers import is_celery_broker_online

logger = logging.getLogger(__name__)

__all__ = [
    "ClusterConfig",
    "ClusterEngine",
    "HighlightService",
    "detect_highlights_celery_task",
    "evaluate_batch_visuals",
    "execute_highlight_detection_job",
    "extract_candidate_windows_rois",
    "scan_audio_energy",
]


class HighlightService:
    """Service handling highlight detection triggers, status polling, and database persistence."""

    @staticmethod
    def sync_celery_task_state(db: Session, video: Video) -> None:
        """Sync live Celery execution status back to Video model if task is in flight."""
        if video.highlight_task_id and video.highlight_status in (
            "pending",
            "scanning",
        ):
            try:
                res = celery_app.AsyncResult(video.highlight_task_id)
                if res.state == "SUCCESS" and video.highlight_status != "completed":
                    video.highlight_status = "completed"
                    video.highlight_progress = 100.0
                    video.highlight_stage = "Highlight scan completed"
                    db.commit()
                elif res.state == "FAILURE" and video.highlight_status != "failed":
                    video.highlight_status = "failed"
                    video.highlight_error = str(res.result)
                    db.commit()
                elif res.state == "PROGRESS" and isinstance(res.info, dict):
                    video.highlight_progress = res.info.get(
                        "progress", video.highlight_progress
                    )
                    video.highlight_stage = res.info.get("stage", video.highlight_stage)
                    db.commit()
            except Exception:
                pass

    @staticmethod
    def detect_highlights(
        db: Session,
        video_id: str,
        request: DetectHighlightsRequest | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> DetectHighlightsResponse:
        """
        Trigger asynchronous or synchronous highlight detection for a video.
        Dispatches to Celery worker when online, or runs via FastAPI BackgroundTasks fallback.
        """
        req = request or DetectHighlightsRequest()
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found")

        source_file = RenderService.resolve_source_video_file(db=db, video_id=video_id)
        if not source_file or not source_file.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Local video file not found for ID: {video_id}. Download or upload the VOD first.",
            )

        # Check if already scanning
        if not req.force_rescan and video.highlight_status == "scanning":
            return DetectHighlightsResponse(
                video_id=video.id,
                status=video.highlight_status,
                message="Highlight scan is already in progress.",
                task_id=video.highlight_task_id,
            )

        # Create tracking run record
        run_id = f"hrun_{uuid.uuid4().hex[:8]}"
        run = HighlightRun(
            id=run_id,
            video_id=video_id,
            status="pending",
            game=req.game or "generic",
            parameters_json=json.dumps(req.model_dump()),
            created_at=datetime.now(UTC),
        )
        db.add(run)

        # Update initial state
        video.highlight_status = "pending"
        video.highlight_progress = 0.0
        video.highlight_stage = "Queued for highlight analysis"
        video.highlight_error = None
        video.highlight_task_id = None
        db.commit()

        if req.sync:
            # Synchronous execution
            result = execute_highlight_detection_job(
                video_id=video_id,
                min_score=req.min_score,
                game=req.game,
                run_id=run_id,
                auto_render_top_n=req.auto_render_top_n,
                clipping_mode=req.clipping_mode,
                db_session=db,
            )
            db.refresh(video)
            status_val = (
                result.get("status")
                if result.get("status") in ("completed", "failed")
                else (video.highlight_status or "completed")
            )
            msg = (
                f"Highlight scan completed synchronously: {result.get('count', 0)} candidates found"
                if status_val == "completed"
                else f"Highlight scan failed: {result.get('error', 'Unknown error')}"
            )
            return DetectHighlightsResponse(
                video_id=video.id,
                status=status_val,
                message=msg,
                task_id=None,
                run_id=run_id,
                auto_staged_count=int(result.get("auto_staged_count", 0) or 0),
            )

        # Asynchronous dispatch
        dispatched_to_celery = False
        if is_celery_broker_online():
            try:
                task = detect_highlights_celery_task.delay(
                    video_id,
                    req.min_score,
                    req.game,
                    run_id,
                    req.auto_render_top_n,
                    req.clipping_mode,
                )
                video.highlight_task_id = task.id
                video.highlight_status = "scanning"
                run.celery_task_id = task.id
                run.status = "scanning"
                db.commit()
                dispatched_to_celery = True
                logger.info(
                    "Dispatched highlight scan for video %s (task: %s, run: %s) to Celery worker",
                    video_id,
                    task.id,
                    run_id,
                )
            except Exception as celery_err:
                logger.warning(
                    "Celery dispatch failed for highlight scan %s: %s, falling back to BackgroundTasks",
                    video_id,
                    celery_err,
                )

        if not dispatched_to_celery:
            logger.info(
                "Celery broker offline or dispatch skipped, dispatching highlight scan for %s to BackgroundTasks",
                video_id,
            )
            if background_tasks:
                background_tasks.add_task(
                    execute_highlight_detection_job,
                    video_id=video_id,
                    min_score=req.min_score,
                    game=req.game,
                    run_id=run_id,
                    auto_render_top_n=req.auto_render_top_n,
                    clipping_mode=req.clipping_mode,
                )
            else:
                execute_highlight_detection_job(
                    video_id=video_id,
                    min_score=req.min_score,
                    game=req.game,
                    run_id=run_id,
                    auto_render_top_n=req.auto_render_top_n,
                    clipping_mode=req.clipping_mode,
                )

        return DetectHighlightsResponse(
            video_id=video.id,
            status="pending" if not dispatched_to_celery else "scanning",
            message="Highlight detection queued successfully"
            + (" via Celery" if dispatched_to_celery else " in background worker"),
            task_id=video.highlight_task_id,
            run_id=run_id,
        )

    @staticmethod
    def get_status(db: Session, video_id: str) -> HighlightStatusResponse:
        """Get the current highlight scanning status, candidate count, and latest run metrics."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found")

        HighlightService.sync_celery_task_state(db=db, video=video)
        candidate_count = (
            db.query(HighlightCandidate)
            .filter(HighlightCandidate.video_id == video_id)
            .count()
        )

        latest_run_obj = (
            db.query(HighlightRun)
            .filter(HighlightRun.video_id == video_id)
            .order_by(HighlightRun.created_at.desc())
            .first()
        )
        latest_run = (
            HighlightRunResponse(**latest_run_obj.to_dict()) if latest_run_obj else None
        )

        return HighlightStatusResponse(
            video_id=video.id,
            status=video.highlight_status or "idle",
            progress=video.highlight_progress or 0.0,
            stage=video.highlight_stage or "",
            error=video.highlight_error,
            candidate_count=candidate_count,
            task_id=video.highlight_task_id,
            latest_run=latest_run,
        )

    @staticmethod
    def list_runs(db: Session, video_id: str) -> HighlightRunListResponse:
        """List all historical highlight detection runs with latencies and metrics for a video."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found")

        runs = (
            db.query(HighlightRun)
            .filter(HighlightRun.video_id == video_id)
            .order_by(HighlightRun.created_at.desc())
            .all()
        )
        run_responses = [HighlightRunResponse(**r.to_dict()) for r in runs]
        return HighlightRunListResponse(
            video_id=video_id,
            count=len(run_responses),
            runs=run_responses,
        )

    @staticmethod
    def list_candidates(db: Session, video_id: str) -> HighlightCandidateListResponse:
        """List all ranked highlight candidates mined for a video."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found")

        HighlightService.sync_celery_task_state(db=db, video=video)

        candidates = (
            db.query(HighlightCandidate)
            .filter(HighlightCandidate.video_id == video_id)
            .order_by(HighlightCandidate.score.desc())
            .all()
        )

        candidate_responses: list[HighlightCandidateResponse] = []
        for c in candidates:
            c_dict = c.to_dict()
            details_dict = c_dict.get("details", {})
            triggers = [
                TriggerEventSchema(**t) for t in details_dict.get("trigger_events", [])
            ]
            details_kwargs = {
                k: v for k, v in details_dict.items() if k != "trigger_events"
            }
            details = HighlightDetailsSchema(
                trigger_events=triggers,
                **details_kwargs,
            )
            candidate_responses.append(
                HighlightCandidateResponse(
                    candidate_id=c.id,
                    video_id=c.video_id,
                    start_seconds=c.start_seconds,
                    end_seconds=c.end_seconds,
                    duration_seconds=c.duration_seconds,
                    score=c.score,
                    event_type=c.event_type,
                    game=c.game or "generic",
                    details=details,
                    thumbnail_url=c.thumbnail_url,
                    thumbnail_path=c.thumbnail_path,
                    peak_timestamp=c.peak_timestamp,
                    suggested_title=c.suggested_title or "",
                    suggested_tags=c_dict.get("suggested_tags", []),
                    created_at=c_dict.get("created_at"),
                    updated_at=c_dict.get("updated_at"),
                )
            )

        return HighlightCandidateListResponse(
            video_id=video.id,
            status=video.highlight_status or "idle",
            count=len(candidate_responses),
            candidates=candidate_responses,
        )

    @staticmethod
    def delete_candidates(db: Session, video_id: str) -> DeleteHighlightsResponse:
        """Delete all highlight candidates and preview thumbnails for a video."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found")

        candidates = (
            db.query(HighlightCandidate)
            .filter(HighlightCandidate.video_id == video_id)
            .all()
        )
        count = len(candidates)

        # Delete thumbnail files
        for c in candidates:
            if c.thumbnail_path:
                try:
                    p = Path(c.thumbnail_path)
                    if p.exists():
                        p.unlink()
                    if p.parent.exists() and not any(p.parent.iterdir()):
                        shutil.rmtree(p.parent, ignore_errors=True)
                except Exception as e:
                    logger.warning(
                        "Could not delete thumbnail file for %s: %s", c.id, e
                    )
            else:
                cand_dir = settings.highlights_path / c.id
                if cand_dir.exists():
                    shutil.rmtree(cand_dir, ignore_errors=True)
            db.delete(c)

        # Reset video highlight state
        video.highlight_status = "idle"
        video.highlight_progress = 0.0
        video.highlight_stage = ""
        video.highlight_error = None
        video.highlight_task_id = None
        db.commit()

        return DeleteHighlightsResponse(
            video_id=video.id,
            deleted_count=count,
            message=f"Successfully deleted {count} highlight candidate(s).",
        )

    @staticmethod
    def get_thumbnail_path(db: Session, video_id: str, candidate_id: str) -> Path:
        """Retrieve path to thumbnail image file for a highlight candidate."""
        candidate = (
            db.query(HighlightCandidate)
            .filter(
                HighlightCandidate.id == candidate_id,
                HighlightCandidate.video_id == video_id,
            )
            .first()
        )
        if not candidate:
            raise HTTPException(
                status_code=404,
                detail=f"Candidate '{candidate_id}' not found for video '{video_id}'",
            )

        if candidate.thumbnail_path and Path(candidate.thumbnail_path).exists():
            return Path(candidate.thumbnail_path)

        fallback = settings.highlights_path / candidate_id / "thumb.jpg"
        if fallback.exists():
            return fallback

        raise HTTPException(
            status_code=404,
            detail=f"Thumbnail file not found for candidate '{candidate_id}'",
        )


def execute_highlight_detection_job(
    video_id: str,
    min_score: float = 0.5,
    game: str | None = None,
    run_id: str | None = None,
    auto_render_top_n: int | None = None,
    clipping_mode: str | None = None,
    celery_task_instance=None,
    db_session: Session | None = None,
) -> dict[str, Any]:
    """
    Core highlight mining execution logic shared by Celery and BackgroundTasks.
    Resolves detector strategy (Marvel Rivals vs Generic single player) and executes pipeline.
    Tracks execution latencies and stage metrics into HighlightRun.
    """
    is_external_session = db_session is not None
    db = db_session if db_session is not None else get_task_db_session()
    video = None
    run = None
    job_start_time = time.perf_counter()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            logger.error("Video %s not found for highlight scanning", video_id)
            return {"status": "failed", "error": f"Video '{video_id}' not found"}

        if run_id:
            run = db.query(HighlightRun).filter(HighlightRun.id == run_id).first()
            if run:
                run.status = "scanning"
                run.started_at = datetime.now(UTC)
                if celery_task_instance and hasattr(celery_task_instance, "request"):
                    run.celery_task_id = celery_task_instance.request.id

        video.highlight_status = "scanning"
        video.highlight_progress = 5.0
        video.highlight_stage = "Probing video media file..."
        video.highlight_error = None
        db.commit()

        if celery_task_instance:
            celery_task_instance.update_state(
                state="PROGRESS",
                meta={"progress": 5.0, "stage": video.highlight_stage},
            )

        source_file = RenderService.resolve_source_video_file(db=db, video_id=video_id)
        if not source_file or not source_file.exists():
            raise FileNotFoundError(
                f"Local video file not found for ID: {video_id}. Download or upload the VOD first."
            )

        # Resolve appropriate detector (Marvel Rivals vs Generic single player)
        detector = get_detector(
            game=game,
            video_title=video.title or "",
            video_description=video.description or "",
        )
        logger.info(
            "Selected highlight detector '%s' for video %s (requested game: %s)",
            detector.game_display_name,
            video_id,
            game,
        )

        def update_progress(progress: float, stage: str):
            video.highlight_progress = progress
            video.highlight_stage = stage
            db.commit()
            if celery_task_instance:
                celery_task_instance.update_state(
                    state="PROGRESS",
                    meta={"progress": progress, "stage": stage},
                )

        metrics = DetectionMetrics()
        filtered = detector.detect(
            video_id=video_id,
            media_path=source_file,
            min_score=min_score,
            progress_callback=update_progress,
            metrics=metrics,
        )

        # Stage 5: Database Persistence
        video.highlight_progress = 95.0
        video.highlight_stage = "Persisting highlight candidates to database..."
        db.commit()

        # Clear existing candidates for this video
        db.query(HighlightCandidate).filter(
            HighlightCandidate.video_id == video_id
        ).delete()

        for c in filtered:
            hc = HighlightCandidate(
                id=c.candidate_id,
                video_id=c.video_id,
                start_seconds=c.start_seconds,
                end_seconds=c.end_seconds,
                duration_seconds=c.duration_seconds,
                score=c.score,
                event_type=c.event_type,
                game=c.game,
                details_json=json.dumps(c.details.model_dump()),
                thumbnail_url=c.thumbnail_url,
                thumbnail_path=c.thumbnail_path,
                peak_timestamp=c.peak_timestamp,
                suggested_title=c.suggested_title,
                suggested_tags_json=json.dumps(c.suggested_tags),
            )
            db.add(hc)

        # Flush candidates so the auto-stage query can see them.
        db.commit()

        # Phase 8: auto-render and stage the top candidates when requested.
        effective_top_n = (
            auto_render_top_n
            if auto_render_top_n is not None
            else (settings.AUTO_STAGE_TOP_N if settings.AUTO_STAGE_ENABLED else 0)
        )
        auto_staged_count = 0
        if effective_top_n and filtered:
            update_progress(97.0, "Auto-staging top highlight candidates...")
            try:
                stage_result = AutoStageService.stage_top_candidates(
                    db=db,
                    video_id=video_id,
                    top_n=effective_top_n,
                    min_score=(
                        min_score
                        if auto_render_top_n is not None
                        else settings.AUTO_STAGE_MIN_SCORE
                    ),
                    clipping_mode=clipping_mode or settings.AUTO_STAGE_CLIPPING_MODE,
                )
                auto_staged_count = int(stage_result.get("staged_count", 0))
            except Exception as stage_err:
                logger.warning(
                    "Auto-stage step failed for video %s: %s", video_id, stage_err
                )

        total_duration = time.perf_counter() - job_start_time

        if run:
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            run.detector_used = detector.game_id
            run.total_duration_seconds = round(total_duration, 3)
            run.video_duration_seconds = metrics.video_duration_seconds
            run.audio_scan_duration_seconds = metrics.audio_scan_duration_seconds
            run.roi_extract_duration_seconds = metrics.roi_extract_duration_seconds
            run.visual_match_duration_seconds = metrics.visual_match_duration_seconds
            run.cluster_duration_seconds = metrics.cluster_duration_seconds
            run.audio_windows_count = metrics.audio_windows_count
            run.frames_analyzed_count = metrics.frames_analyzed_count
            run.visual_events_count = metrics.visual_events_count
            run.candidates_produced_count = len(filtered)
            if metrics.video_duration_seconds and total_duration > 0:
                run.speedup_factor = round(
                    metrics.video_duration_seconds / total_duration, 1
                )

        video.highlight_status = "completed"
        video.highlight_progress = 100.0
        video.highlight_stage = (
            f"Highlight scan complete. Found {len(filtered)} candidate clip(s)."
            + (
                f" Auto-staged {auto_staged_count} for publishing."
                if auto_staged_count
                else ""
            )
        )
        video.highlight_error = None
        db.commit()

        logger.info(
            "Successfully mined %d highlight candidates for video %s using detector %s in %.2fs (speedup: %sx)",
            len(filtered),
            video_id,
            detector.game_display_name,
            total_duration,
            run.speedup_factor if run and run.speedup_factor else "N/A",
        )
        return {
            "status": "completed",
            "count": len(filtered),
            "auto_staged_count": auto_staged_count,
            "run_id": run_id,
            "total_duration_seconds": round(total_duration, 3),
        }

    except Exception as exc:
        logger.error(
            "Highlight detection failed for video %s: %s",
            video_id,
            exc,
            exc_info=True,
        )
        if run:
            try:
                run.status = "failed"
                run.completed_at = datetime.now(UTC)
                run.error_message = str(exc)
                run.total_duration_seconds = round(
                    time.perf_counter() - job_start_time, 3
                )
                db.commit()
            except Exception as run_err:
                logger.error("Failed updating highlight run error status: %s", run_err)
                db.rollback()

        if video:
            try:
                video.highlight_status = "failed"
                video.highlight_progress = 0.0
                video.highlight_stage = "Highlight scanning failed"
                video.highlight_error = str(exc)
                db.commit()
            except Exception as commit_err:
                logger.error("Failed updating video error status: %s", commit_err)
                db.rollback()
        return {"status": "failed", "error": str(exc), "run_id": run_id}

    finally:
        import sys

        main_mod = sys.modules.get("app.main")
        fastapi_app = getattr(main_mod, "app", None) if main_mod else None
        from app.database import get_db

        is_overridden = bool(
            fastapi_app
            and hasattr(fastapi_app, "dependency_overrides")
            and get_db in fastapi_app.dependency_overrides
        )
        if not is_external_session and not is_overridden:
            db.close()


@celery_app.task(bind=True, name="detect_highlights_task")
def detect_highlights_celery_task(
    self,
    video_id: str,
    min_score: float = 0.5,
    game: str | None = None,
    run_id: str | None = None,
    auto_render_top_n: int | None = None,
    clipping_mode: str | None = None,
) -> dict[str, Any]:
    """Celery task for executing highlight candidate detection in the background."""
    logger.info(
        "Celery task started: detect_highlights for video %s (task_id: %s, game: %s, run_id: %s)",
        video_id,
        self.request.id,
        game,
        run_id,
    )
    return execute_highlight_detection_job(
        video_id=video_id,
        min_score=min_score,
        game=game,
        run_id=run_id,
        auto_render_top_n=auto_render_top_n,
        clipping_mode=clipping_mode,
        celery_task_instance=self,
    )
