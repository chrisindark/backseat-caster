"""Unit and API tests for system startup preflight checks (ffmpeg, ffprobe, yt-dlp, disk)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.schemas.preflight import PreflightReport
from app.services.preflight import (
    check_disk_space,
    check_ffmpeg,
    check_ffprobe,
    check_ytdlp,
    run_preflight_checks,
)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_check_ffmpeg_detected():
    """Verify check_ffmpeg detects installed binary and extracts version."""
    with (
        patch("shutil.which", return_value="/usr/local/bin/ffmpeg"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(
            stdout="ffmpeg version 7.1 Copyright (c) 2000-2024", returncode=0
        )
        res = check_ffmpeg()
        assert res.installed is True
        assert res.status == "ok"
        assert res.version == "7.1"
        assert res.path == "/usr/local/bin/ffmpeg"
        assert res.error is None


def test_check_ffmpeg_missing():
    """Verify check_ffmpeg provides installation remedy when missing."""
    with patch("shutil.which", return_value=None):
        res = check_ffmpeg()
        assert res.installed is False
        assert res.status == "error"
        assert "not found" in res.error
        assert "brew install ffmpeg" in res.remedy


def test_check_ffprobe_detected():
    """Verify check_ffprobe detects binary and extracts version."""
    with (
        patch("shutil.which", return_value="/usr/local/bin/ffprobe"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(
            stdout="ffprobe version 7.1 Copyright (c) 2007-2024", returncode=0
        )
        res = check_ffprobe()
        assert res.installed is True
        assert res.status == "ok"
        assert res.version == "7.1"


def test_check_ffprobe_missing():
    """Verify check_ffprobe returns helpful error when missing."""
    with patch("shutil.which", return_value=None):
        res = check_ffprobe()
        assert res.installed is False
        assert res.status == "error"
        assert "not found" in res.error


def test_check_ytdlp_detected():
    """Verify check_ytdlp detects presence via module or binary."""
    res = check_ytdlp()
    assert res.installed is True
    assert res.status == "ok"
    assert res.version is not None


def test_check_ytdlp_missing():
    """Verify check_ytdlp reports missing when neither module nor CLI is available."""
    with (
        patch("builtins.__import__", side_effect=ImportError("No module named yt_dlp")),
        patch("shutil.which", return_value=None),
    ):
        res = check_ytdlp()
        assert res.installed is False
        assert res.status == "error"
        assert "Install yt-dlp" in res.remedy


def test_check_disk_space_ok(tmp_path):
    """Verify check_disk_space correctly reports healthy storage."""
    with patch(
        "shutil.disk_usage",
        return_value=(500 * (1024**3), 200 * (1024**3), 300 * (1024**3)),
    ):
        res = check_disk_space(target_path=tmp_path, min_required_gb=2.0)
        assert res.status == "ok"
        assert res.free_gb == 300.0
        assert res.total_gb == 500.0
        assert res.error is None


def test_check_disk_space_warning_and_critical(tmp_path):
    """Verify check_disk_space triggers warning when space < min_gb and error when < 0.5 GB."""
    # Warning case: 1.5 GB free (< 2.0 GB min)
    with patch(
        "shutil.disk_usage",
        return_value=(100 * (1024**3), 98.5 * (1024**3), 1.5 * (1024**3)),
    ):
        res = check_disk_space(target_path=tmp_path, min_required_gb=2.0)
        assert res.status == "warning"
        assert "Low disk storage" in res.error

    # Critical error case: 0.2 GB free
    with patch(
        "shutil.disk_usage",
        return_value=(100 * (1024**3), 99.8 * (1024**3), 0.2 * (1024**3)),
    ):
        res_crit = check_disk_space(target_path=tmp_path, min_required_gb=2.0)
        assert res_crit.status == "error"
        assert "Critical disk storage" in res_crit.error


def test_run_preflight_checks_aggregate():
    """Verify run_preflight_checks builds aggregate PreflightReport."""
    report = run_preflight_checks(force_refresh=True)
    assert isinstance(report, PreflightReport)
    assert "ffmpeg" in report.checks
    assert "ffprobe" in report.checks
    assert "yt_dlp" in report.checks
    assert "disk_space" in report.checks
    assert report.status in ("healthy", "degraded", "unhealthy")


def test_health_endpoints_surface_preflight(client):
    """Verify GET /api/v1/health and GET /api/v1/health/preflight surface preflight diagnostics."""
    # 1. Main health endpoint
    res = client.get(f"{settings.API_PREFIX}/health")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    resp = data["response"]
    assert "status" in resp
    assert "ready" in resp
    assert "preflight" in resp
    assert "ffmpeg" in resp["preflight"]["checks"]
    assert "disk_space" in resp["preflight"]["checks"]

    # 2. Dedicated preflight endpoint
    res_pref = client.get(f"{settings.API_PREFIX}/health/preflight")
    assert res_pref.status_code == 200
    pref_data = res_pref.json()
    assert pref_data["success"] is True
    pref = pref_data["response"]
    assert "checks" in pref
    assert "ready" in pref
    assert "errors" in pref
    assert "warnings" in pref
