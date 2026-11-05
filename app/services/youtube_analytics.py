"""YouTube Short View Velocity Tracker and Optimal Slot Optimizer service."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_task_db_session
from app.models.render_job import RenderJob
from app.models.video_analytics_snapshot import VideoAnalyticsSnapshot
from app.services.channel_profile import ChannelProfileService
from app.services.youtube_errors import parse_youtube_api_error
from app.services.youtube_quota import YouTubeQuotaService
from app.services.youtube_uploader import YouTubeUploaderService
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_time_slot(slot_str: str) -> tuple[int, int] | None:
    parts = slot_str.strip().split(":")
    if len(parts) == 2:
        try:
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h < 24 and 0 <= m < 60:
                return h, m
        except ValueError:
            pass
    return None


class YouTubeAnalyticsService:
    """Polls YouTube metrics, records time-series snapshots, and derives slot performance."""

    @classmethod
    def poll_video_statistics(
        cls,
        db: Session,
        max_age_days: int = 14,
        force_all: bool = False,
    ) -> dict[str, Any]:
        """Poll YouTube Data API v3 for latest statistics on recently uploaded clips.

        Batches up to 50 video IDs per call, costing only 1 quota unit per batch.
        Default 14-day lookback covers the full 7-day velocity window so
        slowly-accumulating (quiet-day) views are captured.
        """
        creds = YouTubeUploaderService.get_credentials()
        if not creds:
            logger.info("YouTube statistics polling skipped: no valid credentials.")
            return {
                "polled_count": 0,
                "updated_count": 0,
                "snapshots_created": 0,
                "message": "YouTube credentials not connected or expired.",
            }

        # Quota gate (analytics budget, default 2,000 units — independent of
        # the upload budget): only stops analytics when its own budget is spent.
        gate = YouTubeQuotaService.check_analytics_budget(db)
        if not gate["can_analytics"]:
            logger.warning(
                "YouTube analytics skipped: %s (%s units used today)",
                gate["analytics_block_reason"],
                gate["units_used"],
            )
            return {
                "polled_count": 0,
                "updated_count": 0,
                "snapshots_created": 0,
                "skipped": True,
                "message": f"Analytics skipped: YouTube quota budget gated ({gate['analytics_block_reason']}, {gate['units_used']}/{gate['daily_limit_units']} units used).",
                "quota": gate,
            }

        now_utc = datetime.now(UTC)
        cutoff = now_utc - timedelta(days=max_age_days)

        query = db.query(RenderJob).filter(
            RenderJob.youtube_video_id.isnot(None),
            RenderJob.youtube_upload_status == "completed",
        )
        if not force_all:
            query = query.filter(
                (RenderJob.youtube_uploaded_at >= cutoff)
                | (RenderJob.scheduled_publish_at >= cutoff)
                | (RenderJob.completed_at >= cutoff)
            )

        jobs = query.all()
        if not jobs:
            return {
                "polled_count": 0,
                "updated_count": 0,
                "snapshots_created": 0,
                "message": "No active uploaded videos found to poll.",
            }

        job_map: dict[str, RenderJob] = {j.youtube_video_id: j for j in jobs if j.youtube_video_id}
        video_ids = list(job_map.keys())

        # Batch into chunks of 50 (YouTube API cap, 1 unit per batch)
        batch_size = max(1, int(getattr(settings, "YOUTUBE_ANALYTICS_BATCH_LIMIT", 50)))
        batches = [video_ids[i : i + batch_size] for i in range(0, len(video_ids), batch_size)]

        total_snapshots = 0
        updated_jobs = 0

        try:
            youtube = build("youtube", "v3", credentials=creds)
        except Exception as e:
            logger.error("Failed to build YouTube service for analytics: %s", e)
            return {
                "polled_count": 0,
                "updated_count": 0,
                "snapshots_created": 0,
                "error": str(e),
                "message": f"Failed to initialize YouTube client: {e}",
            }

        for batch in batches:
            response: dict | None = None
            for attempt in range(
                max(1, int(getattr(settings, "YOUTUBE_BACKOFF_MAX_ATTEMPTS", 3))) + 1
            ):
                try:
                    request = youtube.videos().list(part="statistics", id=",".join(batch))
                    response = request.execute()
                    break
                except Exception as exc:
                    parsed = parse_youtube_api_error(
                        exc, quota_reset_at=YouTubeQuotaService.resets_at()
                    )
                    max_attempts = max(1, int(getattr(settings, "YOUTUBE_BACKOFF_MAX_ATTEMPTS", 3)))
                    if parsed.retryable and attempt < max_attempts:
                        YouTubeQuotaService.backoff_sleep(attempt)
                        continue
                    if parsed.api_quota_exhausted:
                        try:
                            YouTubeQuotaService.record_upload_failure(db, parsed)
                        except Exception:
                            db.rollback()
                    logger.warning("Failed to fetch statistics batch: %s", exc)
                    db.rollback()
                    response = None
                    break
            if response is None:
                continue
            try:
                # Charge 1 quota unit for this batch
                YouTubeQuotaService.record_units_used(db, 1)

                items = response.get("items", [])
                for item in items:
                    yt_id = item.get("id")
                    if not yt_id or yt_id not in job_map:
                        continue

                    job = job_map[yt_id]
                    stats = item.get("statistics", {})
                    views = int(stats.get("viewCount", 0))
                    likes = int(stats.get("likeCount", 0))
                    comments = int(stats.get("commentCount", 0))

                    # Determine effective publish timestamp
                    pub_dt = _as_utc(
                        job.scheduled_publish_at
                        or job.youtube_uploaded_at
                        or job.completed_at
                        or job.created_at
                    )
                    hours_elapsed = 0.0
                    if pub_dt:
                        hours_elapsed = max(0.0, (now_utc - pub_dt).total_seconds() / 3600.0)

                    # Create snapshot record
                    snapshot = VideoAnalyticsSnapshot(
                        job_id=job.id,
                        clip_id=job.clip_id,
                        youtube_video_id=yt_id,
                        recorded_at=now_utc,
                        published_at=pub_dt,
                        hours_since_publish=hours_elapsed,
                        view_count=views,
                        like_count=likes,
                        comment_count=comments,
                        raw_payload=json.dumps(stats),
                    )
                    db.add(snapshot)
                    total_snapshots += 1

                    # Update cached metrics on RenderJob
                    job.latest_view_count = views
                    job.latest_like_count = likes
                    job.latest_comment_count = comments
                    job.metrics_last_polled_at = now_utc

                    # Update velocity windows
                    if hours_elapsed <= 3.5:
                        job.velocity_3h = views
                    elif not job.velocity_3h:
                        # Find closest recorded snapshot to 3h
                        s3 = (
                            db.query(VideoAnalyticsSnapshot)
                            .filter(
                                VideoAnalyticsSnapshot.job_id == job.id,
                                VideoAnalyticsSnapshot.hours_since_publish >= 2.5,
                                VideoAnalyticsSnapshot.hours_since_publish <= 4.0,
                            )
                            .order_by(VideoAnalyticsSnapshot.hours_since_publish.asc())
                            .first()
                        )
                        if s3:
                            job.velocity_3h = s3.view_count

                    if hours_elapsed <= 25.0:
                        job.velocity_24h = views
                    elif not job.velocity_24h:
                        # Find closest recorded snapshot to 24h
                        s24 = (
                            db.query(VideoAnalyticsSnapshot)
                            .filter(
                                VideoAnalyticsSnapshot.job_id == job.id,
                                VideoAnalyticsSnapshot.hours_since_publish >= 22.0,
                                VideoAnalyticsSnapshot.hours_since_publish <= 26.0,
                            )
                            .order_by(VideoAnalyticsSnapshot.hours_since_publish.asc())
                            .first()
                        )
                        if s24:
                            job.velocity_24h = s24.view_count

                    # 72h window: catches uploads on quiet days (audience may
                    # not be active for 1-2 days after publish).
                    if hours_elapsed <= 73.0:
                        job.velocity_72h = views
                    elif not job.velocity_72h:
                        s72 = (
                            db.query(VideoAnalyticsSnapshot)
                            .filter(
                                VideoAnalyticsSnapshot.job_id == job.id,
                                VideoAnalyticsSnapshot.hours_since_publish >= 70.0,
                                VideoAnalyticsSnapshot.hours_since_publish <= 76.0,
                            )
                            .order_by(VideoAnalyticsSnapshot.hours_since_publish.asc())
                            .first()
                        )
                        if s72:
                            job.velocity_72h = s72.view_count

                    # 7d window: primary ranking signal for optimal slots.
                    if hours_elapsed <= 169.0:
                        job.velocity_7d = views
                    elif not job.velocity_7d:
                        s7d = (
                            db.query(VideoAnalyticsSnapshot)
                            .filter(
                                VideoAnalyticsSnapshot.job_id == job.id,
                                VideoAnalyticsSnapshot.hours_since_publish >= 166.0,
                                VideoAnalyticsSnapshot.hours_since_publish <= 172.0,
                            )
                            .order_by(VideoAnalyticsSnapshot.hours_since_publish.asc())
                            .first()
                        )
                        if s7d:
                            job.velocity_7d = s7d.view_count

                    updated_jobs += 1

                db.commit()

            except Exception as exc:
                logger.warning("Failed to fetch statistics batch: %s", exc)
                db.rollback()

        logger.info(
            "YouTube analytics poll completed: updated %d jobs, created %d snapshots across %d batches.",
            updated_jobs,
            total_snapshots,
            len(batches),
        )
        return {
            "polled_count": len(video_ids),
            "updated_count": updated_jobs,
            "snapshots_created": total_snapshots,
            "message": f"Successfully updated metrics for {updated_jobs} video(s).",
        }

    @classmethod
    def get_slot_analytics(cls, db: Session) -> dict[str, Any]:
        """Aggregate view velocity and engagement per configured daily upload slot."""
        slots_list, tz_name = ChannelProfileService.schedule_config(db)
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")

        parsed_slots: list[tuple[int, int, str]] = []
        for s in slots_list:
            parsed = _parse_time_slot(s)
            if parsed:
                parsed_slots.append((parsed[0], parsed[1], s))
        parsed_slots.sort()

        jobs = (
            db.query(RenderJob)
            .filter(
                RenderJob.youtube_video_id.isnot(None),
                RenderJob.youtube_upload_status == "completed",
            )
            .all()
        )

        def _match_slot(pub_dt: datetime) -> str:
            local_dt = pub_dt.astimezone(tz)
            if not parsed_slots:
                return f"{local_dt.hour:02d}:00"
            # Find slot with smallest absolute minute difference
            pub_mins = local_dt.hour * 60 + local_dt.minute
            best_slot = parsed_slots[0][2]
            min_diff = 9999
            for h, m, slot_str in parsed_slots:
                slot_mins = h * 60 + m
                diff = abs(pub_mins - slot_mins)
                if diff < min_diff:
                    min_diff = diff
                    best_slot = slot_str
            return best_slot

        stats_by_slot: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "videos_count": 0,
                "total_views": 0,
                "total_velocity_3h": 0,
                "total_velocity_24h": 0,
                "total_velocity_72h": 0,
                "total_velocity_7d": 0,
                "total_likes": 0,
                "total_comments": 0,
            }
        )

        # Initialize all configured slots so even slots with 0 videos show up
        for _, _, slot_str in parsed_slots:
            _ = stats_by_slot[slot_str]

        for job in jobs:
            pub_dt = _as_utc(
                job.scheduled_publish_at
                or job.youtube_uploaded_at
                or job.completed_at
                or job.created_at
            )
            if not pub_dt:
                continue

            slot_key = _match_slot(pub_dt)
            data = stats_by_slot[slot_key]
            data["videos_count"] += 1
            data["total_views"] += int(job.latest_view_count or 0)
            data["total_velocity_3h"] += int(job.velocity_3h or job.latest_view_count or 0)
            data["total_velocity_24h"] += int(job.velocity_24h or job.latest_view_count or 0)
            data["total_velocity_72h"] += int(
                getattr(job, "velocity_72h", 0) or job.latest_view_count or 0
            )
            data["total_velocity_7d"] += int(
                getattr(job, "velocity_7d", 0) or job.latest_view_count or 0
            )
            data["total_likes"] += int(job.latest_like_count or 0)
            data["total_comments"] += int(job.latest_comment_count or 0)

        slot_results: list[dict[str, Any]] = []
        for slot_str, data in stats_by_slot.items():
            cnt = data["videos_count"]
            avg_views = round(data["total_views"] / cnt, 1) if cnt > 0 else 0.0
            avg_vel_3h = round(data["total_velocity_3h"] / cnt, 1) if cnt > 0 else 0.0
            avg_vel_24h = round(data["total_velocity_24h"] / cnt, 1) if cnt > 0 else 0.0
            avg_vel_72h = round(data["total_velocity_72h"] / cnt, 1) if cnt > 0 else 0.0
            avg_vel_7d = round(data["total_velocity_7d"] / cnt, 1) if cnt > 0 else 0.0
            eng_rate = (
                round((data["total_likes"] + data["total_comments"]) / max(1, data["total_views"]), 4)
                if data["total_views"] > 0
                else 0.0
            )

            # Score formula (7d-primary): 50% 7d velocity + 25% 72h velocity
            # + 15% 24h velocity + 10% engagement rate. 3h is still reported
            # for early diagnostics but no longer drives the rank.
            perf_score = round(
                0.5 * avg_vel_7d
                + 0.25 * avg_vel_72h
                + 0.15 * avg_vel_24h
                + 0.1 * (eng_rate * 1000.0),
                1,
            )

            slot_results.append(
                {
                    "slot": slot_str,
                    "videos_count": cnt,
                    "avg_views": avg_views,
                    "avg_velocity_3h": avg_vel_3h,
                    "avg_velocity_24h": avg_vel_24h,
                    "avg_velocity_72h": avg_vel_72h,
                    "avg_velocity_7d": avg_vel_7d,
                    "engagement_rate": eng_rate,
                    "performance_score": perf_score,
                }
            )

        # Sort by performance score descending
        slot_results.sort(key=lambda s: (s["performance_score"], s["avg_views"]), reverse=True)
        for rank, item in enumerate(slot_results, start=1):
            item["rank"] = rank
            item["recommended"] = rank <= 4 and item["performance_score"] > 0

        recommended = [s["slot"] for s in slot_results if s.get("recommended")]
        if not recommended:
            # Fallback to chronological configured slots if no video data yet
            recommended = [s[2] for s in parsed_slots[:4]]

        best_slot_str = slot_results[0]["slot"] if slot_results else "None"
        best_score = slot_results[0]["performance_score"] if slot_results else 0.0

        summary = (
            f"Slot {best_slot_str} is your top performing time window (score: {best_score})."
            if jobs
            else "Publish videos across your daily slots to unlock data-driven slot optimization."
        )

        return {
            "timezone": tz_name,
            "total_tracked_videos": len(jobs),
            "slots": slot_results,
            "recommended_slots": sorted(recommended),
            "summary": summary,
        }

    @classmethod
    def apply_optimal_slots(cls, db: Session, top_n: int | None = None) -> dict[str, Any]:
        """Update ChannelProfile upload_slots to the highest-performing daily slots."""
        analytics = cls.get_slot_analytics(db)
        slots_ranked = [s["slot"] for s in analytics["slots"] if s["videos_count"] > 0]
        count = top_n or len(analytics.get("recommended_slots", [])) or 4

        target_slots = slots_ranked[:count] if len(slots_ranked) >= 2 else analytics["recommended_slots"][:count]
        target_slots = sorted(list(set(target_slots)))

        profile = ChannelProfileService.get_or_create(db)
        profile.upload_slots = json.dumps(target_slots)
        profile.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(profile)

        logger.info("Applied optimal upload slots to channel profile: %s", target_slots)
        return {
            "applied_slots": target_slots,
            "timezone": profile.upload_timezone,
            "message": f"Successfully updated daily upload slots to: {', '.join(target_slots)}",
        }

    @classmethod
    def get_clip_velocity_timeline(cls, db: Session, clip_id: str) -> dict[str, Any]:
        """Fetch time-series metric growth points for a specific clip."""
        job = db.query(RenderJob).filter(RenderJob.clip_id == clip_id).first()
        if not job:
            return {"clip_id": clip_id, "found": False, "snapshots": []}

        snapshots = (
            db.query(VideoAnalyticsSnapshot)
            .filter(VideoAnalyticsSnapshot.job_id == job.id)
            .order_by(VideoAnalyticsSnapshot.hours_since_publish.asc())
            .all()
        )

        return {
            "clip_id": clip_id,
            "job_id": job.id,
            "youtube_video_id": job.youtube_video_id,
            "latest_views": job.latest_view_count or 0,
            "latest_likes": job.latest_like_count or 0,
            "velocity_3h": job.velocity_3h or 0,
            "velocity_24h": job.velocity_24h or 0,
            "velocity_72h": getattr(job, "velocity_72h", 0) or 0,
            "velocity_7d": getattr(job, "velocity_7d", 0) or 0,
            "snapshots": [
                {
                    "hours": round(s.hours_since_publish, 2),
                    "views": s.view_count,
                    "likes": s.like_count,
                    "comments": s.comment_count,
                    "recorded_at": s.recorded_at.isoformat() if s.recorded_at else None,
                }
                for s in snapshots
            ],
        }


def execute_sync_analytics_job(max_age_days: int = 14) -> dict[str, Any]:
    """Execute YouTube statistics polling within a standalone DB session."""
    with get_task_db_session() as db:
        return YouTubeAnalyticsService.poll_video_statistics(db, max_age_days=max_age_days)


@celery_app.task(name="app.services.youtube_analytics.sync_video_analytics_task", rate_limit="10/m")
def sync_video_analytics_celery_task(max_age_days: int = 14) -> dict[str, Any]:
    """Celery task entry point for YouTube view statistics polling."""
    return execute_sync_analytics_job(max_age_days=max_age_days)
