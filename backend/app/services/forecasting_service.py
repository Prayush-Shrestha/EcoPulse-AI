"""Forecasting service built on the persisted Phase 4 Random Forest."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.core.errors import (
    InsufficientHistoryError,
    NotFoundError,
    PredictionError,
    RequestValidationError,
)
from app.ml.inference import build_forecast_features
from app.ml.model_loader import ModelRegistry, get_model_registry
from app.models.forecast import ForecastRecord
from app.repositories.energy_repository import EnergyRepository
from app.repositories.forecast_repository import ForecastRepository
from app.schemas.forecast import (
    SUPPORTED_HORIZONS,
    ForecastHistoryResponse,
    ForecastPoint,
    ForecastRecordResponse,
    ForecastRequest,
    ForecastResponse,
)
from app.services.common import validate_time_range

HISTORY_HOURS = 200


class ForecastingService:
    def __init__(
        self,
        db: Session,
        registry: ModelRegistry | None = None,
    ) -> None:
        self.db = db
        self.energy_repository = EnergyRepository(db)
        self.forecast_repository = ForecastRepository(db)
        self.registry = registry or get_model_registry()

    def predict(self, request: ForecastRequest) -> ForecastResponse:
        artifact = self.registry.require_forecast()

        if request.base_timestamp is None:
            base_timestamp = self.energy_repository.latest_complete_hour()
            if base_timestamp is None:
                raise InsufficientHistoryError(
                    "No complete clock-hour is available in PostgreSQL."
                )
        else:
            base_timestamp = request.base_timestamp
            count = self.energy_repository.hour_observation_count(base_timestamp)
            if count != 60:
                raise RequestValidationError(
                    "base_timestamp must identify a complete clock-hour with exactly "
                    "60 stored minute observations.",
                    details={"observation_count": count, "expected": 60},
                )

        base = pd.Timestamp(base_timestamp).floor("h")
        rows = self.energy_repository.hourly_history(end_hour=base.to_pydatetime())
        if not rows:
            raise InsufficientHistoryError("No complete hourly history is available.")

        history = pd.Series(
            [value for _, value in rows],
            index=pd.DatetimeIndex([stamp for stamp, _ in rows]),
            dtype="float64",
        ).sort_index()
        if pd.Timestamp(base) not in history.index or pd.isna(history.loc[pd.Timestamp(base)]):
            raise InsufficientHistoryError(
                "The base hour is not available as a complete hourly target."
            )

        # Preserve missing hours as NaN so the inference layer can reject gaps
        # instead of silently treating them as zero consumption.
        full_index = pd.date_range(history.index.min(), history.index.max(), freq="h")
        history = history.reindex(full_index)
        if history.tail(1).isna().any():
            raise InsufficientHistoryError("The latest hourly target is incomplete.")

        generated_at = datetime.now(UTC)
        predictions: list[tuple[pd.Timestamp, float]] = []
        for step in range(1, request.horizon_hours + 1):
            target = pd.Timestamp(base + timedelta(hours=step))
            features = build_forecast_features(history, target, artifact.feature_names)
            value = float(artifact.predict(features)[0])
            if not pd.notna(value) or value < 0:
                raise PredictionError("The forecasting model returned an invalid value.")
            predictions.append((target, value))
            history.loc[target] = value

        records = [
            ForecastRecord(
                forecast_timestamp=target.to_pydatetime(),
                predicted_energy_kwh=value,
                model_name=artifact.name,
                model_version=artifact.version,
                forecast_horizon=request.horizon_hours,
            )
            for target, value in predictions
        ]
        self.forecast_repository.add_all(records)
        self.db.commit()

        return ForecastResponse(
            generated_at=generated_at,
            base_timestamp=base.to_pydatetime(),
            horizon_hours=request.horizon_hours,
            model_name=artifact.name,
            model_version=artifact.version,
            items=[
                ForecastPoint(
                    forecast_timestamp=target.to_pydatetime(),
                    predicted_energy_kwh=value,
                    model_name=artifact.name,
                    model_version=artifact.version,
                    forecast_horizon=request.horizon_hours,
                )
                for target, value in predictions
            ],
        )

    def history(
        self,
        *,
        model_name: str | None,
        forecast_horizon: int | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
    ) -> ForecastHistoryResponse:
        validate_time_range(start, end)
        if forecast_horizon is not None and forecast_horizon not in SUPPORTED_HORIZONS:
            raise RequestValidationError(
                "forecast_horizon must be one of 1, 6, 24 or 48.",
                details={"supported_horizons": list(SUPPORTED_HORIZONS)},
            )
        rows, total = self.forecast_repository.list_history(
            model_name=model_name,
            forecast_horizon=forecast_horizon,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
        return ForecastHistoryResponse(
            items=[ForecastRecordResponse.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def latest(self) -> ForecastRecordResponse:
        record = self.forecast_repository.latest()
        if record is None:
            raise NotFoundError("No forecast has been generated yet.")
        return ForecastRecordResponse.model_validate(record)
