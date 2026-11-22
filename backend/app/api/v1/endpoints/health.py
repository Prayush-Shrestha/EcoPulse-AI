"""Health and readiness endpoints including ML model status."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.ml.model_loader import ModelRegistry, get_model_registry
from app.schemas.health import HealthCheck, HealthResponse, LivenessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


def _database_check(db: Session) -> HealthCheck:
    started = perf_counter()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health checks must never crash the API
        logger.warning("PostgreSQL health check failed (%s)", type(exc).__name__)
        return HealthCheck(status="unavailable", detail="Database check failed.")

    latency_ms = round((perf_counter() - started) * 1000, 2)
    return HealthCheck(status="ok", latency_ms=latency_ms)


def _model_check(registry: ModelRegistry, key: str) -> HealthCheck:
    artifact = registry.forecast if key == "forecasting" else registry.anomaly
    if artifact is None:
        return HealthCheck(
            status="unavailable",
            detail=registry.errors.get(key, "Model artefact is not loaded."),
        )
    return HealthCheck(
        status="ok",
        detail=f"{artifact.name} {artifact.version} loaded.",
    )


def _collect_health(
    db: Session,
    settings: Settings,
    registry: ModelRegistry,
) -> HealthResponse:
    registry.load()
    checks = {
        "api": HealthCheck(status="ok"),
        "database": _database_check(db),
        "forecast_model": _model_check(registry, "forecasting"),
        "anomaly_model": _model_check(registry, "anomaly_detection"),
    }
    status = "ok" if all(check.status == "ok" for check in checks.values()) else "degraded"

    return HealthResponse(
        status=status,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(UTC),
        checks=checks,
    )


@router.get(
    "",
    response_model=HealthResponse,
    summary="Aggregate health",
    description=(
        "Report API, PostgreSQL and saved-model health without failing the request. "
        "Use /health/ready for a readiness probe with a 503 response."
    ),
)
def health(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    registry: Annotated[ModelRegistry, Depends(get_model_registry)],
) -> HealthResponse:
    return _collect_health(db, settings, registry)


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
)
def liveness(settings: Annotated[Settings, Depends(get_settings)]) -> LivenessResponse:
    return LivenessResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "A dependency is unavailable"}},
    summary="Readiness probe",
)
def readiness(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    registry: Annotated[ModelRegistry, Depends(get_model_registry)],
) -> HealthResponse:
    payload = _collect_health(db, settings, registry)
    if payload.status != "ok":
        response.status_code = 503
    return payload
