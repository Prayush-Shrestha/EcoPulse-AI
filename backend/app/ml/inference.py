"""Causal inference features matching the saved Phase 4 training definitions."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.core.errors import InsufficientHistoryError, PredictionError

FORECAST_LAGS = (1, 2, 3, 24, 48, 168)
FORECAST_ROLLING_WINDOWS = (3, 6, 24, 168)
ANOMALY_MEASUREMENT_COLUMNS = (
    "Global_active_power",
    "Global_reactive_power",
    "Voltage",
    "Global_intensity",
    "Sub_metering_1",
    "Sub_metering_2",
    "Sub_metering_3",
)
ANOMALY_HISTORY_COLUMNS = (
    "gap_lag_1",
    "gap_mean_60",
    "gap_std_60",
    "gap_mean_1440",
    "gap_std_1440",
    "gap_z_24h",
)


def time_features(timestamp: datetime | pd.Timestamp) -> dict[str, float | int | bool]:
    """Return the calendar and cyclical features used by both models."""

    value = pd.Timestamp(timestamp)
    hour = int(value.hour)
    day_of_week = int(value.weekday())
    day_of_month = int(value.day)
    day_of_year = int(value.dayofyear)
    week_of_year = int(value.isocalendar().week)
    month = int(value.month)
    is_weekend = day_of_week >= 5

    return {
        "hour": hour,
        "day_of_week": day_of_week,
        "day_of_month": day_of_month,
        "day_of_year": day_of_year,
        "week_of_year": week_of_year,
        "month": month,
        "is_weekend": is_weekend,
        "hour_sin": float(np.sin(2.0 * np.pi * hour / 24.0)),
        "hour_cos": float(np.cos(2.0 * np.pi * hour / 24.0)),
        "dow_sin": float(np.sin(2.0 * np.pi * day_of_week / 7.0)),
        "dow_cos": float(np.cos(2.0 * np.pi * day_of_week / 7.0)),
        "month_sin": float(np.sin(2.0 * np.pi * (month - 1) / 12.0)),
        "month_cos": float(np.cos(2.0 * np.pi * (month - 1) / 12.0)),
    }


def _validate_finite(frame: pd.DataFrame, context: str) -> None:
    try:
        array = frame.to_numpy(dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise PredictionError(f"{context} contains non-numeric values.") from exc
    if not np.isfinite(array).all():
        raise InsufficientHistoryError(
            f"{context} is incomplete; the model cannot be evaluated safely."
        )


def build_forecast_features(
    history: pd.Series,
    target_timestamp: datetime | pd.Timestamp,
    feature_names: list[str],
) -> pd.DataFrame:
    """Build one forecast row from an hourly target history.

    ``history`` must be indexed by timestamp and contain only observed or
    previously predicted target values. Values at or after ``target_timestamp``
    are never used.
    """

    target = pd.Timestamp(target_timestamp)
    if history.index.has_duplicates:
        raise PredictionError("Forecast history contains duplicate timestamps.")
    ordered = history.sort_index()
    prior = ordered.loc[ordered.index < target]
    if prior.empty:
        raise InsufficientHistoryError("No hourly history exists before the forecast.")

    expected_last = target - timedelta(hours=1)
    if prior.index[-1] != expected_last:
        raise InsufficientHistoryError(
            "The hour immediately before the forecast is missing; "
            "the model cannot build causal lag features."
        )

    needed = [target - timedelta(hours=lag) for lag in FORECAST_LAGS]
    missing = [stamp for stamp in needed if stamp not in prior.index]
    if missing:
        raise InsufficientHistoryError(
            "Missing lag history for "
            + ", ".join(stamp.isoformat() for stamp in missing[:3])
        )

    lag_values = {stamp: prior.loc[stamp] for stamp in needed}
    if any(pd.isna(value) for value in lag_values.values()):
        raise InsufficientHistoryError(
            "Lag history contains incomplete hours; the model cannot be evaluated."
        )

    if len(prior) < max(FORECAST_ROLLING_WINDOWS):
        raise InsufficientHistoryError(
            f"At least {max(FORECAST_ROLLING_WINDOWS)} prior hours are required."
        )
    recent = prior.iloc[-max(FORECAST_ROLLING_WINDOWS) :]
    if recent.isna().any():
        raise InsufficientHistoryError(
            "The rolling feature window contains incomplete hours."
        )

    values = recent.to_numpy(dtype=np.float64)
    row: dict[str, float | int | bool] = dict(time_features(target))
    for lag in FORECAST_LAGS:
        row[f"lag_{lag}"] = float(lag_values[target - timedelta(hours=lag)])

    for window in FORECAST_ROLLING_WINDOWS:
        row[f"rolling_mean_{window}"] = float(values[-window:].mean())
    row["rolling_std_24"] = float(values[-24:].std(ddof=0))

    missing_features = [name for name in feature_names if name not in row]
    if missing_features:
        raise PredictionError(
            "Saved forecast features are not reproducible: "
            + ", ".join(missing_features)
        )

    frame = pd.DataFrame([{name: row[name] for name in feature_names}], columns=feature_names)
    _validate_finite(frame, "Forecast feature row")
    return frame


def build_anomaly_history_features(
    history: pd.DataFrame,
    timestamp: datetime | pd.Timestamp,
) -> dict[str, float]:
    """Build shifted 1-hour and 24-hour statistics from prior observations."""

    target = pd.Timestamp(timestamp)
    required = ("timestamp", "Global_active_power")
    if not all(column in history.columns for column in required):
        raise PredictionError("Anomaly history is missing required measurement columns.")

    frame = history.loc[history["timestamp"] < target, list(required)].copy()
    if frame["timestamp"].duplicated().any():
        raise PredictionError("Anomaly history contains duplicate timestamps.")

    frame = pd.concat(
        [
            frame,
            pd.DataFrame(
                {
                    "timestamp": [target],
                    "Global_active_power": [np.nan],
                }
            ),
        ],
        ignore_index=True,
    )
    frame = frame.sort_values("timestamp").set_index("timestamp")
    previous = frame["Global_active_power"].shift(1)

    mean_60 = previous.rolling("60min", min_periods=30).mean()
    std_60 = previous.rolling("60min", min_periods=30).std(ddof=0)
    mean_1440 = previous.rolling("24h", min_periods=720).mean()
    std_1440 = previous.rolling("24h", min_periods=720).std(ddof=0)

    if target not in previous.index:
        raise PredictionError("Anomaly history could not be aligned to the timestamp.")

    result = {
        "gap_lag_1": float(previous.loc[target]),
        "gap_mean_60": float(mean_60.loc[target]),
        "gap_std_60": float(std_60.loc[target]),
        "gap_mean_1440": float(mean_1440.loc[target]),
        "gap_std_1440": float(std_1440.loc[target]),
    }
    if not np.isfinite(list(result.values())).all() or result["gap_std_1440"] <= 0:
        raise InsufficientHistoryError(
            "A full prior 24-hour baseline is required before anomaly scoring."
        )
    return result


def build_anomaly_features(
    history: pd.DataFrame,
    timestamp: datetime | pd.Timestamp,
    measurements: dict[str, float],
    feature_names: list[str],
) -> pd.DataFrame:
    """Build one anomaly row from current readings and causal history."""

    missing_measurements = [
        name for name in ANOMALY_MEASUREMENT_COLUMNS if name not in measurements
    ]
    if missing_measurements:
        raise PredictionError(
            "Current measurements are missing: " + ", ".join(missing_measurements)
        )

    history_features = build_anomaly_history_features(history, timestamp)
    row: dict[str, float | int | bool] = {
        **{name: float(measurements[name]) for name in ANOMALY_MEASUREMENT_COLUMNS},
        **time_features(timestamp),
        **history_features,
    }
    row["gap_z_24h"] = float(
        (row["Global_active_power"] - row["gap_mean_1440"]) / row["gap_std_1440"]
    )

    missing_features = [name for name in feature_names if name not in row]
    if missing_features:
        raise PredictionError(
            "Saved anomaly features are not reproducible: " + ", ".join(missing_features)
        )

    frame = pd.DataFrame([{name: row[name] for name in feature_names}], columns=feature_names)
    _validate_finite(frame, "Anomaly feature row")
    return frame
