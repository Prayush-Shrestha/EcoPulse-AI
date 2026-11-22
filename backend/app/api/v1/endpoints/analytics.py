"""Application-level analytics endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import AnalyticsOverviewResponse, ConsumptionPatternsResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    summary="Application overview",
    description=(
        "Combine stored energy totals, recent hourly/daily trends, forecast "
        "history and anomaly-history counts. Every value comes from PostgreSQL."
    ),
)
def analytics_overview(db: DbSession) -> AnalyticsOverviewResponse:
    return AnalyticsService(db).overview()


@router.get(
    "/consumption-patterns",
    response_model=ConsumptionPatternsResponse,
    summary="Hour-of-day, weekday and monthly consumption patterns",
    description=(
        "Aggregate real minute observations into descriptive average consumption "
        "profiles. Units are kWh per stored minute observation."
    ),
)
def consumption_patterns(db: DbSession) -> ConsumptionPatternsResponse:
    return AnalyticsService(db).consumption_patterns()
