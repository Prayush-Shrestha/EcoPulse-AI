"""Anomaly detection and history endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ml.model_loader import ModelRegistry, get_model_registry
from app.schemas.anomaly import (
    AnomalyDetectionResponse,
    AnomalyDetectRequest,
    AnomalyHistoryResponse,
    AnomalySummaryResponse,
)
from app.schemas.common import ErrorResponse, LocalDatetime
from app.services.anomaly_service import AnomalyService

router = APIRouter(prefix="/anomalies", tags=["anomalies"])

DbSession = Annotated[Session, Depends(get_db)]
Registry = Annotated[ModelRegistry, Depends(get_model_registry)]
StartQuery = Annotated[LocalDatetime | None, Query(description="Inclusive observation timestamp.")]
EndQuery = Annotated[LocalDatetime | None, Query(description="Inclusive observation timestamp.")]


@router.post(
    "/detect",
    response_model=AnomalyDetectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Score one observation",
    description=(
        "Score a minute with the saved Isolation Forest and its fitted scaler. "
        "Current readings are read from PostgreSQL when omitted. Prior 1-hour and "
        "24-hour statistics are always computed from earlier observations only. "
        "A flagged result is a deviation candidate, not a confirmed fault."
    ),
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse, "description": "Model or database unavailable"},
    },
)
def detect_anomaly(
    payload: AnomalyDetectRequest,
    db: DbSession,
    registry: Registry,
) -> AnomalyDetectionResponse:
    return AnomalyService(db, registry).detect(payload)


@router.get(
    "",
    response_model=AnomalyHistoryResponse,
    summary="List stored anomaly detections",
    responses={422: {"model": ErrorResponse}},
)
def anomaly_history(
    db: DbSession,
    detection_method: str | None = None,
    is_anomaly: bool | None = None,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnomalyHistoryResponse:
    return AnomalyService(db).history(
        detection_method=detection_method,
        is_anomaly=is_anomaly,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/summary",
    response_model=AnomalySummaryResponse,
    summary="Summarise stored detection history",
    description=(
        "Counts are computed from anomaly_records. They describe detections made "
        "through this API, not labelled model accuracy."
    ),
)
def anomaly_summary(db: DbSession) -> AnomalySummaryResponse:
    return AnomalyService(db).summary()
