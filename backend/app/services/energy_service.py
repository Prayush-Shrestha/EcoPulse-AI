"""Business logic for energy readings and aggregates."""

from __future__ import annotations

import calendar
from datetime import datetime

from sqlalchemy.orm import Session

from app.repositories.energy_repository import EnergyRepository
from app.schemas.energy import (
    EnergyAggregatePoint,
    EnergyAggregateResponse,
    EnergyListResponse,
    EnergyReadingResponse,
    EnergySummaryResponse,
)
from app.services.common import validate_time_range


def _expected_observations(granularity: str, period_start: datetime) -> int:
    if granularity == "hour":
        return 60
    if granularity == "day":
        return 1_440
    days = calendar.monthrange(period_start.year, period_start.month)[1]
    return days * 1_440


class EnergyService:
    GRANULARITY_LABELS = {"hour": "hourly", "day": "daily", "month": "monthly"}

    def __init__(self, db: Session) -> None:
        self.repository = EnergyRepository(db)

    def list_readings(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
        descending: bool,
    ) -> EnergyListResponse:
        validate_time_range(start, end)
        rows, total = self.repository.list_readings(
            start=start,
            end=end,
            limit=limit,
            offset=offset,
            descending=descending,
        )
        return EnergyListResponse(
            items=[EnergyReadingResponse.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def summary(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
    ) -> EnergySummaryResponse:
        validate_time_range(start, end)
        return EnergySummaryResponse(**self.repository.summary(start=start, end=end))

    def aggregate(
        self,
        *,
        granularity: str,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
        descending: bool,
    ) -> EnergyAggregateResponse:
        validate_time_range(start, end)
        rows, total = self.repository.aggregate(
            granularity=granularity,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
            descending=descending,
        )
        items = []
        for period_start, consumption, observation_count in rows:
            expected = _expected_observations(granularity, period_start)
            items.append(
                EnergyAggregatePoint(
                    period_start=period_start,
                    consumption_kwh=consumption,
                    observation_count=observation_count,
                    expected_observations=expected,
                    is_complete=observation_count == expected,
                )
            )
        return EnergyAggregateResponse(
            granularity=self.GRANULARITY_LABELS[granularity],
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )
