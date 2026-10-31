"""YouTube API v3 Service for OAuth authentication and programmatic video & Shorts uploads."""

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_task_db_session
from app.models.render_job import RenderJob
from app.models.video import Video
from app.rendering.config import DEFAULT_MAX_CLIP_SECONDS
from app.schemas.youtube import (
    YouTubeAuthStatusResponse,
    YouTubeAuthUrlResponse,
    YouTubeUploadResult,
)
from app.services.channel_profile import ChannelProfileService
from app.services.upload_metadata import (
    append_pinned_hashtags,
    apply_title_template,
    build_description,
    build_tags,
    build_title,
    merge_pinned_hashtags,
)
from app.services.youtube_errors import parse_youtube_api_error
from app.services.youtube_quota import YouTubeQuotaService
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class YouTubeUploaderService:
    """Manages YouTube OAuth authentication and uploads videos/Shorts via YouTube Data API v3."""

    # -------------------------------------------------------------------------
    # Authentication & Credentials Management
    # -------------------------------------------------------------------------

    @staticmethod
    def get_client_config() -> dict[str, Any] | None:
        """Resolve Google OAuth client configuration from file or settings."""
        client_secrets_path = settings.youtube_client_secrets_path
        if client_secrets_path.exists():
            try:
                with open(client_secrets_path) as f:
                    data = json.load(f)
                return data
            except Exception as e:
                logger.warning("Failed to load client_secrets.json: %s", e)

        if settings.YOUTUBE_CLIENT_ID and settings.YOUTUBE_CLIENT_SECRET:
            return {
                "web": {
                    "client_id": settings.YOUTUBE_CLIENT_ID,
                    "client_secret": settings.YOUTUBE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.YOUTUBE_REDIRECT_URI],
                }
            }

        return None

    @staticmethod
    def save_client_secrets(client_data: dict[str, Any] | str) -> None:
        """Save client secrets JSON to data directory."""
        path = settings.youtube_client_secrets_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(client_data, str):
            client_dict = json.loads(client_data)
        else:
            client_dict = client_data

        with open(path, "w") as f:
            json.dump(client_dict, f, indent=2)
        logger.info("Saved client secrets to %s", path)

    @staticmethod
    def get_credentials() -> Credentials | None:
        """Retrieve authorized Credentials, automatically refreshing expired access tokens."""
        token_path = settings.youtube_token_path
        creds: Credentials | None = None

        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(token_path), YOUTUBE_SCOPES
                )
            except Exception as e:
                logger.warning("Could not read credentials from %s: %s", token_path, e)

        if not creds and settings.YOUTUBE_REFRESH_TOKEN:
            client_config = YouTubeUploaderService.get_client_config()
            client_id = None
            client_secret = None
            if client_config:
                inner = client_config.get("web") or client_config.get("installed") or {}
                client_id = inner.get("client_id")
                client_secret = inner.get("client_secret")

            client_id = client_id or settings.YOUTUBE_CLIENT_ID
            client_secret = client_secret or settings.YOUTUBE_CLIENT_SECRET

            if client_id and client_secret:
                creds = Credentials(
                    None,
                    refresh_token=settings.YOUTUBE_REFRESH_TOKEN,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=YOUTUBE_SCOPES,
                )

        if creds:
            if (creds.expired or not creds.valid) and creds.refresh_token:
                try:
                    logger.info(
                        "YouTube access token expired or invalid, refreshing..."
                    )
                    creds.refresh(Request())
                    YouTubeUploaderService.save_credentials(creds)
                except Exception as e:
                    logger.error("Failed to refresh YouTube credentials: %s", e)
                    return None
            return creds

        return None

    @staticmethod
    def save_credentials(creds: Credentials) -> None:
        """Serialize authorized credentials to disk."""
        token_path = settings.youtube_token_path
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        logger.info("Saved YouTube authorized credentials to %s", token_path)

    # -------------------------------------------------------------------------
    # PKCE & State Storage Helpers
    # -------------------------------------------------------------------------

    _oauth_states_cache: ClassVar[dict[str, dict[str, Any]]] = {}

    @classmethod
    def _get_states_file_path(cls) -> Path:
        """Resolve path to local temporary file storing pending OAuth states."""
        return settings.youtube_token_path.parent / "youtube_oauth_states.json"

    @classmethod
    def _load_oauth_states(cls) -> dict[str, dict[str, Any]]:
        """Load pending OAuth state entries from disk/memory and prune expired entries."""
        states = dict(cls._oauth_states_cache)
        file_path = cls._get_states_file_path()
        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        states.update(data)
            except Exception as e:
                logger.warning("Could not read oauth states file: %s", e)

        # Prune expired states (> 15 minutes / 900 seconds)
        now = time.time()
        active = {
            s: v
            for s, v in states.items()
            if isinstance(v, dict) and now - v.get("created_at", 0) < 900
        }
        cls._oauth_states_cache = active
        return active

    @classmethod
    def _persist_oauth_states(cls, states: dict[str, dict[str, Any]]) -> None:
        """Write active states to disk and in-memory cache."""
        cls._oauth_states_cache = states
        file_path = cls._get_states_file_path()
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(states, f, indent=2)
        except Exception as e:
            logger.warning("Could not persist oauth states file: %s", e)

    @classmethod
    def _save_pkce_verifier(
        cls, state: str, code_verifier: str, redirect_uri: str | None = None
    ) -> None:
        """Save PKCE code verifier and redirect URI associated with an OAuth state."""
        states = cls._load_oauth_states()
        states[state] = {
            "state": state,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "created_at": time.time(),
        }
        cls._persist_oauth_states(states)
        logger.debug("Saved PKCE code verifier for OAuth state: %s", state)

    @classmethod
    def _get_and_consume_pkce_verifier(
        cls, state: str | None = None
    ) -> tuple[str | None, str | None]:
        """
        Retrieve and remove the code verifier and redirect URI for a given OAuth state.
        If state is None or not found, fall back to the most recent unexpired verifier.
        Returns (code_verifier, redirect_uri).
        """
        states = cls._load_oauth_states()
        entry: dict[str, Any] | None = None
        matched_state = state

        if state:
            if state in states:
                entry = states.pop(state)
            else:
                logger.warning("OAuth state mismatch or expired for state: %s", state)
                return None, None
        elif states:
            # Fall back to latest created active entry only if state parameter was not provided
            sorted_entries = sorted(
                states.items(),
                key=lambda item: item[1].get("created_at", 0),
                reverse=True,
            )
            matched_state, entry = sorted_entries[0]
            states.pop(matched_state, None)
            logger.info(
                "No state provided in callback; consumed latest pending OAuth state: %s",
                matched_state,
            )

        if entry:
            cls._persist_oauth_states(states)
            return entry.get("code_verifier"), entry.get("redirect_uri")

        return None, None

    @classmethod
    def generate_auth_url(
        cls, redirect_uri: str | None = None
    ) -> YouTubeAuthUrlResponse:
        """Generate Google OAuth 2.0 authorization URL and cache PKCE code verifier."""
        client_config = cls.get_client_config()
        if not client_config:
            raise ValueError(
                "YouTube OAuth client credentials not found. Configure YOUTUBE_CLIENT_ID and "
                "YOUTUBE_CLIENT_SECRET or place client_secrets.json in the data/ directory."
            )

        effective_redirect = redirect_uri or settings.YOUTUBE_REDIRECT_URI
        flow = Flow.from_client_config(
            client_config,
            scopes=YOUTUBE_SCOPES,
            redirect_uri=effective_redirect,
        )

        auth_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )

        code_verifier = getattr(flow, "code_verifier", None)
        if code_verifier and state:
            cls._save_pkce_verifier(
                state=state,
                code_verifier=code_verifier,
                redirect_uri=effective_redirect,
            )

        inner = client_config.get("web") or client_config.get("installed") or {}
        client_id = inner.get("client_id")

        return YouTubeAuthUrlResponse(
            auth_url=auth_url,
            redirect_uri=effective_redirect,
            client_id=client_id,
            state=state,
        )

    @classmethod
    def exchange_code(
        cls,
        code: str,
        redirect_uri: str | None = None,
        state: str | None = None,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        """Exchange authorization code for tokens and persist credentials."""
        client_config = cls.get_client_config()
        if not client_config:
            raise ValueError("YouTube OAuth client credentials not found.")

        # Resolve PKCE code_verifier and redirect_uri from state cache if not explicitly provided
        cached_verifier, cached_redirect = cls._get_and_consume_pkce_verifier(state)
        effective_verifier = code_verifier or cached_verifier
        effective_redirect = (
            redirect_uri or cached_redirect or settings.YOUTUBE_REDIRECT_URI
        )

        flow = Flow.from_client_config(
            client_config,
            scopes=YOUTUBE_SCOPES,
            redirect_uri=effective_redirect,
        )

        if effective_verifier:
            flow.code_verifier = effective_verifier

        fetch_kwargs: dict[str, Any] = {"code": code}
        if effective_verifier:
            fetch_kwargs["code_verifier"] = effective_verifier

        flow.fetch_token(**fetch_kwargs)
        creds = flow.credentials
        cls.save_credentials(creds)

        # Retrieve authorized channel info
        return cls.get_channel_info(creds)

    @staticmethod
    def get_channel_info(creds: Credentials) -> dict[str, Any]:
        """Fetch YouTube channel snippet for the authenticated user."""
        try:
            youtube = build("youtube", "v3", credentials=creds)
            res = (
                youtube.channels()
                .list(part="snippet,contentDetails", mine=True)
                .execute()
            )
            items = res.get("items", [])
            if not items:
                return {
                    "channel_title": "Authorized YouTube Account",
                    "channel_id": None,
                    "channel_handle": None,
                    "thumbnail_url": None,
                }

            snippet = items[0].get("snippet", {})
            channel_id = items[0].get("id")
            thumbnails = snippet.get("thumbnails", {})
            thumb = thumbnails.get("default", {}).get("url") or thumbnails.get(
                "medium", {}
            ).get("url")
            custom_url = snippet.get("customUrl")

            return {
                "channel_title": snippet.get("title"),
                "channel_id": channel_id,
                "channel_handle": custom_url,
                "thumbnail_url": thumb,
            }
        except Exception as e:
            logger.warning("Could not fetch YouTube channel info: %s", e)
            return {
                "channel_title": "Authorized YouTube Account",
                "channel_id": None,
                "channel_handle": None,
                "thumbnail_url": None,
                "error": str(e),
            }

    @staticmethod
    def get_auth_status() -> YouTubeAuthStatusResponse:
        """Check authentication status and return details of authorized channel."""
        client_config = YouTubeUploaderService.get_client_config()
        client_configured = client_config is not None

        creds = YouTubeUploaderService.get_credentials()
        if not creds:
            return YouTubeAuthStatusResponse(
                is_authenticated=False,
                client_configured=client_configured,
                message="Not authenticated. Connect YouTube to enable programmatic uploads.",
            )

        channel_info = YouTubeUploaderService.get_channel_info(creds)
        expires_at = creds.expiry.isoformat() if creds.expiry else None

        return YouTubeAuthStatusResponse(
            is_authenticated=True,
            channel_title=channel_info.get("channel_title"),
            channel_id=channel_info.get("channel_id"),
            channel_handle=channel_info.get("channel_handle"),
            thumbnail_url=channel_info.get("thumbnail_url"),
            scopes=list(creds.scopes or []),
            expires_at=expires_at,
            client_configured=client_configured,
            message="Authenticated successfully with YouTube Data API.",
        )

    @staticmethod
    def revoke_credentials() -> bool:
        """Revoke existing token with Google and remove local token file."""
        token_path = settings.youtube_token_path
        revoked = False
        if token_path.exists():
            try:
                token_path.unlink()
                revoked = True
            except Exception as e:
                logger.warning("Error deleting token file: %s", e)
        return revoked

    # -------------------------------------------------------------------------
    # Uploading Logic: Videos and Shorts
    # -------------------------------------------------------------------------

    @staticmethod
    def resolve_clip_file(
        clip_id: str,
        preferred_format: str | None = None,
    ) -> tuple[Path, str]:
        """
        Locate the rendered video file on disk for a given clip_id.
        Returns tuple of (file_path, resolved_format).
        """
        renders_root = settings.renders_path
        clip_dir = renders_root / clip_id

        if not clip_dir.exists() or not clip_dir.is_dir():
            raise FileNotFoundError(
                f"Rendered clip directory '{clip_id}' not found on disk."
            )

        candidates: list[str] = []
        if preferred_format:
            candidates.append(preferred_format)
        candidates.extend(["vertical_blur", "vertical_crop", "landscape"])

        for fmt in candidates:
            cand_path = clip_dir / f"{fmt}.mp4"
            if cand_path.exists():
                return cand_path, fmt

        # Fallback to any .mp4 file in the folder
        mp4_files = list(clip_dir.glob("*.mp4"))
        if mp4_files:
            fmt = mp4_files[0].stem
            return mp4_files[0], fmt

        raise FileNotFoundError(
            f"No rendered .mp4 video files found in clip directory '{clip_id}'"
        )

    @staticmethod
    def upload_clip_to_youtube(
        clip_id: str,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        privacy: str | None = None,
        format_override: str | None = None,
        is_short: bool | None = None,
        category_id: str = "20",
        publish_at: datetime | None = None,
        progress_callback: Callable[[float], None] | None = None,
        db_session: Session | None = None,
    ) -> YouTubeUploadResult:
        """
        Upload a rendered clip to YouTube using the YouTube Data API v3 resumable protocol.
        Distinguishes and optimizes for YouTube Shorts (9:16 aspect ratio, <= 60s)
        vs. regular landscape videos.
        """
        creds = YouTubeUploaderService.get_credentials()
        if not creds:
            raise RuntimeError(
                "YouTube is not authenticated. Please authenticate first via /api/v1/youtube/auth/url"
            )

        db = db_session if db_session is not None else get_task_db_session()
        job: RenderJob | None = None

        try:
            job = (
                db.query(RenderJob)
                .filter((RenderJob.clip_id == clip_id) | (RenderJob.id == clip_id))
                .first()
            )
            profile = ChannelProfileService.get_or_create(db)
            pinned_hashtags = ChannelProfileService.pinned_hashtags(profile)

            # Read staging metadata from DB or manifest.json
            staging_meta: dict[str, Any] = {}
            if job and job.upload_metadata:
                try:
                    staging_meta = json.loads(job.upload_metadata)
                except Exception:
                    pass

            manifest_path = settings.renders_path / clip_id / "manifest.json"
            manifest_data: dict[str, Any] = {}
            if manifest_path.exists():
                try:
                    with open(manifest_path) as f:
                        manifest_data = json.load(f)
                    if not staging_meta and "upload_selection" in manifest_data:
                        staging_meta = manifest_data["upload_selection"]
                except Exception:
                    pass

            # Resolve native publishAt scheduling: explicit argument wins,
            # otherwise fall back to the clip's staged schedule.
            scheduled_for = publish_at
            if scheduled_for is None and job is not None:
                scheduled_for = job.scheduled_publish_at
            if scheduled_for is not None and scheduled_for.tzinfo is None:
                scheduled_for = scheduled_for.replace(tzinfo=UTC)
            if scheduled_for is not None and scheduled_for <= datetime.now(
                UTC
            ) + timedelta(minutes=1):
                scheduled_for = None

            # Idempotency guard: never re-upload a clip that has already been
            # successfully published unless the caller explicitly overrides data.
            if (
                job is not None
                and job.youtube_video_id
                and (job.youtube_upload_status or "").lower() == "completed"
                and title is None
                and description is None
                and tags is None
                and privacy is None
                and format_override is None
                and is_short is None
            ):
                cached_url = job.youtube_upload_url or (
                    f"https://www.youtube.com/shorts/{job.youtube_video_id}"
                    if "shorts" in (job.youtube_upload_url or "")
                    else f"https://youtu.be/{job.youtube_video_id}"
                )
                cached_format = job.selected_format or "vertical_blur"
                cached_is_short = "/shorts/" in cached_url
                cached_title = f"Gameplay Highlight - {clip_id}"
                cached_privacy = "public"
                if job.upload_metadata:
                    try:
                        cached_meta = json.loads(job.upload_metadata)
                        cached_title = cached_meta.get("title") or cached_title
                        cached_privacy = cached_meta.get("privacy") or cached_privacy
                    except Exception:
                        pass
                return YouTubeUploadResult(
                    clip_id=clip_id,
                    youtube_video_id=job.youtube_video_id,
                    youtube_url=cached_url,
                    title=cached_title,
                    format=cached_format,
                    is_short=cached_is_short,
                    status="completed",
                    privacy=cached_privacy,
                    progress=100.0,
                    scheduled_publish_at=job.scheduled_publish_at.isoformat()
                    if job.scheduled_publish_at
                    else None,
                    uploaded_at=job.youtube_uploaded_at.isoformat()
                    if job.youtube_uploaded_at
                    else None,
                )

            preferred_format = (
                format_override
                or (job.selected_format if job else None)
                or staging_meta.get("preferred_format")
                or "vertical_blur"
            )

            video_file, resolved_format = YouTubeUploaderService.resolve_clip_file(
                clip_id=clip_id,
                preferred_format=preferred_format,
            )

            # Determine whether this is a YouTube Short
            # Short-form criteria: vertical/square aspect ratio and within the
            # upload ceiling (clip + branded bookends), 90s by default.
            budget_meta = manifest_data.get("duration_budget") or {}
            composed_duration = budget_meta.get("composed_seconds")
            duration = (
                float(composed_duration)
                if composed_duration
                else float(
                    (job.duration_seconds if job else None)
                    or manifest_data.get("request", {}).get("duration_seconds")
                    or manifest_data.get("clip", {}).get("duration_seconds")
                    or 15.0
                )
            )
            is_vertical = resolved_format in (
                "vertical_blur",
                "vertical_crop",
                "third_person",
                "direct_crop",
                "cinematic",
                "custom",
            ) or (resolved_format != "landscape")

            target_is_short = is_short
            if target_is_short is None:
                # Short-form covers the whole upload ceiling, not just 60s.
                target_is_short = is_vertical and (duration <= DEFAULT_MAX_CLIP_SECONDS)

            # Prepare title
            parent_video = (
                db.query(Video).filter(Video.id == job.video_id).first()
                if job
                else None
            )

            generated_title = False
            if title:
                final_title = title.strip()
            elif staging_meta.get("title"):
                final_title = str(staging_meta["title"]).strip()
            else:
                final_title = build_title(parent_video, job, clip_id)
                generated_title = True
            if generated_title and profile.title_template:
                final_title = apply_title_template(
                    profile.title_template,
                    final_title,
                    channel_name=profile.channel_name,
                    hero_name=staging_meta.get("hero_name"),
                    game=staging_meta.get("game"),
                    clip_id=clip_id,
                )

            if (
                target_is_short
                and "#Shorts" not in final_title
                and "#shorts" not in final_title
                and len(final_title) + len(" #Shorts") <= 100
            ):
                final_title = f"{final_title} #Shorts"
            final_title = final_title[:100]  # YouTube title limit

            # Prepare description
            final_desc = (
                description
                or staging_meta.get("description")
                or build_description(parent_video, job, clip_id, bool(target_is_short))
            ).strip()
            final_desc = append_pinned_hashtags(final_desc, pinned_hashtags)

            if (
                target_is_short
                and "#Shorts" not in final_desc
                and "#shorts" not in final_desc
            ):
                final_desc = f"{final_desc}\n#Shorts"

            # Prepare tags
            final_tags = (
                tags
                or staging_meta.get("tags")
                or build_tags(parent_video, job, bool(target_is_short))
            )
            final_tags = merge_pinned_hashtags(final_tags, pinned_hashtags)
            if target_is_short and "Shorts" not in final_tags:
                final_tags.append("Shorts")

            # Prepare privacy. A future publishAt requires a private upload;
            # YouTube releases the video at the scheduled instant.
            final_privacy = (
                privacy
                or staging_meta.get("privacy")
                or profile.default_privacy
                or "public"
            )
            if final_privacy not in ("private", "unlisted", "public"):
                final_privacy = "public"
            if scheduled_for is not None:
                final_privacy = "private"

            # Update job state in DB: uploading
            if job:
                job.youtube_upload_status = "uploading"
                job.youtube_upload_progress = 1.0
                job.youtube_upload_error = None
                db.commit()

            logger.info(
                "Starting YouTube upload for clip %s (format: %s, short: %s, privacy: %s): %s",
                clip_id,
                resolved_format,
                target_is_short,
                final_privacy,
                final_title,
            )

            youtube = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "title": final_title,
                    "description": final_desc,
                    "tags": final_tags,
                    "categoryId": category_id,
                },
                "status": {
                    "privacyStatus": final_privacy,
                    "selfDeclaredMadeForKids": False,
                },
            }
            if scheduled_for is not None:
                body["status"]["publishAt"] = (
                    scheduled_for.astimezone(UTC)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z")
                )

            media = MediaFileUpload(
                str(video_file),
                mimetype="video/mp4",
                chunksize=5 * 1024 * 1024,
                resumable=True,
            )

            insert_request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            # Resumable upload chunk loop with exponential backoff on retryable HTTP errors
            response = None
            last_pct = 0.0
            retry_count = 0
            max_retries = 5

            while response is None:
                try:
                    upload_status, response = insert_request.next_chunk()
                    if upload_status:
                        pct = round(upload_status.progress() * 100.0, 1)
                        if pct - last_pct >= 5.0 or pct >= 99.0:
                            last_pct = pct
                            if job:
                                job.youtube_upload_progress = pct
                                db.commit()
                            if progress_callback:
                                progress_callback(pct)
                    retry_count = 0  # reset on successful chunk
                except HttpError as err:
                    if (
                        err.resp.status in [500, 502, 503, 504]
                        and retry_count < max_retries
                    ):
                        retry_count += 1
                        wait_sec = 2**retry_count
                        logger.warning(
                            "Recoverable HTTP error %s uploading clip %s. Retrying in %ds...",
                            err.resp.status,
                            clip_id,
                            wait_sec,
                        )
                        time.sleep(wait_sec)
                    else:
                        raise

            uploaded_id = response.get("id")
            if not uploaded_id:
                raise RuntimeError(
                    "YouTube upload finished without returning a video ID."
                )

            # Only successful uploads consume the project's 1,600-unit API
            # budget in the local advisory counter. Rejected requests are
            # recorded separately with their actual YouTube error reason.
            quota_summary = YouTubeQuotaService.record_upload_success(db)
            logger.info(
                "YouTube quota after successful upload: %d/%d units used "
                "(%d upload(s) remaining)",
                quota_summary["units_used"],
                quota_summary["daily_limit_units"],
                quota_summary["uploads_remaining"],
            )

            # Construct final URL
            if target_is_short:
                youtube_url = f"https://www.youtube.com/shorts/{uploaded_id}"
            else:
                youtube_url = f"https://youtu.be/{uploaded_id}"

            uploaded_at_iso = datetime.now(UTC).isoformat()

            # Synchronize DB job and staging metadata with final upload state
            updated_upload_dict = {
                "is_selected": bool(job.is_selected_for_upload) if job else True,
                "preferred_format": resolved_format,
                "title": final_title,
                "description": final_desc,
                "tags": final_tags,
                "privacy": final_privacy,
                "updated_at": uploaded_at_iso,
            }

            # Update DB job
            if scheduled_for is not None:
                updated_upload_dict["scheduled_publish_at"] = scheduled_for.isoformat()
                updated_upload_dict["privacy"] = "private"

            if job:
                job.youtube_video_id = uploaded_id
                job.youtube_upload_status = "completed"
                job.youtube_upload_progress = 100.0
                job.youtube_upload_url = youtube_url
                job.youtube_uploaded_at = datetime.now(UTC)
                job.youtube_upload_error = None
                job.upload_metadata = json.dumps(updated_upload_dict)
                job.selected_format = resolved_format
                if scheduled_for is not None:
                    job.scheduled_publish_at = scheduled_for
                db.commit()

            # Update manifest.json with upload record and sync upload_selection
            if manifest_path.exists():
                try:
                    manifest_data["upload_selection"] = updated_upload_dict
                    manifest_data["youtube_upload"] = {
                        "video_id": uploaded_id,
                        "url": youtube_url,
                        "format": resolved_format,
                        "is_short": target_is_short,
                        "privacy": final_privacy,
                        "title": final_title,
                        "scheduled_publish_at": scheduled_for.isoformat()
                        if scheduled_for
                        else None,
                        "uploaded_at": uploaded_at_iso,
                    }
                    with open(manifest_path, "w") as f:
                        json.dump(manifest_data, f, indent=2)
                except Exception as e:
                    logger.warning(
                        "Failed updating manifest.json with youtube_upload: %s", e
                    )

            logger.info(
                "Successfully uploaded clip %s to YouTube: %s (id: %s)",
                clip_id,
                youtube_url,
                uploaded_id,
            )

            return YouTubeUploadResult(
                clip_id=clip_id,
                youtube_video_id=uploaded_id,
                youtube_url=youtube_url,
                title=final_title,
                format=resolved_format,
                is_short=target_is_short,
                status="completed",
                privacy=final_privacy,
                progress=100.0,
                scheduled_publish_at=scheduled_for.isoformat()
                if scheduled_for
                else None,
                uploaded_at=uploaded_at_iso,
            )

        except Exception as e:
            error = parse_youtube_api_error(
                e, quota_reset_at=YouTubeQuotaService.resets_at()
            )
            logger.exception(
                "Failed uploading clip %s to YouTube (%s)",
                clip_id,
                error.error_code,
            )
            if job:
                job.youtube_upload_status = "failed"
                job.youtube_upload_error = error.user_message
                try:
                    db.commit()
                except Exception as commit_err:
                    logger.warning(
                        "Could not commit upload failure state: %s", commit_err
                    )
            try:
                YouTubeQuotaService.record_upload_failure(db, error)
            except Exception as quota_err:
                logger.warning(
                    "Could not persist YouTube quota failure state: %s", quota_err
                )
            raise error from e
        finally:
            if db_session is None:
                import sys

                main_mod = sys.modules.get("app.main")
                fastapi_app = getattr(main_mod, "app", None) if main_mod else None
                from app.database import get_db

                is_overridden = bool(
                    fastapi_app
                    and hasattr(fastapi_app, "dependency_overrides")
                    and get_db in fastapi_app.dependency_overrides
                )
                if not is_overridden:
                    db.close()

    @staticmethod
    def upload_selected_clips(
        db: Session | None = None,
    ) -> list[YouTubeUploadResult]:
        """Upload all completed clips currently marked with is_selected_for_upload."""
        is_external_session = db is not None
        db_session = db if db is not None else get_task_db_session()
        try:
            jobs = (
                db_session.query(RenderJob)
                .filter(
                    RenderJob.is_selected_for_upload.is_(True),
                    RenderJob.status == "completed",
                    or_(
                        RenderJob.youtube_video_id.is_(None),
                        RenderJob.youtube_upload_status != "completed",
                    ),
                )
                .all()
            )

            results: list[YouTubeUploadResult] = []
            for job in jobs:
                try:
                    res = YouTubeUploaderService.upload_clip_to_youtube(
                        clip_id=job.clip_id,
                        db_session=db_session,
                    )
                    results.append(res)
                except Exception as e:
                    error = parse_youtube_api_error(
                        e, quota_reset_at=YouTubeQuotaService.resets_at()
                    )
                    logger.error(
                        "Failed uploading selected clip %s (%s): %s",
                        job.clip_id,
                        error.error_code,
                        error.user_message,
                    )
                    failed_privacy = "public"
                    if job.upload_metadata:
                        try:
                            meta = json.loads(job.upload_metadata)
                            failed_privacy = meta.get("privacy", "public")
                        except Exception:
                            pass
                    results.append(
                        YouTubeUploadResult(
                            clip_id=job.clip_id,
                            title=job.clip_id,
                            format=job.selected_format or "vertical_blur",
                            is_short=True,
                            status="failed",
                            privacy=failed_privacy,
                            error_message=error.user_message,
                            error_code=error.error_code,
                            retry_at=error.retry_at.isoformat()
                            if error.retry_at
                            else None,
                        )
                    )

            return results
        finally:
            if not is_external_session:
                import sys

                main_mod = sys.modules.get("app.main")
                fastapi_app = getattr(main_mod, "app", None) if main_mod else None
                from app.database import get_db

                is_overridden = bool(
                    fastapi_app
                    and hasattr(fastapi_app, "dependency_overrides")
                    and get_db in fastapi_app.dependency_overrides
                )
                if not is_overridden:
                    db_session.close()


@celery_app.task(bind=True, name="upload_clip_celery_task")
def upload_clip_celery_task(
    self,
    clip_id: str,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    privacy: str | None = None,
    format_override: str | None = None,
    is_short: bool | None = None,
    category_id: str = "20",
    publish_at: str | None = None,
):
    """Celery task for uploading video clip to YouTube."""
    logger.info("Celery task started: uploading clip %s to YouTube", clip_id)

    def on_progress(pct: float):
        self.update_state(state="PROGRESS", meta={"progress": pct})

    return YouTubeUploaderService.upload_clip_to_youtube(
        clip_id=clip_id,
        title=title,
        description=description,
        tags=tags,
        privacy=privacy,
        format_override=format_override,
        is_short=is_short,
        category_id=category_id,
        publish_at=datetime.fromisoformat(publish_at) if publish_at else None,
        progress_callback=on_progress,
    ).model_dump()


@celery_app.task(bind=True, name="batch_upload_clips_celery_task")
def batch_upload_clips_celery_task(self):
    """Celery task for uploading all selected clips to YouTube."""
    logger.info("Celery task started: batch uploading selected clips")
    results = YouTubeUploaderService.upload_selected_clips()
    return [r.model_dump() for r in results]
