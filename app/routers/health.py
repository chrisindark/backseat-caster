from fastapi import APIRouter
from fastapi_health import health

from app.config import settings
from app.core.responses import BaseResponse
from app.schemas.preflight import PreflightReport
from app.services.health import (
    celery_failure_handler,
    celery_success_handler,
    check_celery_broker,
    check_celery_workers,
    check_database,
    check_liveness,
    check_redis,
    liveness_failure_handler,
    liveness_success_handler,
    readiness_failure_handler,
    readiness_success_handler,
)
from app.services.preflight import run_preflight_checks

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=BaseResponse[dict])
def health_check():
    """Basic health check endpoint returning API status and system preflight diagnostics."""
    preflight = run_preflight_checks()
    return BaseResponse.success_response(
        response={
            "status": preflight.status,
            "ready": preflight.ready,
            "version": settings.VERSION,
            "downloads_dir": str(settings.downloads_path),
            "preflight": preflight.model_dump(),
        }
    )


@router.get("/preflight", response_model=BaseResponse[PreflightReport])
def get_preflight_report():
    """Dedicated endpoint returning full preflight diagnostic checks for CLI tools and storage."""
    preflight = run_preflight_checks()
    return BaseResponse.success_response(response=preflight)


router.add_api_route(
    "/live",
    health(
        [check_liveness],
        success_handler=liveness_success_handler,
        failure_handler=liveness_failure_handler,
        success_status=200,
        failure_status=503,
    ),
    methods=["GET"],
    summary="Process liveness probe",
)

router.add_api_route(
    "/ready",
    health(
        [check_database, check_redis],
        success_handler=readiness_success_handler,
        failure_handler=readiness_failure_handler,
        success_status=200,
        failure_status=503,
    ),
    methods=["GET"],
    summary="Readiness probe for Redis, and Database with 1s timeouts",
)

router.add_api_route(
    "/worker",
    health(
        [check_celery_broker, check_celery_workers],
        success_handler=celery_success_handler,
        failure_handler=celery_failure_handler,
        success_status=200,
        failure_status=503,
    ),
    methods=["GET"],
    summary="Celery worker and broker readiness probe",
)

router.add_api_route(
    "/celery",
    health(
        [check_celery_broker, check_celery_workers],
        success_handler=celery_success_handler,
        failure_handler=celery_failure_handler,
        success_status=200,
        failure_status=503,
    ),
    methods=["GET"],
    summary="Celery worker and broker readiness probe alias",
)
