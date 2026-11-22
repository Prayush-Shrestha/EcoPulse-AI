"""Energy reading, summary and aggregate endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ErrorResponse, LocalDatetime
from app.schemas.energy import (
    EnergyAggregateResponse,
    EnergyListResponse,
    EnergySummaryResponse,
)
from app.services.energy_service import EnergyService

router = APIRouter(prefix="/energy", tags=["energy"])

DbSession = Annotated[Session, Depends(get_db)]
StartQuery = Annotated[
    LocalDatetime | None,
    Query(description="Inclusive naive local timestamp or ISO date."),
]
EndQuery = Annotated[
    LocalDatetime | None,
    Query(description="Inclusive naive local timestamp or ISO date."),
]
LimitQuery = Annotated[int, Query(ge=1, le=5000, description="Maximum rows per page.")]
OffsetQuery = Annotated[int, Query(ge=0, description="Number of rows to skip.")]


@router.get(
    "",
    response_model=EnergyListResponse,
    summary="List minute-level energy readings",
    description=(
        "Return stored minute observations with optional time filtering, sorting "
        "and pagination. Timestamps are naive local civil time from the source."
    ),
    responses={422: {"model": ErrorResponse}},
)
def list_energy(
    db: DbSession,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: LimitQuery = 100,
    offset: OffsetQuery = 0,
    order: Literal["asc", "desc"] = "desc",
) -> EnergyListResponse:
    return EnergyService(db).list_readings(
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        descending=order == "desc",
    )


@router.get(
    "/summary",
    response_model=EnergySummaryResponse,
    summary="Summarise consumption",
    description=(
        "Return total, average, minimum and maximum per-observation consumption "
        "for the filtered range, plus observation count and actual date coverage."
    ),
    responses={422: {"model": ErrorResponse}},
)
def energy_summary(
    db: DbSession,
    start: StartQuery = None,
    end: EndQuery = None,
) -> EnergySummaryResponse:
    return EnergyService(db).summary(start=start, end=end)


@router.get(
    "/hourly",
    response_model=EnergyAggregateResponse,
    summary="Hourly aggregated consumption",
    description=(
        "Aggregate stored minute readings into clock-hours. Observation counts and "
        "completeness are returned so partial boundary hours are explicit."
    ),
    responses={422: {"model": ErrorResponse}},
)
def hourly_energy(
    db: DbSession,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: LimitQuery = 1000,
    offset: OffsetQuery = 0,
    order: Literal["asc", "desc"] = "asc",
) -> EnergyAggregateResponse:
    return EnergyService(db).aggregate(
        granularity="hour",
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        descending=order == "desc",
    )


@router.get(
    "/daily",
    response_model=EnergyAggregateResponse,
    summary="Daily aggregated consumption",
    responses={422: {"model": ErrorResponse}},
)
def daily_energy(
    db: DbSession,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: LimitQuery = 1000,
    offset: OffsetQuery = 0,
    order: Literal["asc", "desc"] = "asc",
) -> EnergyAggregateResponse:
    return EnergyService(db).aggregate(
        granularity="day",
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        descending=order == "desc",
    )


@router.get(
    "/monthly",
    response_model=EnergyAggregateResponse,
    summary="Monthly aggregated consumption",
    responses={422: {"model": ErrorResponse}},
)
def monthly_energy(
    db: DbSession,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: LimitQuery = 1000,
    offset: OffsetQuery = 0,
    order: Literal["asc", "desc"] = "asc",
) -> EnergyAggregateResponse:
    return EnergyService(db).aggregate(
        granularity="month",
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        descending=order == "desc",
    )
