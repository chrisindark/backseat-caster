"""Startup preflight checker for media engines, CLI binaries, and disk storage.

Validates that critical dependencies (FFmpeg, FFprobe, yt-dlp) and adequate local
disk space are available before heavy download, rendering, or clipping tasks begin.
Surfaces diagnostics in the startup log, the /health endpoint, and the web UI.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from app.config import settings
from app.schemas.preflight import DiskStatus, PreflightReport, ToolStatus

logger = logging.getLogger(__name__)

# Cached report instance across app lifetime
_LAST_PREFLIGHT_REPORT: PreflightReport | None = None


def check_ffmpeg() -> ToolStatus:
    """Check if FFmpeg executable is present and inspect its version."""
    bin_path = shutil.which("ffmpeg")
    if not bin_path:
        return ToolStatus(
            name="ffmpeg",
            status="error",
            installed=False,
            version=None,
            path=None,
            error="FFmpeg binary not found on system PATH",
            remedy=(
                "Install FFmpeg: 'brew install ffmpeg' (macOS) or "
                "'sudo apt-get install -y ffmpeg' (Debian/Ubuntu)."
            ),
        )

    version_str: str | None = None
    try:
        proc = subprocess.run(
            [bin_path, "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0,
        )
        if proc.stdout:
            match = re.search(r"ffmpeg version\s+([^\s,]+)", proc.stdout)
            if match:
                version_str = match.group(1)
            else:
                version_str = proc.stdout.splitlines()[0][:40]
    except Exception as exc:
        logger.debug("Failed executing ffmpeg -version: %s", exc)
        version_str = "unknown"

    return ToolStatus(
        name="ffmpeg",
        status="ok",
        installed=True,
        version=version_str,
        path=bin_path,
        error=None,
        remedy=None,
    )


def check_ffprobe() -> ToolStatus:
    """Check if FFprobe executable is present and inspect its version."""
    bin_path = shutil.which("ffprobe")
    if not bin_path:
        return ToolStatus(
            name="ffprobe",
            status="error",
            installed=False,
            version=None,
            path=None,
            error="FFprobe binary not found on system PATH",
            remedy=(
                "Install FFmpeg suite (includes ffprobe): 'brew install ffmpeg' (macOS) or "
                "'sudo apt-get install -y ffmpeg' (Debian/Ubuntu)."
            ),
        )

    version_str: str | None = None
    try:
        proc = subprocess.run(
            [bin_path, "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0,
        )
        if proc.stdout:
            match = re.search(r"ffprobe version\s+([^\s,]+)", proc.stdout)
            if match:
                version_str = match.group(1)
            else:
                version_str = proc.stdout.splitlines()[0][:40]
    except Exception as exc:
        logger.debug("Failed executing ffprobe -version: %s", exc)
        version_str = "unknown"

    return ToolStatus(
        name="ffprobe",
        status="ok",
        installed=True,
        version=version_str,
        path=bin_path,
        error=None,
        remedy=None,
    )


def check_ytdlp() -> ToolStatus:
    """Check if yt-dlp is available either as a Python module or CLI binary."""
    # 1. Check Python module first (used directly by YtdlpService)
    module_installed = False
    module_version: str | None = None
    try:
        import yt_dlp

        module_installed = True
        module_version = getattr(getattr(yt_dlp, "version", None), "__version__", None)
    except Exception:
        pass

    # 2. Check CLI binary on PATH
    cli_path = shutil.which("yt-dlp")
    cli_version: str | None = None
    if cli_path:
        try:
            proc = subprocess.run(
                [cli_path, "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2.0,
            )
            cli_version = proc.stdout.strip() if proc.stdout else None
        except Exception:
            pass

    if module_installed:
        return ToolStatus(
            name="yt-dlp",
            status="ok",
            installed=True,
            version=module_version or cli_version or "installed",
            path=cli_path or "python:yt_dlp",
            error=None,
            remedy=None,
        )

    if cli_path:
        return ToolStatus(
            name="yt-dlp",
            status="ok",
            installed=True,
            version=cli_version or "installed",
            path=cli_path,
            error=None,
            remedy=None,
        )

    return ToolStatus(
        name="yt-dlp",
        status="error",
        installed=False,
        version=None,
        path=None,
        error="yt-dlp module or CLI binary not found",
        remedy="Install yt-dlp: 'uv sync' or 'pip install yt-dlp'.",
    )


def check_disk_space(
    target_path: Path | str | None = None,
    min_required_gb: float | None = None,
) -> DiskStatus:
    """Probe storage volume containing local downloads and renders."""
    min_gb = min_required_gb or settings.PREFLIGHT_MIN_DISK_SPACE_GB

    # Resolve target directory (or its existing parent)
    resolved_path: Path
    if target_path:
        resolved_path = Path(target_path).resolve()
    else:
        resolved_path = Path(settings.DOWNLOADS_DIR).resolve()

    probe_dir = resolved_path
    while not probe_dir.exists() and probe_dir != probe_dir.parent:
        probe_dir = probe_dir.parent

    try:
        total, used, free = shutil.disk_usage(probe_dir)
        total_gb = round(total / (1024**3), 2)
        used_gb = round(used / (1024**3), 2)
        free_gb = round(free / (1024**3), 2)
        pct_used = round((used / max(1, total)) * 100.0, 1)

        if free_gb < 0.5:
            status = "error"
            error = (
                f"Critical disk storage: only {free_gb} GB free on {probe_dir} "
                f"(requires >= {min_gb} GB)."
            )
            remedy = (
                "Free disk space immediately before downloading or rendering videos."
            )
        elif free_gb < min_gb:
            status = "warning"
            error = (
                f"Low disk storage: {free_gb} GB free on {probe_dir} "
                f"(recommended >= {min_gb} GB)."
            )
            remedy = (
                "Consider cleaning up old VOD downloads or renders to prevent failures."
            )
        else:
            status = "ok"
            error = None
            remedy = None

        return DiskStatus(
            path=str(probe_dir),
            status=status,
            total_gb=total_gb,
            used_gb=used_gb,
            free_gb=free_gb,
            percent_used=pct_used,
            min_required_gb=min_gb,
            error=error,
            remedy=remedy,
        )
    except Exception as exc:
        logger.warning("Disk space check failed on %s: %s", probe_dir, exc)
        return DiskStatus(
            path=str(probe_dir),
            status="warning",
            total_gb=0.0,
            used_gb=0.0,
            free_gb=0.0,
            percent_used=0.0,
            min_required_gb=min_gb,
            error=f"Unable to read disk usage: {exc}",
            remedy=None,
        )


def run_preflight_checks(
    min_disk_space_gb: float | None = None,
    force_refresh: bool = True,
) -> PreflightReport:
    """Run all preflight dependency checks and generate aggregate diagnostic report."""
    global _LAST_PREFLIGHT_REPORT

    if not force_refresh and _LAST_PREFLIGHT_REPORT is not None:
        return _LAST_PREFLIGHT_REPORT

    ffmpeg_res = check_ffmpeg()
    ffprobe_res = check_ffprobe()
    ytdlp_res = check_ytdlp()
    disk_res = check_disk_space(min_required_gb=min_disk_space_gb)

    checks = {
        "ffmpeg": ffmpeg_res.model_dump(),
        "ffprobe": ffprobe_res.model_dump(),
        "yt_dlp": ytdlp_res.model_dump(),
        "disk_space": disk_res.model_dump(),
    }

    errors: list[str] = []
    warnings: list[str] = []

    for name, res in [
        ("FFmpeg", ffmpeg_res),
        ("FFprobe", ffprobe_res),
        ("yt-dlp", ytdlp_res),
    ]:
        if res.status == "error":
            errors.append(f"{name}: {res.error} (Remedy: {res.remedy})")
        elif res.status == "warning":
            warnings.append(f"{name}: {res.error}")

    if disk_res.status == "error":
        errors.append(f"Storage: {disk_res.error}")
    elif disk_res.status == "warning":
        warnings.append(f"Storage: {disk_res.error}")

    ready = len(errors) == 0
    if not ready:
        overall_status = "unhealthy"
    elif len(warnings) > 0:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    report = PreflightReport(
        ready=ready,
        status=overall_status,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )
    _LAST_PREFLIGHT_REPORT = report
    return report


def log_preflight_report(report: PreflightReport) -> None:
    """Print high-visibility diagnostic banner on backend application startup."""
    checks = report.checks
    ffmpeg_check = checks.get("ffmpeg", {})
    ffprobe_check = checks.get("ffprobe", {})
    ytdlp_check = checks.get("yt_dlp", {})
    disk_check = checks.get("disk_space", {})

    status_icon = "✓" if report.ready else "✗"
    box_header = f"=== BackseatCaster Preflight System Check [{status_icon}] ==="
    separator = "=" * len(box_header)

    logger.info(separator)
    logger.info(box_header)
    logger.info(
        "  ffmpeg     : %s (v%s - %s)",
        ffmpeg_check.get("status", "unknown").upper(),
        ffmpeg_check.get("version") or "?",
        ffmpeg_check.get("path") or "missing",
    )
    logger.info(
        "  ffprobe    : %s (v%s - %s)",
        ffprobe_check.get("status", "unknown").upper(),
        ffprobe_check.get("version") or "?",
        ffprobe_check.get("path") or "missing",
    )
    logger.info(
        "  yt-dlp     : %s (v%s - %s)",
        ytdlp_check.get("status", "unknown").upper(),
        ytdlp_check.get("version") or "?",
        ytdlp_check.get("path") or "missing",
    )
    logger.info(
        "  Disk Space : %s (%.1f GB free / %.1f GB total on %s)",
        disk_check.get("status", "unknown").upper(),
        disk_check.get("free_gb", 0.0),
        disk_check.get("total_gb", 0.0),
        disk_check.get("path", "./data"),
    )

    if report.warnings:
        for w in report.warnings:
            logger.warning("  ⚠ Warning: %s", w)

    if report.errors:
        for err in report.errors:
            logger.error("  ✗ Error: %s", err)

    logger.info(separator)
