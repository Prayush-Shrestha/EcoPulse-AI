"""Energy-data request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import LocalDatetime, Pagination


class EnergyReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    global_active_power: float
    global_reactive_power: float
    voltage: float
    global_intensity: float
    sub_metering_1: float
    sub_metering_2: float
    sub_metering_3: float
    energy_consumption_kwh: float
    is_imputed: bool


class EnergyListResponse(Pagination):
    items: list[EnergyReadingResponse]


class EnergySummaryResponse(BaseModel):
    start_timestamp: datetime | None
    end_timestamp: datetime | None
    total_observations: int = Field(ge=0)
    total_consumption_kwh: float = Field(ge=0)
    average_consumption_kwh: float = Field(ge=0)
    maximum_consumption_kwh: float = Field(ge=0)
    minimum_consumption_kwh: float = Field(ge=0)
    units: Literal["kWh"] = "kWh"


class EnergyAggregatePoint(BaseModel):
    period_start: datetime
    consumption_kwh: float = Field(ge=0)
    observation_count: int = Field(ge=0)
    expected_observations: int = Field(ge=0)
    is_complete: bool


class EnergyAggregateResponse(Pagination):
    granularity: Literal["hourly", "daily", "monthly"]
    items: list[EnergyAggregatePoint]


class EnergyQuery(BaseModel):
    start: LocalDatetime | None = None
    end: LocalDatetime | None = None
