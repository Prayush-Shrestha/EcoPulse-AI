"""Forecasting request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import HourAlignedDatetime, LocalDatetime, Pagination

HorizonHours = Literal[1, 6, 24, 48]
SUPPORTED_HORIZONS = (1, 6, 24, 48)


class ForecastRequest(BaseModel):
    horizon_hours: HorizonHours = Field(
        default=1,
        description=(
            "Number of hourly steps to forecast recursively. Supported values "
            "are 1, 6, 24 and 48."
        ),
    )
    base_timestamp: HourAlignedDatetime | None = Field(
        default=None,
        description=(
            "Complete clock-hour from which to forecast. When omitted, the latest "
            "complete hour in PostgreSQL is used."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "horizon_hours": 6,
                    "base_timestamp": "2010-11-26T15:00:00",
                }
            ]
        }
    )


class ForecastPoint(BaseModel):
    forecast_timestamp: datetime
    predicted_energy_kwh: float
    model_name: str
    model_version: str
    forecast_horizon: int = Field(ge=1, le=48)
    units: Literal["kWh"] = "kWh"


class ForecastResponse(BaseModel):
    generated_at: datetime
    base_timestamp: datetime
    horizon_hours: int = Field(ge=1, le=48)
    model_name: str
    model_version: str
    units: Literal["kWh"] = "kWh"
    items: list[ForecastPoint]


class ForecastRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    forecast_timestamp: datetime
    predicted_energy_kwh: float
    model_name: str
    model_version: str
    forecast_horizon: int = Field(ge=1, le=48)
    units: Literal["kWh"] = "kWh"


class ForecastHistoryResponse(Pagination):
    items: list[ForecastRecordResponse]


class ForecastHistoryQuery(BaseModel):
    model_name: str | None = None
    forecast_horizon: HorizonHours | None = None
    start: LocalDatetime | None = None
    end: LocalDatetime | None = None
