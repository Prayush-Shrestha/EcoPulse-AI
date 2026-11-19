"""Prepare leakage-safe Phase 4 modelling datasets from Phase 3 Parquet files.

The hourly Phase 3 aggregate is the forecasting source.  Only complete clock
hours become supervised targets; lags and rolling features are shifted so no
current or future value can enter its own features.  The cleaned minute dataset
is the anomaly-detection source, excluding interpolated rows and requiring a
full prior 24-hour history for the rolling baseline.
"""

from __future__ import annotations

import gc
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACHINE_LEARNING_DIR = PROJECT_ROOT / "machine-learning"
DATA_DIR = PROJECT_ROOT / "data" / "processed"
ML_DATA_DIR = DATA_DIR / "ml"

if str(MACHINE_LEARNING_DIR) not in sys.path:
    sys.path.insert(0, str(MACHINE_LEARNING_DIR))

from utils.features import (  # noqa: E402
    ANOMALY_FEATURES,
    FORECAST_FEATURES,
    TARGET_COLUMN,
    build_anomaly_dataset,
    build_forecasting_dataset,
    split_summary,
)
from utils.validation import (  # noqa: E402
    FAIL,
    add_check,
    check_lines,
    summarize_checks,
    validate_anomaly_dataset,
    validate_forecast_dataset,
    validate_phase3_inputs,
)

PROJECT_NAME = "EcoPulse AI"
FORECAST_DATASET_PATH = ML_DATA_DIR / "forecasting_dataset.parquet"
ANOMALY_DATASET_PATH = ML_DATA_DIR / "anomaly_dataset.parquet"
PREPARATION_SUMMARY_PATH = ML_DATA_DIR / "preparation_summary.json"

EXPECTED_INPUTS = {
    "household_power_cleaned.parquet": [
        "timestamp",
        "Global_active_power",
        "Global_reactive_power",
        "Voltage",
        "Global_intensity",
        "Sub_metering_1",
        "Sub_metering_2",
        "Sub_metering_3",
        "energy_consumption_kwh",
        "is_imputed",
    ],
    "household_power_hourly.parquet": [
        "period_start",
        "expected_observation_count",
        "valid_observation_count",
        "is_complete",
        "total_energy_consumption_kwh",
    ],
    "household_power_daily.parquet": [
        "period_start",
        "total_energy_consumption_kwh",
    ],
    "household_power_monthly.parquet": [
        "period_start",
        "total_energy_consumption_kwh",
    ],
}


