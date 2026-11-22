"""Anomaly-detection request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import LocalDatetime, MinuteAlignedDatetime, Pagination

Severity = Literal["none", "low", "medium", "high"]
DetectionMethod = Literal["isolation_forest"]


class AnomalyMeasurements(BaseModel):
    """Current minute measurements.

    If this object is omitted, the current minute is read from PostgreSQL.
    """

    global_active_power: float = Field(ge=0)
    global_reactive_power: float = Field(ge=0)
    voltage: float = Field(gt=0)
    global_intensity: float = Field(ge=0)
    sub_metering_1: float = Field(ge=0)
    sub_metering_2: float = Field(ge=0)
    sub_metering_3: float = Field(ge=0)


class AnomalyDetectRequest(BaseModel):
    observation_timestamp: MinuteAlignedDatetime = Field(
        description=(
            "Whole-minute local civil timestamp to score. A complete prior "
            "24-hour history must already exist in PostgreSQL."
        )
    )
    measurements: AnomalyMeasurements | None = Field(
        default=None,
        description=(
            "Optional current-minute measurements. When omitted, the observation "
            "is loaded from energy_readings."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "observation_timestamp": "2010-11-26T21:02:00",
                }
            ]
        }
    )


class AnomalyDetectionResponse(BaseModel):
    id: int
    detected_at: datetime
    observation_timestamp: datetime
    energy_consumption_kwh: float
    anomaly_score: float
    detection_method: str
    severity: Severity
    is_anomaly: bool
    threshold: float
    model_name: str
    model_version: str
    label_status: str


class AnomalyRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    detected_at: datetime
    observation_timestamp: datetime
    energy_consumption_kwh: float
    anomaly_score: float
    detection_method: str
    severity: Severity
    is_anomaly: bool


class AnomalyHistoryResponse(Pagination):
    items: list[AnomalyRecordResponse]


class AnomalyHistoryQuery(BaseModel):
    detection_method: str | None = None
    is_anomaly: bool | None = None
    start: LocalDatetime | None = None
    end: LocalDatetime | None = None


class AnomalyMethodSummary(BaseModel):
    detection_method: str
    total_observations: int = Field(ge=0)
    total_anomalies: int = Field(ge=0)
    anomaly_percentage: float = Field(ge=0, le=100)
    start_timestamp: datetime | None
    end_timestamp: datetime | None


class AnomalySummaryResponse(BaseModel):
    methods: list[AnomalyMethodSummary]
    label_status: str
