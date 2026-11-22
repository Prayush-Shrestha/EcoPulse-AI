"""Analytics response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.energy import EnergyAggregatePoint


class EnergyOverview(BaseModel):
    start_timestamp: datetime | None
    end_timestamp: datetime | None
    total_observations: int = Field(ge=0)
    total_consumption_kwh: float = Field(ge=0)
    average_consumption_kwh: float = Field(ge=0)
    peak_consumption_kwh: float = Field(ge=0)


class ForecastOverview(BaseModel):
    total_predictions: int = Field(ge=0)
    models: list[str]
    latest_forecast_timestamp: datetime | None
    latest_generated_at: datetime | None


class AnomalyOverview(BaseModel):
    total_observations: int = Field(ge=0)
    total_anomalies: int = Field(ge=0)
    anomaly_percentage: float = Field(ge=0, le=100)
    latest_detected_at: datetime | None


class AnalyticsOverviewResponse(BaseModel):
    energy: EnergyOverview
    forecast: ForecastOverview
    anomaly: AnomalyOverview
    hourly_trend: list[EnergyAggregatePoint]
    daily_trend: list[EnergyAggregatePoint]


class HourlyPatternPoint(BaseModel):
    hour: int = Field(ge=0, le=23)
    average_consumption_kwh: float = Field(ge=0)
    observation_count: int = Field(ge=0)


class WeekdayPatternPoint(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    day_name: str
    average_consumption_kwh: float = Field(ge=0)
    observation_count: int = Field(ge=0)


class MonthlyPatternPoint(BaseModel):
    month: int = Field(ge=1, le=12)
    month_name: str
    average_consumption_kwh: float = Field(ge=0)
    observation_count: int = Field(ge=0)


class ConsumptionPatternsResponse(BaseModel):
    hourly: list[HourlyPatternPoint]
    weekday: list[WeekdayPatternPoint]
    monthly: list[MonthlyPatternPoint]