def sha256sum(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the four Phase 3 datasets from Parquet."""
    cleaned = pd.read_parquet(DATA_DIR / "household_power_cleaned.parquet")
    hourly = pd.read_parquet(DATA_DIR / "household_power_hourly.parquet")
    daily = pd.read_parquet(DATA_DIR / "household_power_daily.parquet")
    monthly = pd.read_parquet(DATA_DIR / "household_power_monthly.parquet")
    return cleaned, hourly, daily, monthly


def _energy_totals(
    cleaned: pd.DataFrame,
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
) -> dict[str, float]:
    """Return the total energy reported by each Phase 3 dataset."""
    return {
        "minute": float(cleaned["energy_consumption_kwh"].sum()),
        "hourly": float(hourly["total_energy_consumption_kwh"].sum()),
        "daily": float(daily["total_energy_consumption_kwh"].sum()),
        "monthly": float(monthly["total_energy_consumption_kwh"].sum()),
    }


def _frame_summary(frame: pd.DataFrame, timestamp_column: str) -> dict[str, Any]:
    """Describe a prepared dataset for the JSON preparation summary."""
    return {
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "start": frame[timestamp_column].min().isoformat(),
        "end": frame[timestamp_column].max().isoformat(),
        "splits": [
            {
                "split": row["split"],
                "rows": int(row["rows"]),
                "start": pd.Timestamp(row["start"]).isoformat(),
                "end": pd.Timestamp(row["end"]).isoformat(),
            }
            for row in split_summary(frame, timestamp_column)
        ],
    }


def run_prepare_data(verbose: bool = True) -> dict[str, Any]:
    """Build, validate and save both Phase 4 modelling datasets."""
    started_utc = datetime.now(UTC)
    started = time.perf_counter()
    ML_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if verbose:
        print("=" * 78)
        print(f"{PROJECT_NAME.upper()} - PHASE 4 ML DATA PREPARATION")
        print("=" * 78)
        print(f"Project root: {PROJECT_ROOT}")
        print(f"Input folder: {DATA_DIR}")

    missing_files = [
        filename
        for filename in EXPECTED_INPUTS
        if not (DATA_DIR / filename).is_file()
    ]
    if missing_files:
        raise FileNotFoundError(
            "Phase 3 outputs are missing: " + ", ".join(missing_files)
        )

    checks = validate_phase3_inputs(DATA_DIR, EXPECTED_INPUTS)
    if any(check.status == FAIL for check in checks):
        raise RuntimeError(
            "Phase 3 input validation failed:\n"
            + "\n".join(check_lines(checks, include_passed=False))
        )

    load_started = time.perf_counter()
    cleaned, hourly, daily, monthly = _load_inputs()
    load_seconds = time.perf_counter() - load_started

    totals = _energy_totals(cleaned, hourly, daily, monthly)
    total_spread = max(totals.values()) - min(totals.values())
    add_check(
        checks,
        "INPUT",
        "aggregate energy totals agree",
        total_spread <= 1e-6,
        f"spread {total_spread:.3e} kWh across minute/hourly/daily/monthly",
    )

    expected_minutes = int(hourly["expected_observation_count"].sum())
    valid_minutes = int(hourly["valid_observation_count"].sum())
    add_check(
        checks,
        "INPUT",
        "hourly counts reconcile with cleaned minute data",
        expected_minutes >= valid_minutes and valid_minutes == len(cleaned),
        f"hourly expected grid {expected_minutes:,}, valid {valid_minutes:,}, "
        f"cleaned rows {len(cleaned):,}; "
        f"{expected_minutes - valid_minutes:,} unresolved slots removed in Phase 3",
    )

    complete_hours = int(hourly["is_complete"].sum())
    incomplete_hours = int(len(hourly) - complete_hours)
    empty_hours = int((hourly["valid_observation_count"] == 0).sum())
    minute_imputed = int(cleaned["is_imputed"].sum())

    if verbose:
        print(
            f"Loaded minute={len(cleaned):,}, hourly={len(hourly):,}, "
            f"daily={len(daily):,}, monthly={len(monthly):,} in "
            f"{load_seconds:.2f} s"
        )
        print(
            f"Hourly coverage: {complete_hours:,} complete, "
            f"{incomplete_hours:,} incomplete ({empty_hours:,} empty)"
        )

    forecast_started = time.perf_counter()
    forecast = build_forecasting_dataset(hourly)
    forecast_seconds = time.perf_counter() - forecast_started
    forecast_checks = validate_forecast_dataset(forecast, FORECAST_FEATURES)
    checks.extend(forecast_checks)

    anomaly_started = time.perf_counter()
    anomaly = build_anomaly_dataset(cleaned)
    anomaly_seconds = time.perf_counter() - anomaly_started
    anomaly_checks = validate_anomaly_dataset(anomaly, ANOMALY_FEATURES)
    checks.extend(anomaly_checks)

    validation_summary = summarize_checks(checks)
    if validation_summary["failed"]:
        raise RuntimeError(
            "Prepared data validation failed:\n"
            + "\n".join(check_lines(checks, include_passed=False))
        )

    forecast_path = ML_DATA_DIR / FORECAST_DATASET_PATH.name
    anomaly_path = ML_DATA_DIR / ANOMALY_DATASET_PATH.name
    forecast.to_parquet(forecast_path, index=False, compression="snappy")
    anomaly.to_parquet(anomaly_path, index=False, compression="snappy")

    modeling_rows = int(forecast["is_modeling_row"].sum())
    target = forecast.loc[forecast["is_modeling_row"], TARGET_COLUMN]
    forecast_summary = _frame_summary(forecast, "timestamp")
    anomaly_summary = _frame_summary(anomaly, "timestamp")
    forecast_summary.update(
        {
            "hourly_intervals": int(len(hourly)),
            "complete_hours": complete_hours,
            "incomplete_hours": incomplete_hours,
            "empty_hours": empty_hours,
            "modeling_rows": modeling_rows,
            "warmup_excluded_rows": int(len(forecast) - modeling_rows),
            "feature_count": len(FORECAST_FEATURES),
            "features": list(FORECAST_FEATURES),
            "target": TARGET_COLUMN,
            "target_min": float(target.min()),
            "target_median": float(target.median()),
            "target_mean": float(target.mean()),
            "target_max": float(target.max()),
            "build_seconds": forecast_seconds,
            "file_bytes": int(forecast_path.stat().st_size),
            "file_sha256": sha256sum(forecast_path),
        }
    )
    anomaly_summary.update(
        {
            "cleaned_minutes": int(len(cleaned)),
            "imputed_rows_excluded": minute_imputed,
            "warmup_or_gap_rows_excluded": int(len(cleaned) - len(anomaly)),
            "feature_count": len(ANOMALY_FEATURES),
            "features": list(ANOMALY_FEATURES),
            "zscore_threshold": 3.0,
            "zscore_anomalies_in_prepared_data": int(
                (anomaly["gap_z_24h"].abs() >= 3.0).sum()
            ),
            "build_seconds": anomaly_seconds,
            "file_bytes": int(anomaly_path.stat().st_size),
            "file_sha256": sha256sum(anomaly_path),
        }
    )

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "phase": 4,
        "dataset": "Individual Household Electric Power Consumption",
        "input_seconds": load_seconds,
        "total_seconds": time.perf_counter() - started,
        "started_at_utc": started_utc.isoformat(),
        "inputs": {
            "cleaned": {"rows": int(len(cleaned)), "columns": int(cleaned.shape[1])},
            "hourly": {"rows": int(len(hourly)), "columns": int(hourly.shape[1])},
            "daily": {"rows": int(len(daily)), "columns": int(daily.shape[1])},
            "monthly": {"rows": int(len(monthly)), "columns": int(monthly.shape[1])},
            "minute_imputed_rows": minute_imputed,
            "energy_totals_kwh": totals,
        },
        "forecasting": forecast_summary,
        "anomaly_detection": anomaly_summary,
        "validation": summarize_checks(checks),
        "artifacts": {
            "forecasting_dataset": str(forecast_path.relative_to(PROJECT_ROOT)),
            "anomaly_dataset": str(anomaly_path.relative_to(PROJECT_ROOT)),
        },
    }
    with PREPARATION_SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    if verbose:
        print(
            f"Forecasting: {len(forecast):,} grid rows -> {modeling_rows:,} "
            f"modelling rows in {forecast_seconds:.2f} s"
        )
        for row in forecast_summary["splits"]:
            print(
                f"  {row['split']:<10} {row['rows']:>7,} rows "
                f"{row['start']} -> {row['end']}"
            )
        print(
            f"Anomaly: {len(anomaly):,} usable minutes in "
            f"{anomaly_seconds:.2f} s"
        )
        for row in anomaly_summary["splits"]:
            print(
                f"  {row['split']:<10} {row['rows']:>7,} rows "
                f"{row['start']} -> {row['end']}"
            )
        validation_summary = summary["validation"]
        print(
            f"Validation: {validation_summary['passed']} passed, "
            f"{validation_summary['failed']} failed, "
            f"{validation_summary['warnings']} warnings "
            f"({validation_summary['status']})"
        )
        for line in check_lines(checks, include_passed=False):
            print("  " + line)
        print(f"Saved: {forecast_path.relative_to(PROJECT_ROOT)}")
        print(f"Saved: {anomaly_path.relative_to(PROJECT_ROOT)}")

    del cleaned, hourly, daily, monthly, forecast, anomaly
    gc.collect()
    return summary


def main() -> int:
    """Prepare the ML datasets from the command line."""
    try:
        summary = run_prepare_data(verbose=True)
    except Exception as error:  # pragma: no cover - surfaced with a clear message
        print(f"\nERROR: {error}")
        return 1
    print(
        f"\nPhase 4 data preparation status: {summary['validation']['status']} "
        f"({summary['total_seconds']:.2f} s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
