"""OBS watch folder: zero-click ingest for streamers.

Point ``WATCH_DIR`` at the folder OBS writes finished recordings into and every
poll (or a manual ``POST /api/v1/videos/watch/scan``) catalogues new files:

    file appears -> stable? -> copy/move into data/downloads -> probe + thumbnail
    -> Video row -> auto-mine -> auto-stage

Stability matters because OBS is still writing the file when it first appears.
A file is only considered finished when its mtime is older than
``WATCH_STABILITY_SECONDS``, which avoids ingesting a truncated MP4 that would
fail to probe.
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_task_db_session
from app.models.watch_ingest import WatchIngest
from app.services.auto_mine import AutoMineService
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


class WatchFolderService:
    """Scan a folder for finished recordings and ingest them into the catalog."""

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def is_enabled() -> bool:
        """Whether a watch folder is configured."""
        return settings.watch_path is not None

    @staticmethod
    def fingerprint(path: Path) -> str:
        """Identity of a specific recording take (size + mtime)."""
        stat = path.stat()
        return f"{stat.st_size}:{int(stat.st_mtime)}"

    @classmethod
    def _candidate_files(cls) -> list[Path]:
        """Finished-looking video files in the watch folder, oldest first."""
        watch_path = settings.watch_path
        if watch_path is None or not watch_path.exists() or not watch_path.is_dir():
            return []

        allowed = set(settings.WATCH_VIDEO_EXTENSIONS)
        min_bytes = int(max(0.0, settings.WATCH_MIN_FILE_MB) * 1024 * 1024)
        now = time.time()

        candidates: list[Path] = []
        for entry in watch_path.iterdir():
            try:
                if not entry.is_file() or entry.is_symlink():
                    continue
                if entry.suffix.lower() not in allowed:
                    continue
                # OBS-side sidecar/partial files
                if entry.name.startswith(".") or entry.name.endswith(".tmp"):
                    continue
                stat = entry.stat()
                if stat.st_size < min_bytes:
                    continue
                if (now - stat.st_mtime) < settings.WATCH_STABILITY_SECONDS:
                    logger.debug(
                        "Watch folder: skipping %s (still being written)", entry.name
                    )
                    continue
                candidates.append(entry)
            except OSError as exc:
                logger.debug("Watch folder: could not stat %s: %s", entry, exc)

        candidates.sort(key=lambda p: p.stat().st_mtime)
        return candidates

    @classmethod
    def _ledger_entry(cls, db: Session, path: Path, fingerprint: str) -> WatchIngest:
        """Fetch or create the ledger row for a source path."""
        entry = (
            db.query(WatchIngest).filter(WatchIngest.source_path == str(path)).first()
        )
        if entry is None:
            entry = WatchIngest(
                id=f"watch_{uuid.uuid4().hex[:10]}",
                source_path=str(path),
                source_name=path.name,
                fingerprint=fingerprint,
                status="discovered",
            )
            db.add(entry)
            db.flush()
        return entry

    # ----------------------------------------------------------------- scanning

    @classmethod
    def scan(
        cls,
        db: Session,
        *,
        background_tasks: Any = None,
        ingest: bool = True,
        max_files: int | None = None,
    ) -> dict[str, Any]:
        """Ingest every new, finished recording found in the watch folder.

        Args:
            db: Active database session.
            background_tasks: Optional request-scoped dispatcher for auto-mine.
            ingest: When False, only report what would be ingested (dry run).
            max_files: Cap the number of files processed in this pass.
        """
        watch_path = settings.watch_path
        if watch_path is None:
            return {
                "enabled": False,
                "watch_dir": None,
                "discovered": 0,
                "ingested": 0,
                "skipped": 0,
                "failed": 0,
                "items": [],
                "message": "Watch folder is not configured (set WATCH_DIR).",
            }

        if not watch_path.exists() or not watch_path.is_dir():
            return {
                "enabled": True,
                "watch_dir": str(watch_path),
                "discovered": 0,
                "ingested": 0,
                "skipped": 0,
                "failed": 0,
                "items": [],
                "message": f"Watch folder does not exist: {watch_path}",
            }

        files = cls._candidate_files()
        if max_files is not None and max_files >= 0:
            files = files[:max_files]

        items: list[dict[str, Any]] = []
        ingested = skipped = failed = 0

        for path in files:
            try:
                fp = cls.fingerprint(path)
            except OSError:
                continue

            entry = cls._ledger_entry(db, path, fp)

            # Same take already ingested -> nothing to do.
            if entry.status == "ingested" and entry.fingerprint == fp:
                skipped += 1
                items.append(
                    {
                        "source_name": path.name,
                        "status": "already_ingested",
                        "video_id": entry.video_id,
                    }
                )
                continue

            if not ingest:
                items.append({"source_name": path.name, "status": "would_ingest"})
                continue

            # A rewritten recording keeps its row but gets re-ingested.
            entry.fingerprint = fp
            entry.file_size_bytes = path.stat().st_size
            entry.file_mtime = path.stat().st_mtime

            try:
                video = cls._ingest_file(db, path, background_tasks=background_tasks)
                entry.status = "ingested"
                entry.video_id = video.id
                entry.error_message = None
                entry.processed_at = datetime.now(UTC)
                db.commit()
                ingested += 1
                items.append(
                    {
                        "source_name": path.name,
                        "status": "ingested",
                        "video_id": video.id,
                        "title": video.title,
                    }
                )
                logger.info("Watch folder ingested %s as video %s", path, video.id)
            except Exception as exc:  # isolate per-file failures
                logger.warning("Watch folder failed to ingest %s: %s", path, exc)
                db.rollback()
                entry = cls._ledger_entry(db, path, fp)
                entry.status = "failed"
                entry.error_message = str(exc)
                entry.processed_at = datetime.now(UTC)
                db.commit()
                failed += 1
                items.append(
                    {
                        "source_name": path.name,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

        message = (
            f"Ingested {ingested} new recording(s)"
            f"{f', skipped {skipped} already ingested' if skipped else ''}"
            f"{f', {failed} failed' if failed else ''}."
            if (ingested or skipped or failed)
            else "No new recordings found in the watch folder."
        )
        return {
            "enabled": True,
            "watch_dir": str(watch_path),
            "discovered": len(files),
            "ingested": ingested,
            "skipped": skipped,
            "failed": failed,
            "items": items,
            "message": message,
        }

    @classmethod
    def _ingest_file(
        cls,
        db: Session,
        path: Path,
        *,
        background_tasks: Any = None,
    ):
        """Copy or move one recording into the catalog and kick off auto-mine."""
        # Imported lazily so watch_folder does not pull the whole video service
        # (and its Celery task graph) into the celery app import cycle.
        from app.services.videos import VideoService

        settings.downloads_path.mkdir(parents=True, exist_ok=True)
        video_id = f"watch_{uuid.uuid4().hex[:10]}"
        dest_path = settings.downloads_path / f"{video_id}{path.suffix.lower()}"

        if settings.WATCH_DELETE_AFTER_INGEST:
            shutil.move(str(path), str(dest_path))
        else:
            shutil.copy2(str(path), str(dest_path))

        video = VideoService.catalog_local_file(
            db=db,
            video_id=video_id,
            dest_path=dest_path,
            original_filename=path.name,
            channel_name="OBS Watch Folder",
        )

        AutoMineService.trigger_after_ingest(
            db, video.id, background_tasks=background_tasks
        )
        return video

    # ------------------------------------------------------------------- status

    @classmethod
    def status(cls, db: Session, *, recent_limit: int = 10) -> dict[str, Any]:
        """Report watch folder configuration and recent ingest history."""
        watch_path = settings.watch_path
        pending = 0
        exists = bool(watch_path and watch_path.exists() and watch_path.is_dir())
        if exists:
            try:
                pending = len(cls._candidate_files())
            except OSError:
                pending = 0

        recent = (
            db.query(WatchIngest)
            .order_by(WatchIngest.created_at.desc())
            .limit(max(1, recent_limit))
            .all()
        )

        return {
            "enabled": watch_path is not None,
            "watch_dir": str(watch_path) if watch_path else None,
            "exists": exists,
            "pending_files": pending,
            "poll_interval_minutes": settings.WATCH_POLL_INTERVAL_MINUTES,
            "delete_after_ingest": settings.WATCH_DELETE_AFTER_INGEST,
            "stability_seconds": settings.WATCH_STABILITY_SECONDS,
            "supported_extensions": list(settings.WATCH_VIDEO_EXTENSIONS),
            "recent_ingests": [row.to_dict() for row in recent],
        }


def execute_watch_folder_scan(db_session: Session | None = None) -> dict[str, Any]:
    """Run one watch folder scan with an owned or caller-provided session."""
    db = db_session if db_session is not None else get_task_db_session()
    try:
        return WatchFolderService.scan(db)
    except Exception:
        logger.exception("Watch folder scan failed")
        db.rollback()
        raise
    finally:
        if db_session is None:
            db.close()


@celery_app.task(bind=True, name="watch_folder_scan_task")
def watch_folder_scan_celery_task(self) -> dict[str, Any]:
    """Celery entry point for the periodic watch folder scan."""
    logger.info("Celery watch folder scan started (task_id: %s)", self.request.id)
    return execute_watch_folder_scan()
