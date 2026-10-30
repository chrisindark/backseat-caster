"""Structured classification of YouTube Data API upload failures.

YouTube reports quota problems in two very different ways:

* ``quotaExceeded`` / ``dailyLimitExceeded`` — the Google Cloud project's
  Data API unit budget is exhausted (10,000 units/day by default).
* ``uploadLimitExceeded`` — the authenticated channel has reached its own
  video upload limit. This is *not* the Data API unit quota and is not fixed
  by waiting for the project quota; YouTube usually clears it within 24h.

The raw ``HttpError`` string is noisy and hides that distinction, so parse the
JSON error payload once and carry a stable code + retry hint to the API and UI.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

API_QUOTA_REASONS = {"quotaexceeded", "dailylimitexceeded"}
UPLOAD_LIMIT_REASONS = {"uploadlimitexceeded"}
RATE_LIMIT_REASONS = {"ratelimitexceeded", "userratelimitexceeded"}
AUTH_REASONS = {
    "autherror",
    "unauthorized",
    "forbidden",
    "insufficientpermissions",
}


@dataclass(frozen=True)
class GoogleErrorPayload:
    """The useful fields from a Google API error response."""

    status_code: int | None = None
    message: str = ""
    reason: str | None = None
    domain: str | None = None


class YouTubeUploadError(RuntimeError):
    """A YouTube upload failure with a UI-safe message and machine code."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        reason: str | None = None,
        http_status: int = 500,
        retry_at: datetime | None = None,
        api_quota_exhausted: bool = False,
        upload_limit_exceeded: bool = False,
        raw_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.user_message = message
        self.error_code = error_code
        self.reason = reason
        self.http_status = http_status
        self.retry_at = retry_at
        self.api_quota_exhausted = api_quota_exhausted
        self.upload_limit_exceeded = upload_limit_exceeded
        self.raw_detail = raw_detail


def _decode_content(content: Any) -> dict[str, Any] | None:
    if content is None:
        return None
    if isinstance(content, dict):
        return content
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8", errors="replace")
        except Exception:
            return None
    if not isinstance(content, str):
        return None
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_google_error_payload(
    content: Any, fallback_status: int | None = None
) -> GoogleErrorPayload:
    """Extract code/message/reason from a Google API JSON error payload."""
    data = _decode_content(content)
    if not data:
        return GoogleErrorPayload(status_code=fallback_status)

    error = data.get("error")
    if not isinstance(error, dict):
        error = data

    status_code = error.get("code")
    if not isinstance(status_code, int):
        status_code = fallback_status

    message = str(error.get("message") or "").strip()
    reason: str | None = None
    domain: str | None = None

    errors = error.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if not isinstance(item, dict):
                continue
            if item.get("reason") and reason is None:
                reason = str(item["reason"])
            if item.get("domain") and domain is None:
                domain = str(item["domain"])
            if not message and item.get("message"):
                message = str(item["message"])

    # Some newer Google responses put the reason under error.details.
    if reason is None and isinstance(error.get("details"), list):
        for item in error["details"]:
            if not isinstance(item, dict):
                continue
            if item.get("reason"):
                reason = str(item["reason"])
                break

    if reason is None and error.get("reason"):
        reason = str(error["reason"])

    return GoogleErrorPayload(
        status_code=status_code,
        message=message,
        reason=reason,
        domain=domain,
    )


def _fallback_reason_from_message(message: str) -> str | None:
    lowered = message.lower()
    if "exceeded your quota" in lowered:
        return "quotaExceeded"
    if "number of videos they may upload" in lowered:
        return "uploadLimitExceeded"
    if "rate limit" in lowered:
        return "rateLimitExceeded"
    return None


def _format_retry_at(retry_at: datetime | None) -> str:
    if retry_at is None:
        return "later"
    return retry_at.isoformat()


def legacy_youtube_error_message(raw: str | None) -> str | None:
    """Translate a raw ``HttpError`` string persisted by older releases.

    Existing ``render_jobs.youtube_upload_error`` rows can contain the full
    googleapiclient exception text. Keep the UI readable without a destructive
    data migration.
    """
    if not raw:
        return raw
    lowered = raw.lower()
    if "uploadlimitexceeded" in lowered:
        return (
            "YouTube rejected the upload because this channel has reached its "
            "video upload limit (uploadLimitExceeded). This is separate from the "
            "Data API unit quota and usually clears within 24 hours."
        )
    if "quotaexceeded" in lowered or "dailylimitexceeded" in lowered:
        return (
            "YouTube Data API quota is exhausted for this project. It resets at "
            "midnight Pacific; other uploads will fail until then."
        )
    if "ratelimitexceeded" in lowered or "userratelimitexceeded" in lowered:
        return "YouTube rate limit reached. Wait a few minutes, then retry the upload."
    return raw


def parse_youtube_api_error(
    exc: BaseException,
    *,
    quota_reset_at: datetime | None = None,
) -> YouTubeUploadError:
    """Convert a Google ``HttpError`` into a user-facing upload error."""
    if isinstance(exc, YouTubeUploadError):
        return exc

    raw_detail = str(exc)
    payload = GoogleErrorPayload()
    http_status = 500

    if isinstance(exc, HttpError):
        payload = extract_google_error_payload(
            getattr(exc, "content", None),
            fallback_status=getattr(getattr(exc, "resp", None), "status", None),
        )
        http_status = payload.status_code or getattr(exc.resp, "status", 500) or 500

    message = payload.message or raw_detail
    reason = payload.reason or _fallback_reason_from_message(message)
    reason_key = (reason or "").lower()

    if reason_key in API_QUOTA_REASONS:
        friendly = (
            "YouTube Data API daily quota is exhausted. The upload was rejected "
            f"before any video was created; quota resets at {_format_retry_at(quota_reset_at)} "
            "Pacific time. Other API calls may still use the remaining budget."
        )
        return YouTubeUploadError(
            friendly,
            error_code="api_quota_exceeded",
            reason=reason,
            http_status=429,
            retry_at=quota_reset_at,
            api_quota_exhausted=True,
            raw_detail=raw_detail,
        )

    if reason_key in UPLOAD_LIMIT_REASONS:
        friendly = (
            "YouTube rejected the upload because this channel has reached its "
            "video upload limit (uploadLimitExceeded). This is separate from the "
            "Data API unit quota and is not fixed by the local quota counter. "
            f"Retry after {_format_retry_at(quota_reset_at)}."
        )
        return YouTubeUploadError(
            friendly,
            error_code="upload_limit_exceeded",
            reason=reason,
            http_status=429,
            retry_at=quota_reset_at,
            upload_limit_exceeded=True,
            raw_detail=raw_detail,
        )

    if reason_key in RATE_LIMIT_REASONS:
        return YouTubeUploadError(
            "YouTube rate limit reached. Wait a few minutes, then retry the upload.",
            error_code="rate_limit_exceeded",
            reason=reason,
            http_status=429,
            raw_detail=raw_detail,
        )

    if reason_key in AUTH_REASONS or http_status == 401:
        return YouTubeUploadError(
            "YouTube authorization failed or the connected account lacks upload "
            "permission. Reconnect the channel and try again.",
            error_code="auth_error",
            reason=reason,
            http_status=401,
            raw_detail=raw_detail,
        )

    label = reason or ("HTTP " + str(http_status) if http_status else "API error")
    return YouTubeUploadError(
        f"YouTube upload failed ({label}): {message}",
        error_code="youtube_api_error",
        reason=reason,
        http_status=http_status if 400 <= http_status < 600 else 500,
        raw_detail=raw_detail,
    )
