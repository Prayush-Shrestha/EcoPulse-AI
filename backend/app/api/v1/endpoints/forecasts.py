"""Forecast generation and history endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ml.model_loader import ModelRegistry, get_model_registry
from app.schemas.common import ErrorResponse, LocalDatetime
from app.schemas.forecast import (
    ForecastHistoryResponse,
    ForecastRecordResponse,
    ForecastRequest,
    ForecastResponse,
)
from app.services.forecasting_service import ForecastingService

router = APIRouter(prefix="/forecasts", tags=["forecasts"])

DbSession = Annotated[Session, Depends(get_db)]
Registry = Annotated[ModelRegistry, Depends(get_model_registry)]
StartQuery = Annotated[LocalDatetime | None, Query(description="Inclusive forecast timestamp.")]
EndQuery = Annotated[LocalDatetime | None, Query(description="Inclusive forecast timestamp.")]


@router.post(
    "/predict",
    response_model=ForecastResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a recursive hourly forecast",
    description=(
        "Use the saved Phase 4 Random Forest with causal lag and rolling features. "
        "Multi-step horizons are generated recursively; no future actual readings "
        "are used. Every returned point is persisted to forecast_records."
    ),
    responses={
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse, "description": "Model or database unavailable"},
    },
)
def predict_forecast(
    payload: ForecastRequest,
    db: DbSession,
    registry: Registry,
) -> ForecastResponse:
    return ForecastingService(db, registry).predict(payload)


@router.get(
    "/history",
    response_model=ForecastHistoryResponse,
    summary="List stored forecasts",
    responses={422: {"model": ErrorResponse}},
)
def forecast_history(
    db: DbSession,
    model_name: str | None = None,
    forecast_horizon: int | None = None,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ForecastHistoryResponse:
    return ForecastingService(db).history(
        model_name=model_name,
        forecast_horizon=forecast_horizon,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/latest",
    response_model=ForecastRecordResponse,
    summary="Most recent stored forecast point",
    responses={404: {"model": ErrorResponse}},
)
def latest_forecast(db: DbSession) -> ForecastRecordResponse:
    return ForecastingService(db).latest()
