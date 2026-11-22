"""PostgreSQL persistence for forecast history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.forecast import ForecastRecord


class ForecastRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_all(self, records: list[ForecastRecord]) -> list[ForecastRecord]:
        self.db.add_all(records)
        self.db.flush()
        return records

    def list_history(
        self,
        *,
        model_name: str | None,
        forecast_horizon: int | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ForecastRecord], int]:
        statement = select(ForecastRecord)
        if model_name:
            statement = statement.where(ForecastRecord.model_name == model_name)
        if forecast_horizon is not None:
            statement = statement.where(
                ForecastRecord.forecast_horizon == forecast_horizon
            )
        if start is not None:
            statement = statement.where(ForecastRecord.forecast_timestamp >= start)
        if end is not None:
            statement = statement.where(ForecastRecord.forecast_timestamp <= end)

        total = int(
            self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = self.db.scalars(
            statement.order_by(
                ForecastRecord.created_at.desc(),
                ForecastRecord.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        ).all()
        return list(rows), total

    def latest(self) -> ForecastRecord | None:
        return self.db.scalar(
            select(ForecastRecord)
            .order_by(ForecastRecord.created_at.desc(), ForecastRecord.id.desc())
            .limit(1)
        )

    def overview(self) -> dict[str, Any]:
        row = self.db.execute(
            select(
                func.count(ForecastRecord.id),
                func.max(ForecastRecord.forecast_timestamp),
                func.max(ForecastRecord.created_at),
            )
        ).one()
        models = list(
            self.db.scalars(
                select(ForecastRecord.model_name).distinct().order_by(ForecastRecord.model_name)
            ).all()
        )
        return {
            "total_predictions": int(row[0] or 0),
            "latest_forecast_timestamp": row[1],
            "latest_generated_at": row[2],
            "models": models,
        }
