"""Application-level analytics composed from real stored records."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.energy_repository import EnergyRepository
from app.repositories.forecast_repository import ForecastRepository
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    AnomalyOverview,
    ConsumptionPatternsResponse,
    EnergyOverview,
    ForecastOverview,
    HourlyPatternPoint,
    MonthlyPatternPoint,
    WeekdayPatternPoint,
)
from app.schemas.energy import EnergyAggregatePoint
from app.services.energy_service import _expected_observations

DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.energy_repository = EnergyRepository(db)
        self.forecast_repository = ForecastRepository(db)
        self.anomaly_repository = AnomalyRepository(db)

    def overview(self) -> AnalyticsOverviewResponse:
        summary = self.energy_repository.summary(start=None, end=None)
        hourly_rows, _ = self.energy_repository.aggregate(
            granularity="hour",
            start=None,
            end=None,
            limit=48,
            offset=0,
            descending=True,
        )
        daily_rows, _ = self.energy_repository.aggregate(
            granularity="day",
            start=None,
            end=None,
            limit=30,
            offset=0,
            descending=True,
        )

        def build_points(rows: list[tuple], granularity: str) -> list[EnergyAggregatePoint]:
            points = []
            for period_start, consumption, count in reversed(rows):
                expected = _expected_observations(granularity, period_start)
                points.append(
                    EnergyAggregatePoint(
                        period_start=period_start,
                        consumption_kwh=consumption,
                        observation_count=count,
                        expected_observations=expected,
                        is_complete=count == expected,
                    )
                )
            return points

        forecast = self.forecast_repository.overview()
        anomaly = self.anomaly_repository.overview()

        return AnalyticsOverviewResponse(
            energy=EnergyOverview(
                start_timestamp=summary["start_timestamp"],
                end_timestamp=summary["end_timestamp"],
                total_observations=summary["total_observations"],
                total_consumption_kwh=summary["total_consumption_kwh"],
                average_consumption_kwh=summary["average_consumption_kwh"],
                peak_consumption_kwh=summary["maximum_consumption_kwh"],
            ),
            forecast=ForecastOverview(**forecast),
            anomaly=AnomalyOverview(**anomaly),
            hourly_trend=build_points(hourly_rows, "hour"),
            daily_trend=build_points(daily_rows, "day"),
        )

    def consumption_patterns(self) -> ConsumptionPatternsResponse:
        return ConsumptionPatternsResponse(
            hourly=[
                HourlyPatternPoint(
                    hour=hour,
                    average_consumption_kwh=average,
                    observation_count=count,
                )
                for hour, average, count in self.energy_repository.hourly_pattern()
            ],
            weekday=[
                WeekdayPatternPoint(
                    day_of_week=day,
                    day_name=DAY_NAMES[day],
                    average_consumption_kwh=average,
                    observation_count=count,
                )
                for day, average, count in self.energy_repository.weekday_pattern()
            ],
            monthly=[
                MonthlyPatternPoint(
                    month=month,
                    month_name=MONTH_NAMES[month - 1],
                    average_consumption_kwh=average,
                    observation_count=count,
                )
                for month, average, count in self.energy_repository.monthly_pattern()
            ],
        )
