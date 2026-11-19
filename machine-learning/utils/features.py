"""Shared feature engineering for Phase 4 forecasting and anomaly detection.

Every lag and rolling statistic in this module is computed from values that are
strictly earlier than the row being described.  The functions never shuffle or
reorder time-series observations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TIMESTAMP_COLUMN = "timestamp"
TARGET_COLUMN = "target_energy_kwh"

TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
TEST_FRACTION = 0.15

LAG_FEATURES = ["lag_1", "lag_2", "lag_3", "lag_24", "lag_48", "lag_168"]
ROLLING_FEATURES = [
    "rolling_mean_3",
    "rolling_mean_6",
    "rolling_mean_24",
    "rolling_mean_168",
    "rolling_std_24",
]
CYCLICAL_FEATURES = [
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "month_sin",
    "month_cos",
]
TIME_FEATURES = [
    "hour",
    "day_of_week",
    "day_of_month",
    "day_of_year",
    "week_of_year",
    "month",
    "is_weekend",
    *CYCLICAL_FEATURES,
]
FORECAST_FEATURES = [*TIME_FEATURES, *LAG_FEATURES, *ROLLING_FEATURES]

ANOMALY_MEASUREMENT_FEATURES = [
    "Global_active_power",
    "Global_reactive_power",
    "Voltage",
    "Global_intensity",
    "Sub_metering_1",
    "Sub_metering_2",
    "Sub_metering_3",
]
ANOMALY_TIME_FEATURES = [
    "hour",
    "day_of_week",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]
ANOMALY_HISTORY_FEATURES = [
    "gap_lag_1",
    "gap_mean_60",
    "gap_std_60",
    "gap_mean_1440",
    "gap_std_1440",
    "gap_z_24h",
]
ANOMALY_FEATURES = [
    *ANOMALY_MEASUREMENT_FEATURES,
    *ANOMALY_TIME_FEATURES,
    *ANOMALY_HISTORY_FEATURES,
]


class LagBaseline:
    """A deterministic lag baseline that can be saved with Joblib.

    The class intentionally mirrors a minimal scikit-learn estimator so the
    saved Phase 4 artefact can be loaded and asked for predictions.
    """

    def __init__(self, lag: int) -> None:
        self.lag = int(lag)

    def predict(self, features: pd.DataFrame | np.ndarray) -> np.ndarray:
        column = f"lag_{self.lag}"
        if isinstance(features, pd.DataFrame):
            return features[column].to_numpy(dtype=np.float64)
        return np.asarray(features, dtype=np.float64)[
            :, FORECAST_FEATURES.index(column)
        ]

    def get_params(self, deep: bool = True) -> dict[str, int]:
        return {"lag": self.lag}


def _week_of_year(timestamp: pd.Series) -> pd.Series:
    """Return ISO week numbers as int16 without pandas nullable noise."""
    return timestamp.dt.isocalendar().week.astype("int16")


def add_time_features(
    dataframe: pd.DataFrame,
    timestamp_column: str = TIMESTAMP_COLUMN,
) -> pd.DataFrame:
    """Add calendar and cyclical features from a validated timestamp column."""
    result = dataframe.copy()
    timestamp = result[timestamp_column]
    if not pd.api.types.is_datetime64_any_dtype(timestamp):
        raise TypeError(f"{timestamp_column} must be datetime64 before feature creation.")
    if timestamp.isna().any():
        raise ValueError(f"{timestamp_column} contains invalid timestamps.")

    result["hour"] = timestamp.dt.hour.astype("int8")
    result["day_of_week"] = timestamp.dt.dayofweek.astype("int8")
    result["day"] = timestamp.dt.day.astype("int8")
    result["day_of_month"] = result["day"]
    result["day_of_year"] = timestamp.dt.dayofyear.astype("int16")
    result["week_of_year"] = _week_of_year(timestamp)
    result["month"] = timestamp.dt.month.astype("int8")
    result["is_weekend"] = result["day_of_week"] >= 5

    result["hour_sin"] = np.sin(2.0 * np.pi * result["hour"] / 24.0)
    result["hour_cos"] = np.cos(2.0 * np.pi * result["hour"] / 24.0)
    result["dow_sin"] = np.sin(2.0 * np.pi * result["day_of_week"] / 7.0)
    result["dow_cos"] = np.cos(2.0 * np.pi * result["day_of_week"] / 7.0)
    result["month_sin"] = np.sin(2.0 * np.pi * (result["month"] - 1) / 12.0)
    result["month_cos"] = np.cos(2.0 * np.pi * (result["month"] - 1) / 12.0)
    return result


def _assign_chronological_split(
    dataframe: pd.DataFrame,
    row_mask: pd.Series,
    timestamp_column: str,
) -> pd.DataFrame:
    """Assign train/validation/test labels by chronological row position."""
    result = dataframe.copy()
    result["split"] = pd.Series(pd.NA, index=result.index, dtype="string")

    positions = np.flatnonzero(row_mask.to_numpy())
    total = len(positions)
    if total < 3:
        raise ValueError("At least three usable chronological rows are required.")
    train_end = int(total * TRAIN_FRACTION)
    validation_end = train_end + int(total * VALIDATION_FRACTION)
    if train_end == 0 or validation_end == train_end or validation_end >= total:
        raise ValueError("The requested split leaves an empty train/validation/test set.")

    result.loc[result.index[positions[:train_end]], "split"] = "train"
    result.loc[
        result.index[positions[train_end:validation_end]], "split"
    ] = "validation"
    result.loc[result.index[positions[validation_end:]], "split"] = "test"

    ordered = result.loc[result["split"].notna()].sort_values(timestamp_column)
    labels = ordered["split"].to_numpy()
    if not (
        np.all(labels[:train_end] == "train")
        and np.all(labels[train_end:validation_end] == "validation")
        and np.all(labels[validation_end:] == "test")
    ):
        raise RuntimeError("Chronological split labels are not ordered in time.")
    return result


def build_forecasting_dataset(hourly: pd.DataFrame) -> pd.DataFrame:
    """Build the supervised hourly forecasting table and chronological split.

    The target is a complete clock-hour energy total.  Incomplete hours and the
    two partial boundary hours are marked missing rather than treated as zero.
    """
    required = [
        "period_start",
        "expected_observation_count",
        "valid_observation_count",
        "is_complete",
        "total_energy_consumption_kwh",
    ]
    missing = [column for column in required if column not in hourly.columns]
    if missing:
        raise ValueError("Hourly dataset is missing columns: " + ", ".join(missing))

    frame = hourly.copy()
    frame[TIMESTAMP_COLUMN] = pd.to_datetime(frame["period_start"])
    frame = frame.sort_values(TIMESTAMP_COLUMN, kind="mergesort").reset_index(drop=True)
    if frame[TIMESTAMP_COLUMN].duplicated().any():
        raise ValueError("Hourly dataset contains duplicate period_start values.")

    start = frame[TIMESTAMP_COLUMN].min().floor("h")
    end = frame[TIMESTAMP_COLUMN].max().floor("h")
    grid = pd.DataFrame({TIMESTAMP_COLUMN: pd.date_range(start, end, freq="h")})
    frame = grid.merge(frame, on=TIMESTAMP_COLUMN, how="left")

    expected = frame["expected_observation_count"].fillna(0).astype("int64")
    valid = frame["valid_observation_count"].fillna(0).astype("int64")
    complete = frame["is_complete"].fillna(False).astype(bool)
    target_mask = complete & (expected == 60) & (valid == expected)
    frame["expected_observation_count"] = expected
    frame["valid_observation_count"] = valid
    frame["is_complete"] = complete
    frame["target_energy_kwh"] = frame["total_energy_consumption_kwh"].where(target_mask)

    frame = add_time_features(frame)

    target = frame.set_index(TIMESTAMP_COLUMN)[TARGET_COLUMN]
    for lag in (1, 2, 3, 24, 48, 168):
        frame[f"lag_{lag}"] = target.shift(lag).to_numpy()
    shifted = target.shift(1)
    for window in (3, 6, 24, 168):
        frame[f"rolling_mean_{window}"] = (
            shifted.rolling(window, min_periods=window).mean().to_numpy()
        )
    frame["rolling_std_24"] = (
        shifted.rolling(24, min_periods=24).std(ddof=0).to_numpy()
    )

    feature_missing = frame[FORECAST_FEATURES].isna().any(axis=1)
    frame["is_modeling_row"] = frame[TARGET_COLUMN].notna() & ~feature_missing
    frame = _assign_chronological_split(
        frame,
        frame["is_modeling_row"],
        TIMESTAMP_COLUMN,
    )

    ordered = [
        TIMESTAMP_COLUMN,
        TARGET_COLUMN,
        *FORECAST_FEATURES,
        "split",
        "is_modeling_row",
        "is_complete",
        "expected_observation_count",
        "valid_observation_count",
        "total_energy_consumption_kwh",
    ]
    return frame[ordered].sort_values(TIMESTAMP_COLUMN).reset_index(drop=True)


def build_anomaly_dataset(minute: pd.DataFrame) -> pd.DataFrame:
    """Build causal minute-level features for unsupervised anomaly detection.

    Interpolated rows are excluded from anomaly modelling.  Rolling statistics
    are shifted by one minute, so the current reading is never part of its own
    baseline.
    """
    required = [
        TIMESTAMP_COLUMN,
        *ANOMALY_MEASUREMENT_FEATURES,
        "is_imputed",
    ]
    missing = [column for column in required if column not in minute.columns]
    if missing:
        raise ValueError("Minute dataset is missing columns: " + ", ".join(missing))

    frame = minute.loc[~minute["is_imputed"], required].copy()
    frame = frame.sort_values(TIMESTAMP_COLUMN, kind="mergesort").reset_index(drop=True)
    if frame[TIMESTAMP_COLUMN].duplicated().any():
        raise ValueError("Minute dataset contains duplicate timestamps.")
    frame = add_time_features(frame)

    indexed = frame.set_index(TIMESTAMP_COLUMN)
    previous = indexed["Global_active_power"].shift(1)

    mean_60 = previous.rolling("60min", min_periods=30).mean()
    std_60 = previous.rolling("60min", min_periods=30).std(ddof=0)
    mean_1440 = previous.rolling("24h", min_periods=720).mean()
    std_1440 = previous.rolling("24h", min_periods=720).std(ddof=0)

    frame["gap_lag_1"] = previous.to_numpy()
    frame["gap_mean_60"] = mean_60.to_numpy()
    frame["gap_std_60"] = std_60.to_numpy()
    frame["gap_mean_1440"] = mean_1440.to_numpy()
    frame["gap_std_1440"] = std_1440.to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        z_score = (frame["Global_active_power"] - frame["gap_mean_1440"]) / frame[
            "gap_std_1440"
        ].replace(0.0, np.nan)
    frame["gap_z_24h"] = z_score

    usable = frame[ANOMALY_FEATURES].notna().all(axis=1)
    frame = frame.loc[usable].reset_index(drop=True)
    frame = _assign_chronological_split(
        frame,
        pd.Series(True, index=frame.index),
        TIMESTAMP_COLUMN,
    )

    ordered = [TIMESTAMP_COLUMN, *ANOMALY_FEATURES, "split"]
    return frame[ordered].sort_values(TIMESTAMP_COLUMN).reset_index(drop=True)


def split_summary(dataframe: pd.DataFrame, timestamp_column: str = TIMESTAMP_COLUMN) -> list[dict]:
    """Return row counts and date ranges for the three chronological splits."""
    rows: list[dict] = []
    for split in ("train", "validation", "test"):
        part = dataframe.loc[dataframe["split"] == split]
        rows.append(
            {
                "split": split,
                "rows": int(len(part)),
                "start": part[timestamp_column].min(),
                "end": part[timestamp_column].max(),
            }
        )
    return rows
