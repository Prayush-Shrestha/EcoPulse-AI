"""Validation helpers for Phase 4 data, splits, leakage and saved models.

The checks are deliberately independent of the training code: they re-derive
lag/rolling features from the target column, verify chronological boundaries,
and reload saved Joblib artefacts before comparing predictions with the stored
evaluation outputs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .metrics import regression_metrics

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

SPLITS = ("train", "validation", "test")


@dataclass(frozen=True)
class CheckResult:
    """One auditable validation check."""

    category: str
    name: str
    status: str
    detail: str


def make_check(
    category: str,
    name: str,
    passed: bool,
    detail: str,
    warning: bool = False,
) -> CheckResult:
    """Create a PASS/FAIL check, optionally downgrading a failure to a warning."""
    if passed:
        status = PASS
    elif warning:
        status = WARN
    else:
        status = FAIL
    return CheckResult(category=category, name=name, status=status, detail=detail)


def add_check(
    checks: list[CheckResult],
    category: str,
    name: str,
    passed: bool,
    detail: str,
    warning: bool = False,
) -> None:
    """Append one check to a list."""
    checks.append(make_check(category, name, passed, detail, warning=warning))


def summarize_checks(checks: Iterable[CheckResult]) -> dict[str, Any]:
    """Return passed/failed/warning counts and an overall status string."""
    check_list = list(checks)
    passed = sum(check.status == PASS for check in check_list)
    failed = sum(check.status == FAIL for check in check_list)
    warnings = sum(check.status == WARN for check in check_list)
    if failed:
        status = "FAILED"
    elif warnings:
        status = "PASSED WITH WARNINGS"
    else:
        status = "PASSED"
    return {
        "total": len(check_list),
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "status": status,
    }


def check_lines(
    checks: Iterable[CheckResult],
    include_passed: bool = True,
) -> list[str]:
    """Format checks as report lines with a fixed-width status column."""
    lines: list[str] = []
    for check in checks:
        if not include_passed and check.status == PASS:
            continue
        lines.append(
            f"[{check.status:<4}] {check.category:<14} {check.name}: {check.detail}"
        )
    return lines


def _read_parquet_schema(path: Path) -> tuple[list[str], int]:
    """Read column names and row count without loading the dataset."""
    parquet_file = pq.ParquetFile(path)
    return list(parquet_file.schema_arrow.names), int(parquet_file.metadata.num_rows)


def validate_phase3_inputs(
    processed_dir: Path,
    expected: dict[str, list[str]],
) -> list[CheckResult]:
    """Validate the four Phase 3 Parquet inputs using schema metadata.

    ``expected`` maps a filename to the columns Phase 4 requires.  Timestamp
    ordering, uniqueness and frequency are checked by reading the timestamp
    column only, which keeps the inspection local and memory-light.
    """
    checks: list[CheckResult] = []
    for filename, required_columns in expected.items():
        path = processed_dir / filename
        exists = path.is_file()
        add_check(
            checks,
            "INPUT",
            f"{filename} exists",
            exists,
            str(path) if exists else f"missing file: {path}",
        )
        if not exists:
            continue

        columns, rows = _read_parquet_schema(path)
        add_check(
            checks,
            "INPUT",
            f"{filename} rows",
            rows > 0,
            f"{rows:,} rows, {len(columns)} columns",
        )
        missing = [column for column in required_columns if column not in columns]
        add_check(
            checks,
            "INPUT",
            f"{filename} columns",
            not missing,
            "all required columns present"
            if not missing
            else "missing: " + ", ".join(missing),
        )

    timestamp_specs = {
        "household_power_cleaned.parquet": ("timestamp", "minute"),
        "household_power_hourly.parquet": ("period_start", "hour"),
        "household_power_daily.parquet": ("period_start", "day"),
        "household_power_monthly.parquet": ("period_start", "month"),
    }
    for filename, (timestamp_column, _frequency) in timestamp_specs.items():
        path = processed_dir / filename
        if not path.is_file():
            continue
        timestamps = pd.read_parquet(path, columns=[timestamp_column])[
            timestamp_column
        ]
        parsed = pd.to_datetime(timestamps)
        add_check(
            checks,
            "INPUT",
            f"{filename} timestamps",
            parsed.notna().all(),
            f"{int(parsed.isna().sum()):,} invalid timestamps",
        )
        add_check(
            checks,
            "INPUT",
            f"{filename} sorted",
            parsed.is_monotonic_increasing,
            "timestamps are chronological",
        )
        duplicates = int(parsed.duplicated().sum())
        add_check(
            checks,
            "INPUT",
            f"{filename} unique timestamps",
            duplicates == 0,
            f"{duplicates:,} duplicate timestamps",
        )

    hourly_path = processed_dir / "household_power_hourly.parquet"
    if hourly_path.is_file():
        hourly = pd.read_parquet(hourly_path, columns=["period_start"])
        diffs = hourly["period_start"].diff().dropna()
        one_hour = pd.Timedelta(hours=1)
        invalid_gaps = int((diffs != one_hour).sum())
        add_check(
            checks,
            "INPUT",
            "hourly grid is continuous",
            invalid_gaps == 0,
            f"{invalid_gaps:,} period gaps differ from one hour",
        )

    return checks


def validate_forecast_dataset(
    frame: pd.DataFrame,
    feature_names: list[str],
    timestamp_column: str = "timestamp",
    target_column: str = "target_energy_kwh",
) -> list[CheckResult]:
    """Validate the prepared hourly forecasting dataset and its lags."""
    checks: list[CheckResult] = []
    required = [
        timestamp_column,
        target_column,
        "split",
        "is_modeling_row",
        *feature_names,
    ]
    missing = [column for column in required if column not in frame.columns]
    add_check(
        checks,
        "FORECAST DATA",
        "required columns",
        not missing,
        "all required columns present"
        if not missing
        else "missing: " + ", ".join(missing),
    )
    if missing:
        return checks

    timestamps = frame[timestamp_column]
    add_check(
        checks,
        "FORECAST DATA",
        "timestamp dtype",
        pd.api.types.is_datetime64_any_dtype(timestamps),
        str(timestamps.dtype),
    )
    add_check(
        checks,
        "FORECAST DATA",
        "timestamps valid",
        timestamps.notna().all(),
        f"{int(timestamps.isna().sum()):,} invalid timestamps",
    )
    add_check(
        checks,
        "FORECAST DATA",
        "timestamps sorted",
        timestamps.is_monotonic_increasing,
        "chronological order",
    )
    add_check(
        checks,
        "FORECAST DATA",
        "timestamps unique",
        int(timestamps.duplicated().sum()) == 0,
        f"{int(timestamps.duplicated().sum()):,} duplicates",
    )
    one_hour = pd.Timedelta(hours=1)
    irregular = int((timestamps.diff().dropna() != one_hour).sum())
    add_check(
        checks,
        "FORECAST DATA",
        "hourly grid is continuous",
        irregular == 0,
        f"{irregular:,} irregular intervals",
    )

    modeling_mask = frame["is_modeling_row"].astype(bool)
    modeling_rows = int(modeling_mask.sum())
    add_check(
        checks,
        "FORECAST DATA",
        "modeling rows exist",
        modeling_rows > 0,
        f"{modeling_rows:,} supervised rows",
    )
    feature_nulls = int(frame.loc[modeling_mask, feature_names].isna().sum().sum())
    add_check(
        checks,
        "FORECAST DATA",
        "features complete on modeling rows",
        feature_nulls == 0,
        f"{feature_nulls:,} missing feature cells",
    )
    target_values = frame.loc[modeling_mask, target_column]
    target_nulls = int(target_values.isna().sum())
    target_nonpositive = int((target_values <= 0).sum())
    add_check(
        checks,
        "FORECAST DATA",
        "target is complete",
        target_nulls == 0,
        f"{target_nulls:,} missing target values",
    )
    add_check(
        checks,
        "FORECAST DATA",
        "target is positive",
        target_nonpositive == 0,
        f"{target_nonpositive:,} non-positive target values",
    )

    split_values = set(frame.loc[modeling_mask, "split"].dropna().unique())
    add_check(
        checks,
        "FORECAST DATA",
        "all splits present",
        split_values == set(SPLITS),
        "splits: " + ", ".join(sorted(split_values)),
    )
    non_modeling_split = int(frame.loc[~modeling_mask, "split"].notna().sum())
    add_check(
        checks,
        "FORECAST DATA",
        "non-modeling rows unassigned",
        non_modeling_split == 0,
        f"{non_modeling_split:,} warm-up rows carry a split label",
    )

    split_ranges = {}
    for split in SPLITS:
        part = frame.loc[frame["split"] == split]
        split_ranges[split] = (part[timestamp_column].min(), part[timestamp_column].max())
        add_check(
            checks,
            "FORECAST DATA",
            f"{split} split is non-empty",
            len(part) > 0,
            f"{len(part):,} rows from {part[timestamp_column].min()} to {part[timestamp_column].max()}",
        )

    if set(split_ranges) == set(SPLITS) and all(
        pd.notna(value[0]) for value in split_ranges.values()
    ):
        chronological = (
            split_ranges["train"][1] < split_ranges["validation"][0]
            and split_ranges["validation"][1] < split_ranges["test"][0]
        )
        add_check(
            checks,
            "SPLIT",
            "chronological boundaries",
            chronological,
            (
                f"train ends {split_ranges['train'][1]}, "
                f"validation starts {split_ranges['validation'][0]}, "
                f"test starts {split_ranges['test'][0]}"
            ),
        )

    first_modeling = timestamps.loc[modeling_mask].min()
    first_observed = timestamps.min()
    warmup_hours = (first_modeling - first_observed) / pd.Timedelta(hours=1)
    add_check(
        checks,
        "LEAKAGE",
        "feature warm-up excluded",
        warmup_hours >= 168,
        f"first modeling row is {warmup_hours:,.0f} hours after the first timestamp",
    )

    target = frame.set_index(timestamp_column)[target_column]
    lag_columns = sorted(
        (column for column in feature_names if column.startswith("lag_")),
        key=lambda column: int(column.split("_")[1]),
    )
    for column in lag_columns:
        lag = int(column.split("_")[1])
        expected = target.shift(lag).to_numpy()
        actual = frame[column].to_numpy()
        mask = modeling_mask.to_numpy()
        difference = np.nanmax(np.abs(expected[mask] - actual[mask]))
        add_check(
            checks,
            "LEAKAGE",
            f"{column} uses only past targets",
            bool(np.allclose(expected[mask], actual[mask], rtol=1e-9, atol=1e-9)),
            f"max absolute difference {difference:.3e}",
        )

    shifted = target.shift(1)
    rolling_windows = [3, 6, 24, 168]
    for window in rolling_windows:
        column = f"rolling_mean_{window}"
        expected = shifted.rolling(window, min_periods=window).mean().to_numpy()
        actual = frame[column].to_numpy()
        mask = modeling_mask.to_numpy()
        difference = np.nanmax(np.abs(expected[mask] - actual[mask]))
        add_check(
            checks,
            "LEAKAGE",
            f"{column} is causal",
            bool(np.allclose(expected[mask], actual[mask], rtol=1e-9, atol=1e-9)),
            f"max absolute difference {difference:.3e}",
        )

    column = "rolling_std_24"
    expected = shifted.rolling(24, min_periods=24).std(ddof=0).to_numpy()
    actual = frame[column].to_numpy()
    mask = modeling_mask.to_numpy()
    difference = np.nanmax(np.abs(expected[mask] - actual[mask]))
    add_check(
        checks,
        "LEAKAGE",
        f"{column} is causal",
        bool(np.allclose(expected[mask], actual[mask], rtol=1e-9, atol=1e-9)),
        f"max absolute difference {difference:.3e}",
    )

    return checks


def validate_anomaly_dataset(
    frame: pd.DataFrame,
    feature_names: list[str],
    timestamp_column: str = "timestamp",
) -> list[CheckResult]:
    """Validate the prepared minute-level anomaly dataset and causal z-scores."""
    checks: list[CheckResult] = []
    required = [timestamp_column, "split", *feature_names]
    missing = [column for column in required if column not in frame.columns]
    add_check(
        checks,
        "ANOMALY DATA",
        "required columns",
        not missing,
        "all required columns present"
        if not missing
        else "missing: " + ", ".join(missing),
    )
    if missing:
        return checks

    timestamps = frame[timestamp_column]
    add_check(
        checks,
        "ANOMALY DATA",
        "timestamp dtype",
        pd.api.types.is_datetime64_any_dtype(timestamps),
        str(timestamps.dtype),
    )
    add_check(
        checks,
        "ANOMALY DATA",
        "timestamps valid",
        timestamps.notna().all(),
        f"{int(timestamps.isna().sum()):,} invalid timestamps",
    )
    add_check(
        checks,
        "ANOMALY DATA",
        "timestamps sorted",
        timestamps.is_monotonic_increasing,
        "chronological order",
    )
    duplicates = int(timestamps.duplicated().sum())
    add_check(
        checks,
        "ANOMALY DATA",
        "timestamps unique",
        duplicates == 0,
        f"{duplicates:,} duplicate timestamps",
    )
    add_check(
        checks,
        "ANOMALY DATA",
        "rows available",
        len(frame) > 0,
        f"{len(frame):,} usable minutes",
    )

    feature_nulls = int(frame[feature_names].isna().sum().sum())
    add_check(
        checks,
        "ANOMALY DATA",
        "features complete",
        feature_nulls == 0,
        f"{feature_nulls:,} missing feature cells",
    )
    non_finite = int(
        np.count_nonzero(~np.isfinite(frame[feature_names].to_numpy(dtype=float)))
    )
    add_check(
        checks,
        "ANOMALY DATA",
        "features finite",
        non_finite == 0,
        f"{non_finite:,} non-finite feature cells",
    )

    split_values = set(frame["split"].dropna().unique())
    add_check(
        checks,
        "ANOMALY DATA",
        "all splits present",
        split_values == set(SPLITS),
        "splits: " + ", ".join(sorted(split_values)),
    )
    split_ranges = {}
    for split in SPLITS:
        part = frame.loc[frame["split"] == split]
        split_ranges[split] = (part[timestamp_column].min(), part[timestamp_column].max())
        add_check(
            checks,
            "ANOMALY DATA",
            f"{split} split is non-empty",
            len(part) > 0,
            f"{len(part):,} rows from {part[timestamp_column].min()} to {part[timestamp_column].max()}",
        )
    if all(pd.notna(value[0]) for value in split_ranges.values()):
        chronological = (
            split_ranges["train"][1] < split_ranges["validation"][0]
            and split_ranges["validation"][1] < split_ranges["test"][0]
        )
        add_check(
            checks,
            "SPLIT",
            "anomaly chronological boundaries",
            chronological,
            (
                f"train ends {split_ranges['train'][1]}, "
                f"validation starts {split_ranges['validation'][0]}, "
                f"test starts {split_ranges['test'][0]}"
            ),
        )

    if "gap_z_24h" in frame.columns and {
        "gap_mean_1440",
        "gap_std_1440",
    }.issubset(frame.columns):
        with np.errstate(divide="ignore", invalid="ignore"):
            expected = (
                frame["Global_active_power"] - frame["gap_mean_1440"]
            ) / frame["gap_std_1440"].replace(0.0, np.nan)
        difference = float(np.nanmax(np.abs(expected - frame["gap_z_24h"])))
        add_check(
            checks,
            "LEAKAGE",
            "z-score uses prior 24h statistics",
            bool(np.allclose(expected, frame["gap_z_24h"], rtol=1e-9, atol=1e-9)),
            f"max absolute difference {difference:.3e}",
        )

    add_check(
        checks,
        "ANOMALY DATA",
        "voltage is positive",
        bool((frame["Voltage"] > 0).all()),
        f"min voltage {frame['Voltage'].min():,.3f} V",
    )
    negative_power = int((frame[["Global_active_power", "Global_reactive_power"]] < 0).sum().sum())
    add_check(
        checks,
        "ANOMALY DATA",
        "power readings are non-negative",
        negative_power == 0,
        f"{negative_power:,} negative active/reactive readings",
    )

    return checks


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_forecasting_model_artifact(
    model_path: Path,
    metadata_path: Path,
    features_path: Path,
    predictions: pd.DataFrame,
    model_name: str,
    feature_names: list[str],
    test_split: str = "test",
    feature_frame: pd.DataFrame | None = None,
) -> list[CheckResult]:
    """Reload the saved forecasting bundle and reproduce its test predictions."""
    checks: list[CheckResult] = []
    add_check(
        checks,
        "MODEL ARTEFACT",
        "forecasting model exists",
        model_path.is_file(),
        f"{model_path.name} ({model_path.stat().st_size:,} bytes)"
        if model_path.is_file()
        else f"missing: {model_path}",
    )
    add_check(
        checks,
        "MODEL ARTEFACT",
        "forecasting metadata exists",
        metadata_path.is_file(),
        metadata_path.name,
    )
    add_check(
        checks,
        "MODEL ARTEFACT",
        "forecasting feature list exists",
        features_path.is_file(),
        features_path.name,
    )
    if not (model_path.is_file() and metadata_path.is_file() and features_path.is_file()):
        return checks

    bundle = joblib.load(model_path)
    metadata = _load_json(metadata_path)
    feature_document = _load_json(features_path)
    add_check(
        checks,
        "MODEL ARTEFACT",
        "bundle structure",
        isinstance(bundle, dict) and "model" in bundle,
        "bundle contains a fitted model"
        if isinstance(bundle, dict) and "model" in bundle
        else "unexpected bundle format",
    )
    if not (isinstance(bundle, dict) and "model" in bundle):
        return checks

    add_check(
        checks,
        "MODEL ARTEFACT",
        "metadata model name",
        metadata.get("model_name") == model_name,
        f"metadata: {metadata.get('model_name')}",
    )
    add_check(
        checks,
        "MODEL ARTEFACT",
        "feature list matches training",
        list(feature_document.get("features", [])) == list(feature_names)
        and list(bundle.get("feature_names", [])) == list(feature_names),
        f"{len(feature_names)} features",
    )

    model_predictions = predictions.loc[predictions["model"] == model_name].copy()
    test_predictions = model_predictions.loc[
        model_predictions["split"] == test_split
    ].sort_values("timestamp")
    add_check(
        checks,
        "MODEL ARTEFACT",
        "stored test predictions exist",
        not test_predictions.empty,
        f"{len(test_predictions):,} rows",
    )
    if test_predictions.empty:
        return checks

    if feature_frame is not None:
        missing_source = [
            column
            for column in ["timestamp", *feature_names]
            if column not in feature_frame.columns
        ]
        add_check(
            checks,
            "MODEL ARTEFACT",
            "feature source is available",
            not missing_source,
            "prepared dataset supplies the model features"
            if not missing_source
            else "missing: " + ", ".join(missing_source),
        )
        if missing_source:
            return checks
        test_predictions = test_predictions.merge(
            feature_frame[["timestamp", *feature_names]],
            on="timestamp",
            how="left",
            validate="one_to_one",
        )
        if test_predictions[feature_names].isna().any().any():
            add_check(
                checks,
                "MODEL ARTEFACT",
                "features join to test predictions",
                False,
                "some test timestamps did not receive model features",
            )
            return checks
        test_predictions = test_predictions.sort_values("timestamp")
    elif not set(feature_names).issubset(test_predictions.columns):
        add_check(
            checks,
            "MODEL ARTEFACT",
            "features available for reload check",
            False,
            "prediction table does not contain model features and no feature source was supplied",
        )
        return checks

    features = test_predictions[feature_names]
    reloaded = np.asarray(bundle["model"].predict(features), dtype=float)
    stored = test_predictions["predicted"].to_numpy(dtype=float)
    difference = float(np.max(np.abs(reloaded - stored)))
    add_check(
        checks,
        "MODEL ARTEFACT",
        "reloaded model reproduces test predictions",
        difference <= 1e-6,
        f"max absolute difference {difference:.3e}",
    )

    recomputed = regression_metrics(
        test_predictions["actual"].to_numpy(),
        stored,
    )
    stored_metrics = metadata.get("test_metrics", {})
    metric_differences = {}
    for key in ("mae", "rmse", "r2"):
        stored_value = stored_metrics.get(key)
        recomputed_value = recomputed.get(key)
        if stored_value is None or recomputed_value is None:
            metric_differences[key] = None
        else:
            metric_differences[key] = abs(float(stored_value) - float(recomputed_value))
    metrics_match = all(
        difference is None or difference <= 1e-6
        for difference in metric_differences.values()
    )
    add_check(
        checks,
        "MODEL ARTEFACT",
        "metadata test metrics match predictions",
        metrics_match,
        "MAX(MAE, RMSE, R2) difference "
        + f"{max((value or 0.0) for value in metric_differences.values()):.3e}",
    )
    return checks


def validate_anomaly_model_artifact(
    model_path: Path,
    scaler_path: Path,
    metadata_path: Path,
    features_path: Path,
    predictions: pd.DataFrame,
    feature_names: list[str],
    zscore_threshold: float,
    sample_size: int = 25_000,
    random_state: int = 42,
    feature_frame: pd.DataFrame | None = None,
) -> list[CheckResult]:
    """Reload the anomaly bundle and reproduce a sample of test flags."""
    checks: list[CheckResult] = []
    for label, path in (
        ("anomaly model", model_path),
        ("anomaly scaler", scaler_path),
        ("anomaly metadata", metadata_path),
        ("anomaly feature list", features_path),
    ):
        add_check(
            checks,
            "MODEL ARTEFACT",
            f"{label} exists",
            path.is_file(),
            f"{path.name} ({path.stat().st_size:,} bytes)"
            if path.is_file()
            else f"missing: {path}",
        )
    if not all(
        path.is_file()
        for path in (model_path, scaler_path, metadata_path, features_path)
    ):
        return checks

    bundle = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    metadata = _load_json(metadata_path)
    feature_document = _load_json(features_path)
    add_check(
        checks,
        "MODEL ARTEFACT",
        "anomaly bundle structure",
        isinstance(bundle, dict)
        and {"model", "scaler", "threshold"}.issubset(bundle),
        "bundle contains model, scaler and threshold"
        if isinstance(bundle, dict)
        else "unexpected bundle format",
    )
    if not isinstance(bundle, dict):
        return checks

    add_check(
        checks,
        "MODEL ARTEFACT",
        "anomaly feature list matches training",
        list(feature_document.get("features", [])) == list(feature_names)
        and list(bundle.get("feature_names", [])) == list(feature_names),
        f"{len(feature_names)} features",
    )
    threshold = float(bundle.get("threshold", np.nan))
    metadata_threshold = float(
        metadata.get("isolation_forest", {}).get(
            "iforest_offset", metadata.get("iforest_offset", np.nan)
        )
    )
    add_check(
        checks,
        "MODEL ARTEFACT",
        "threshold stored with model",
        np.isfinite(threshold)
        and np.isfinite(metadata_threshold)
        and abs(threshold - metadata_threshold) <= 1e-9,
        f"offset {threshold:.6f}",
    )

    test_rows = (
        predictions.loc[
            predictions["split"] == "test",
            [
                "timestamp",
                "isolation_forest_anomaly",
                "zscore_anomaly",
                "gap_z_24h",
            ],
        ]
        .rename(columns={"gap_z_24h": "stored_gap_z_24h"})
        .reset_index(drop=True)
    )

    if feature_frame is not None:
        source_columns = list(dict.fromkeys(["timestamp", *feature_names]))
        missing_source = [
            column for column in source_columns if column not in feature_frame.columns
        ]
        add_check(
            checks,
            "MODEL ARTEFACT",
            "anomaly feature source is available",
            not missing_source,
            "prepared dataset supplies the model features"
            if not missing_source
            else "missing: " + ", ".join(missing_source),
        )
        if missing_source:
            return checks
        test_rows = test_rows.merge(
            feature_frame[source_columns],
            on="timestamp",
            how="left",
            validate="one_to_one",
        )
        missing_features = int(test_rows[feature_names].isna().any(axis=1).sum())
        add_check(
            checks,
            "MODEL ARTEFACT",
            "features join to anomaly test rows",
            missing_features == 0,
            f"{missing_features:,} rows without model features",
        )
        if missing_features:
            return checks
    else:
        required = ["stored_gap_z_24h", *feature_names]
        missing_prediction_features = [
            column for column in required if column not in test_rows.columns
        ]
        if missing_prediction_features:
            add_check(
                checks,
                "MODEL ARTEFACT",
                "features available for anomaly reload check",
                False,
                "prediction table lacks model features and no feature source was supplied",
            )
            return checks

    if len(test_rows) > sample_size:
        rng = np.random.default_rng(random_state)
        positions = np.sort(rng.choice(len(test_rows), size=sample_size, replace=False))
        test_rows = test_rows.iloc[positions].reset_index(drop=True)
    add_check(
        checks,
        "MODEL ARTEFACT",
        "anomaly evaluation sample",
        not test_rows.empty,
        f"{len(test_rows):,} test rows",
    )
    if test_rows.empty:
        return checks

    scaled = scaler.transform(test_rows[feature_names].to_numpy(dtype=np.float64))
    reloaded_flags = bundle["model"].predict(scaled) == -1
    stored_flags = test_rows["isolation_forest_anomaly"].astype(bool).to_numpy()
    mismatches = int(np.count_nonzero(reloaded_flags != stored_flags))
    add_check(
        checks,
        "MODEL ARTEFACT",
        "reloaded Isolation Forest reproduces flags",
        mismatches == 0,
        f"{mismatches:,} mismatches in {len(test_rows):,} rows",
    )

    recomputed_z = (
        np.abs(test_rows["stored_gap_z_24h"].to_numpy(dtype=float))
        >= zscore_threshold
    )
    stored_z = test_rows["zscore_anomaly"].astype(bool).to_numpy()
    z_mismatches = int(np.count_nonzero(recomputed_z != stored_z))
    add_check(
        checks,
        "MODEL ARTEFACT",
        "z-score threshold reproduces flags",
        z_mismatches == 0,
        f"{z_mismatches:,} mismatches in {len(test_rows):,} rows",
    )
    return checks
