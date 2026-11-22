"""PostgreSQL persistence for anomaly-detection history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.anomaly import AnomalyRecord


class AnomalyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, record: AnomalyRecord) -> AnomalyRecord:
        self.db.add(record)
        self.db.flush()
        return record

    def list_history(
        self,
        *,
        detection_method: str | None,
        is_anomaly: bool | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AnomalyRecord], int]:
        statement = select(AnomalyRecord)
        if detection_method:
            statement = statement.where(
                AnomalyRecord.detection_method == detection_method
            )
        if is_anomaly is not None:
            statement = statement.where(AnomalyRecord.is_anomaly.is_(is_anomaly))
        if start is not None:
            statement = statement.where(AnomalyRecord.observation_timestamp >= start)
        if end is not None:
            statement = statement.where(AnomalyRecord.observation_timestamp <= end)

        total = int(
            self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = self.db.scalars(
            statement.order_by(
                AnomalyRecord.detected_at.desc(),
                AnomalyRecord.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        ).all()
        return list(rows), total

    def summary(self) -> list[dict[str, Any]]:
        anomaly_count = func.sum(
            case((AnomalyRecord.is_anomaly.is_(True), 1), else_=0)
        )
        rows = self.db.execute(
            select(
                AnomalyRecord.detection_method,
                func.count(AnomalyRecord.id),
                anomaly_count,
                func.min(AnomalyRecord.observation_timestamp),
                func.max(AnomalyRecord.observation_timestamp),
            ).group_by(AnomalyRecord.detection_method)
        ).all()

        summaries: list[dict[str, Any]] = []
        for method, total, anomalies, start, end in rows:
            summaries.append(
                {
                    "detection_method": method,
                    "total_observations": int(total or 0),
                    "total_anomalies": int(anomalies or 0),
                    "anomaly_percentage": (
                        float(anomalies or 0) / float(total) * 100.0 if total else 0.0
                    ),
                    "start_timestamp": start,
                    "end_timestamp": end,
                }
            )
        return summaries

    def overview(self) -> dict[str, Any]:
        anomaly_count = func.sum(
            case((AnomalyRecord.is_anomaly.is_(True), 1), else_=0)
        )
        row = self.db.execute(
            select(
                func.count(AnomalyRecord.id),
                anomaly_count,
                func.max(AnomalyRecord.detected_at),
            )
        ).one()
        total = int(row[0] or 0)
        anomalies = int(row[1] or 0)
        return {
            "total_observations": total,
            "total_anomalies": anomalies,
            "anomaly_percentage": (anomalies / total * 100.0) if total else 0.0,
            "latest_detected_at": row[2],
        }
