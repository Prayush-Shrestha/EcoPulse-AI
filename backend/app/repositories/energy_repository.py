"""PostgreSQL queries for energy readings and aggregates."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Integer, Select, cast, func, select
from sqlalchemy.orm import Session

from app.models.energy import EnergyReading

Granularity = str


def _apply_range(
    statement: Select[Any],
    start: datetime | None,
    end: datetime | None,
) -> Select[Any]:
    if start is not None:
        statement = statement.where(EnergyReading.timestamp >= start)
    if end is not None:
        statement = statement.where(EnergyReading.timestamp <= end)
    return statement


class EnergyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_readings(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
        descending: bool,
    ) -> tuple[list[EnergyReading], int]:
        statement = _apply_range(select(EnergyReading), start, end)
        total = int(
            self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        order = EnergyReading.timestamp.desc() if descending else EnergyReading.timestamp.asc()
        rows = self.db.scalars(statement.order_by(order).offset(offset).limit(limit)).all()
        return list(rows), total

    def summary(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
    ) -> dict[str, Any]:
        statement = select(
            func.min(EnergyReading.timestamp),
            func.max(EnergyReading.timestamp),
            func.count(EnergyReading.id),
            func.coalesce(func.sum(EnergyReading.energy_consumption_kwh), 0),
            func.coalesce(func.avg(EnergyReading.energy_consumption_kwh), 0),
            func.coalesce(func.max(EnergyReading.energy_consumption_kwh), 0),
            func.coalesce(func.min(EnergyReading.energy_consumption_kwh), 0),
        )
        if start is not None:
            statement = statement.where(EnergyReading.timestamp >= start)
        if end is not None:
            statement = statement.where(EnergyReading.timestamp <= end)

        row = self.db.execute(statement).one()
        return {
            "start_timestamp": row[0],
            "end_timestamp": row[1],
            "total_observations": int(row[2] or 0),
            "total_consumption_kwh": float(row[3] or 0),
            "average_consumption_kwh": float(row[4] or 0),
            "maximum_consumption_kwh": float(row[5] or 0),
            "minimum_consumption_kwh": float(row[6] or 0),
        }

    def aggregate(
        self,
        *,
        granularity: Granularity,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
        descending: bool,
    ) -> tuple[list[tuple[datetime, float, int]], int]:
        bucket = func.date_trunc(granularity, EnergyReading.timestamp).label("period_start")
        statement = (
            select(
                bucket,
                func.coalesce(func.sum(EnergyReading.energy_consumption_kwh), 0),
                func.count(EnergyReading.id),
            )
            .group_by(bucket)
            .order_by(bucket.desc() if descending else bucket.asc())
        )
        if start is not None:
            statement = statement.where(EnergyReading.timestamp >= start)
        if end is not None:
            statement = statement.where(EnergyReading.timestamp <= end)

        total = int(
            self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = self.db.execute(statement.offset(offset).limit(limit)).all()
        return [(row[0], float(row[1]), int(row[2])) for row in rows], total

    def get_at(self, timestamp: datetime) -> EnergyReading | None:
        return self.db.scalar(
            select(EnergyReading).where(EnergyReading.timestamp == timestamp)
        )

    def hour_observation_count(self, hour_start: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.count(EnergyReading.id)).where(
                    EnergyReading.timestamp >= hour_start,
                    EnergyReading.timestamp < hour_start + timedelta(hours=1),
                )
            )
            or 0
        )

    def latest_complete_hour(self) -> datetime | None:
        bucket = func.date_trunc("hour", EnergyReading.timestamp)
        return self.db.scalar(
            select(bucket)
            .group_by(bucket)
            .having(func.count(EnergyReading.id) == 60)
            .order_by(bucket.desc())
            .limit(1)
        )

    def hourly_history(
        self,
        *,
        end_hour: datetime,
        hours: int = 200,
    ) -> list[tuple[datetime, float]]:
        """Return complete hourly totals ending at ``end_hour`` inclusive."""

        bucket = func.date_trunc("hour", EnergyReading.timestamp).label("period_start")
        start = end_hour - timedelta(hours=hours - 1)
        statement = (
            select(bucket, func.sum(EnergyReading.energy_consumption_kwh))
            .where(
                EnergyReading.timestamp >= start,
                EnergyReading.timestamp < end_hour + timedelta(hours=1),
            )
            .group_by(bucket)
            .having(func.count(EnergyReading.id) == 60)
            .order_by(bucket.asc())
        )
        rows = self.db.execute(statement).all()
        return [(row[0], float(row[1])) for row in rows]

    def minute_history(
        self,
        *,
        timestamp: datetime,
        hours: int = 25,
    ) -> Sequence[EnergyReading]:
        statement = (
            select(EnergyReading)
            .where(
                EnergyReading.timestamp >= timestamp - timedelta(hours=hours),
                EnergyReading.timestamp < timestamp,
                EnergyReading.is_imputed.is_(False),
            )
            .order_by(EnergyReading.timestamp.asc())
        )
        return self.db.scalars(statement).all()

    def hourly_pattern(self) -> list[tuple[int, float, int]]:
        hour = cast(func.extract("hour", EnergyReading.timestamp), Integer).label("hour")
        rows = self.db.execute(
            select(
                hour,
                func.avg(EnergyReading.energy_consumption_kwh),
                func.count(EnergyReading.id),
            )
            .group_by(hour)
            .order_by(hour)
        ).all()
        return [(int(row[0]), float(row[1]), int(row[2])) for row in rows]

    def weekday_pattern(self) -> list[tuple[int, float, int]]:
        # isodow is 1=Monday ... 7=Sunday; the trained features use 0=Monday.
        weekday = cast(
            func.extract("isodow", EnergyReading.timestamp) - 1,
            Integer,
        ).label("day_of_week")
        rows = self.db.execute(
            select(
                weekday,
                func.avg(EnergyReading.energy_consumption_kwh),
                func.count(EnergyReading.id),
            )
            .group_by(weekday)
            .order_by(weekday)
        ).all()
        return [(int(row[0]), float(row[1]), int(row[2])) for row in rows]

    def monthly_pattern(self) -> list[tuple[int, float, int]]:
        month = cast(func.extract("month", EnergyReading.timestamp), Integer).label("month")
        rows = self.db.execute(
            select(
                month,
                func.avg(EnergyReading.energy_consumption_kwh),
                func.count(EnergyReading.id),
            )
            .group_by(month)
            .order_by(month)
        ).all()
        return [(int(row[0]), float(row[1]), int(row[2])) for row in rows]
