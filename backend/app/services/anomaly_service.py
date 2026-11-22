"""Anomaly-detection service using the persisted Isolation Forest."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.core.errors import (
    InsufficientHistoryError,
    NotFoundError,
    PredictionError,
    RequestValidationError,
)
from app.ml.inference import build_anomaly_features
from app.ml.model_loader import ModelRegistry, get_model_registry
from app.models.anomaly import AnomalyRecord
from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.energy_repository import EnergyRepository
from app.schemas.anomaly import (
    AnomalyDetectionResponse,
    AnomalyDetectRequest,
    AnomalyHistoryResponse,
    AnomalyRecordResponse,
    AnomalySummaryResponse,
)
from app.services.common import validate_time_range

DETECTION_METHOD = "isolation_forest"
LABEL_STATUS = (
    "Unsupervised deviation candidate, not a confirmed electricity fault. "
    "No labelled accuracy, precision, recall or F1 is claimed."
)
# Request bodies use lower_snake_case; the saved Phase 4 model expects the
# original dataset column names, so explicit measurements are translated.
EXPLICIT_MEASUREMENT_COLUMNS = {
    "global_active_power": "Global_active_power",
    "global_reactive_power": "Global_reactive_power",
    "voltage": "Voltage",
    "global_intensity": "Global_intensity",
    "sub_metering_1": "Sub_metering_1",
    "sub_metering_2": "Sub_metering_2",
    "sub_metering_3": "Sub_metering_3",
}


def _severity(score: float, is_anomaly: bool) -> str:
    """Heuristic ranking only; not a calibrated fault severity."""

    if not is_anomaly:
        return "none"
    if score <= -0.15:
        return "high"
    if score <= -0.08:
        return "medium"
    return "low"


class AnomalyService:
    def __init__(
        self,
        db: Session,
        registry: ModelRegistry | None = None,
    ) -> None:
        self.db = db
        self.energy_repository = EnergyRepository(db)
        self.anomaly_repository = AnomalyRepository(db)
        self.registry = registry or get_model_registry()

    def detect(self, request: AnomalyDetectRequest) -> AnomalyDetectionResponse:
        artifact = self.registry.require_anomaly()
        timestamp = pd.Timestamp(request.observation_timestamp)
        stored = self.energy_repository.get_at(timestamp.to_pydatetime())

        if request.measurements is None:
            if stored is None:
                raise NotFoundError(
                    "No energy reading exists at the requested timestamp."
                )
            if stored.is_imputed:
                raise RequestValidationError(
                    "The stored observation is interpolated; anomaly scoring is "
                    "only defined for observed minutes.",
                )
            measurements = {
                "Global_active_power": float(stored.global_active_power),
                "Global_reactive_power": float(stored.global_reactive_power),
                "Voltage": float(stored.voltage),
                "Global_intensity": float(stored.global_intensity),
                "Sub_metering_1": float(stored.sub_metering_1),
                "Sub_metering_2": float(stored.sub_metering_2),
                "Sub_metering_3": float(stored.sub_metering_3),
            }
            energy_consumption = float(stored.energy_consumption_kwh)
        else:
            explicit = request.measurements.model_dump()
            measurements = {
                column: float(explicit[field])
                for field, column in EXPLICIT_MEASUREMENT_COLUMNS.items()
            }
            energy_consumption = measurements["Global_active_power"] / 60.0

        history_rows = self.energy_repository.minute_history(
            timestamp=timestamp.to_pydatetime(),
            hours=25,
        )
        if not history_rows:
            raise InsufficientHistoryError(
                "A complete prior 24-hour history is required before scoring."
            )
        history = pd.DataFrame(
            [
                {
                    "timestamp": row.timestamp,
                    "Global_active_power": float(row.global_active_power),
                }
                for row in history_rows
            ]
        )

        features = build_anomaly_features(
            history,
            timestamp,
            measurements,
            artifact.feature_names,
        )
        score, is_anomaly = artifact.score(features)
        if not pd.notna(score):
            raise PredictionError("The anomaly model returned an invalid score.")

        record = AnomalyRecord(
            observation_timestamp=timestamp.to_pydatetime(),
            energy_consumption_kwh=energy_consumption,
            anomaly_score=score,
            detection_method=DETECTION_METHOD,
            severity=_severity(score, is_anomaly),
            is_anomaly=is_anomaly,
        )
        self.anomaly_repository.add(record)
        self.db.commit()
        self.db.refresh(record)

        return AnomalyDetectionResponse(
            id=record.id,
            detected_at=record.detected_at,
            observation_timestamp=record.observation_timestamp,
            energy_consumption_kwh=float(record.energy_consumption_kwh),
            anomaly_score=float(record.anomaly_score),
            detection_method=record.detection_method,
            severity=record.severity,
            is_anomaly=record.is_anomaly,
            threshold=artifact.threshold,
            model_name=artifact.name,
            model_version=artifact.version,
            label_status=LABEL_STATUS,
        )

    def history(
        self,
        *,
        detection_method: str | None,
        is_anomaly: bool | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
    ) -> AnomalyHistoryResponse:
        validate_time_range(start, end)
        rows, total = self.anomaly_repository.list_history(
            detection_method=detection_method,
            is_anomaly=is_anomaly,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
        return AnomalyHistoryResponse(
            items=[AnomalyRecordResponse.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def summary(self) -> AnomalySummaryResponse:
        return AnomalySummaryResponse(
            methods=self.anomaly_repository.summary(),
            label_status=LABEL_STATUS,
        )
