"""Run the complete Phase 3 EcoPulse AI ETL workflow.

Stages:

1. **Extract** - verify the raw dataset checksum and load it read-only.
2. **Clean** - parse timestamps, convert numerics, interpolate only short
   gaps, retain long gaps, and remove unresolved rows only for modelling.
3. **Transform** - add calendar and energy features, then build gap-aware
   hourly, daily and monthly aggregates.
4. **Load** - write four Parquet datasets with PyArrow.
5. **Validate** - run manual consistency checks, Pandera schemas and Parquet
   readback verification.
6. **Report** - write all five Phase 3 reports.

Run from any directory::

    python data-engineering/src/04_run_etl_pipeline.py
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
import time
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pandera
import pandera.pandas as pa
import pyarrow
from pandera.pandas import Check, Column, DataFrameSchema

# ---------------------------------------------------------------------------
# Paths and schema
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "household_power_consumption.txt"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORT_DIR = PROJECT_ROOT / "reports" / "data-engineering"

NUMERIC_COLUMNS = [
    "Global_active_power",
    "Global_reactive_power",
    "Voltage",
    "Global_intensity",
    "Sub_metering_1",
    "Sub_metering_2",
    "Sub_metering_3",
]
SUB_METERING_COLUMNS = ["Sub_metering_1", "Sub_metering_2", "Sub_metering_3"]
TIMESTAMP_COLUMN = "timestamp"
IMPUTED_COLUMN = "is_imputed"
ENERGY_COLUMN = "energy_consumption_kwh"

DATETIME_COLUMNS = [
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "day_of_week",
    "day_name",
    "is_weekend",
]

AGGREGATION_NAMES = ("hourly", "daily", "monthly")
AGGREGATION_REQUIRED_COLUMNS = [
    "period_start",
    "expected_observation_count",
    "valid_observation_count",
    "imputed_observation_count",
    "coverage_percentage",
    "is_complete",
    "mean_global_active_power_kw",
    "max_global_active_power_kw",
    "min_global_active_power_kw",
    "total_energy_consumption_kwh",
    "mean_global_reactive_power_kw",
    "mean_voltage_v",
    "mean_global_intensity_a",
    "mean_sub_metering_1_wh",
    "mean_sub_metering_2_wh",
    "mean_sub_metering_3_wh",
    "total_sub_metering_1_kwh",
    "total_sub_metering_2_kwh",
    "total_sub_metering_3_kwh",
    "total_sub_metering_kwh",
]

PROJECT_NAME = "EcoPulse AI"
DATASET_NAME = "Individual Household Electric Power Consumption"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_bytes(size_bytes: int | float) -> str:
    """Return a human-readable byte size."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:,.2f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def wrap_report_lines(lines: list[str], width: int = 78) -> list[str]:
    """Wrap long bullet paragraphs while leaving headings and tables intact."""
    wrapped: list[str] = []
    for line in lines:
        if len(line) <= width or not line.startswith(("- ", "  - ")):
            wrapped.append(line)
            continue
        prefix = line[: line.index("- ") + 2]
        body = line[len(prefix) :]
        wrapped.append(
            textwrap.fill(
                body,
                width=width,
                initial_indent=prefix,
                subsequent_indent=" " * len(prefix),
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return wrapped


def write_text_report(path: Path, lines: list[str]) -> Path:
    """Write a report with UTF-8 encoding and consistent wrapping."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(wrap_report_lines(lines)), encoding="utf-8")
    return path


def format_timestamp(value: Any) -> str:
    """Format a timestamp for reports, or return ``n/a`` when missing."""
    if value is None or pd.isna(value):
        return "n/a"
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def _load_module(module_name: str, filename: str) -> Any:
    """Load a numbered sibling script as an importable module."""
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Validation result model
# ---------------------------------------------------------------------------


@dataclass
class ValidationCheck:
    """One named validation result."""

    category: str
    name: str
    status: str
    detail: str = ""


@dataclass
class ValidationResult:
    """Collected validation checks, warnings and failures."""

    checks: list[ValidationCheck] = field(default_factory=list)
    started_utc: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_utc: datetime | None = None

    def add_pass(self, category: str, name: str, detail: str = "") -> None:
        """Record a passed check."""
        self.checks.append(ValidationCheck(category, name, "PASS", detail))

    def add_fail(self, category: str, name: str, detail: str = "") -> None:
        """Record a failed check."""
        self.checks.append(ValidationCheck(category, name, "FAIL", detail))

    def add_warning(self, category: str, name: str, detail: str = "") -> None:
        """Record a non-fatal data-quality warning."""
        self.checks.append(ValidationCheck(category, name, "WARN", detail))

    @property
    def passed(self) -> list[ValidationCheck]:
        """All passed checks."""
        return [check for check in self.checks if check.status == "PASS"]

    @property
    def failed(self) -> list[ValidationCheck]:
        """All failed checks."""
        return [check for check in self.checks if check.status == "FAIL"]

    @property
    def warnings(self) -> list[ValidationCheck]:
        """All warning checks."""
        return [check for check in self.checks if check.status == "WARN"]

    @property
    def final_status(self) -> str:
        """Human-readable final validation status."""
        if self.failed:
            return "FAILED"
        if self.warnings:
            return "PASSED WITH WARNINGS"
        return "PASSED"


# ---------------------------------------------------------------------------
# Pandera schemas
# ---------------------------------------------------------------------------


def _non_negative(series: pd.Series) -> bool:
    """Return true when every non-null value is non-negative."""
    return bool(series.dropna().ge(0).all())


def _increasing(series: pd.Series) -> bool:
    """Return true when a datetime series is chronologically sorted."""
    return bool(series.is_monotonic_increasing)


def build_minute_schema() -> DataFrameSchema:
    """Schema for the transformed minute-level modelling dataset."""
    non_negative = Check(_non_negative, name="non_negative")
    return DataFrameSchema(
        {
            "timestamp": Column(
                pa.DateTime,
                nullable=False,
                unique=True,
                checks=Check(_increasing, name="chronological"),
            ),
            "year": Column(np.int16, checks=Check.in_range(2006, 2030)),
            "month": Column(np.int8, checks=Check.in_range(1, 12)),
            "day": Column(np.int8, checks=Check.in_range(1, 31)),
            "hour": Column(np.int8, checks=Check.in_range(0, 23)),
            "minute": Column(np.int8, checks=Check.in_range(0, 59)),
            "day_of_week": Column(np.int8, checks=Check.in_range(0, 6)),
            "day_name": Column(str),
            "is_weekend": Column(bool),
            "Global_active_power": Column(
                np.float64, nullable=False, checks=non_negative
            ),
            "Global_reactive_power": Column(
                np.float64, nullable=False, checks=non_negative
            ),
            "Voltage": Column(np.float64, nullable=False, checks=non_negative),
            "Global_intensity": Column(
                np.float64, nullable=False, checks=non_negative
            ),
            "Sub_metering_1": Column(
                np.float64, nullable=False, checks=non_negative
            ),
            "Sub_metering_2": Column(
                np.float64, nullable=False, checks=non_negative
            ),
            "Sub_metering_3": Column(
                np.float64, nullable=False, checks=non_negative
            ),
            "energy_consumption_kwh": Column(
                np.float64, nullable=False, checks=non_negative
            ),
            "is_imputed": Column(bool),
        },
        strict=False,
        name="minute_dataset",
    )


def build_aggregate_schema(name: str) -> DataFrameSchema:
    """Schema for one gap-aware aggregation level."""
    non_negative = Check(_non_negative, name="non_negative")
    schema: dict[str, Any] = {
        "period_start": Column(
            pa.DateTime,
            nullable=False,
            unique=True,
            checks=Check(_increasing, name="chronological"),
        ),
        "expected_observation_count": Column(np.int64, checks=Check.gt(0)),
        "valid_observation_count": Column(np.int64, checks=Check.ge(0)),
        "imputed_observation_count": Column(np.int64, checks=Check.ge(0)),
        "coverage_percentage": Column(
            np.float64, checks=Check.in_range(0.0, 100.0)
        ),
        "is_complete": Column(bool),
        "mean_global_active_power_kw": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "max_global_active_power_kw": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "min_global_active_power_kw": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "total_energy_consumption_kwh": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "mean_global_reactive_power_kw": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "mean_voltage_v": Column(np.float64, nullable=True, checks=non_negative),
        "mean_global_intensity_a": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "mean_sub_metering_1_wh": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "mean_sub_metering_2_wh": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "mean_sub_metering_3_wh": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "total_sub_metering_1_kwh": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "total_sub_metering_2_kwh": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "total_sub_metering_3_kwh": Column(
            np.float64, nullable=True, checks=non_negative
        ),
        "total_sub_metering_kwh": Column(
            np.float64, nullable=True, checks=non_negative
        ),
    }
    return DataFrameSchema(schema, strict=False, name=name)


def _run_pandera_schema(
    result: ValidationResult,
    dataframe: pd.DataFrame,
    schema: DataFrameSchema,
    label: str,
) -> None:
    """Validate one frame with Pandera and record a concise result."""
    try:
        schema.validate(dataframe, lazy=True)
    except Exception as exc:  # Pandera raises SchemaError or SchemaErrors
        failure_cases = getattr(exc, "failure_cases", None)
        if isinstance(failure_cases, pd.DataFrame) and not failure_cases.empty:
            detail = failure_cases.head(20).to_string(index=False)
        else:
            detail = str(exc)
        if len(detail) > 4000:
            detail = detail[:4000] + "\n... truncated ..."
        result.add_fail("Pandera", f"{label} schema", detail)
    else:
        result.add_pass(
            "Pandera",
            f"{label} schema",
            f"{len(dataframe):,} rows validated against the declared Pandera schema.",
        )


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------


def _add_boolean_check(
    result: ValidationResult,
    category: str,
    name: str,
    condition: bool,
    pass_detail: str,
    fail_detail: str,
) -> None:
    """Record a pass/fail check from a boolean condition."""
    if condition:
        result.add_pass(category, name, pass_detail)
    else:
        result.add_fail(category, name, fail_detail)


def _validate_minute_dataset(
    result: ValidationResult,
    transformed: pd.DataFrame,
    cleaning_stats: Any,
    transform_stats: Any,
) -> None:
    """Validate the minute-level modelling dataset."""
    category = "Minute dataset"
    required = [
        TIMESTAMP_COLUMN,
        *DATETIME_COLUMNS,
        *NUMERIC_COLUMNS,
        ENERGY_COLUMN,
        IMPUTED_COLUMN,
    ]
    missing = [column for column in required if column not in transformed.columns]
    _add_boolean_check(
        result,
        category,
        "Required columns exist",
        not missing,
        f"All {len(required)} required columns are present.",
        "Missing columns: " + ", ".join(missing),
    )
    if missing:
        return

    _add_boolean_check(
        result,
        category,
        "Row count matches the cleaning result",
        len(transformed) == cleaning_stats.final_rows,
        f"{len(transformed):,} rows.",
        f"Expected {cleaning_stats.final_rows:,}, found {len(transformed):,}.",
    )
    _add_boolean_check(
        result,
        category,
        "Row count matches the transformation result",
        len(transformed) == transform_stats.output_rows,
        f"{len(transformed):,} rows.",
        f"Expected {transform_stats.output_rows:,}, found {len(transformed):,}.",
    )
    _add_boolean_check(
        result,
        category,
        "Timestamp is datetime and non-null",
        pd.api.types.is_datetime64_any_dtype(transformed[TIMESTAMP_COLUMN])
        and not transformed[TIMESTAMP_COLUMN].isna().any(),
        "Datetime dtype with no invalid values.",
        "Timestamp dtype or nullability is invalid.",
    )
    _add_boolean_check(
        result,
        category,
        "Timestamps are unique",
        not transformed[TIMESTAMP_COLUMN].duplicated().any(),
        "No duplicate timestamps.",
        f"{int(transformed[TIMESTAMP_COLUMN].duplicated().sum()):,} duplicate timestamps.",
    )
    _add_boolean_check(
        result,
        category,
        "Rows are sorted chronologically",
        transformed[TIMESTAMP_COLUMN].is_monotonic_increasing,
        "Timestamp order is strictly increasing.",
        "Timestamp order is not chronological.",
    )
    first_last_ok = (
        transformed[TIMESTAMP_COLUMN].min() == cleaning_stats.first_timestamp
        and transformed[TIMESTAMP_COLUMN].max() == cleaning_stats.last_timestamp
    )
    _add_boolean_check(
        result,
        category,
        "Time coverage matches the cleaning range",
        first_last_ok,
        f"{format_timestamp(transformed[TIMESTAMP_COLUMN].min())} to "
        f"{format_timestamp(transformed[TIMESTAMP_COLUMN].max())}.",
        "The transformed time range differs from the cleaned source range.",
    )

    numeric_ok = all(
        pd.api.types.is_float_dtype(transformed[column])
        for column in [*NUMERIC_COLUMNS, ENERGY_COLUMN]
    )
    _add_boolean_check(
        result,
        category,
        "Measurement and energy columns are numeric",
        numeric_ok,
        "All eight measurement/energy columns are float64.",
        "One or more measurement/energy columns are not numeric.",
    )

    missing_measurements = int(transformed[NUMERIC_COLUMNS].isna().sum().sum())
    _add_boolean_check(
        result,
        category,
        "No unresolved measurement values",
        missing_measurements == 0,
        "The final modelling dataset has zero missing measurements.",
        f"{missing_measurements:,} missing measurement cells remain.",
    )
    missing_energy = int(transformed[ENERGY_COLUMN].isna().sum())
    _add_boolean_check(
        result,
        category,
        "Energy has no missing values",
        missing_energy == 0,
        "Every retained row has a calculated energy value.",
        f"{missing_energy:,} energy values are missing.",
    )

    difference = (
        transformed[ENERGY_COLUMN] - transformed["Global_active_power"] / 60.0
    ).abs()
    max_difference = float(difference.max()) if len(difference) else 0.0
    _add_boolean_check(
        result,
        category,
        "Energy equals Global_active_power / 60",
        max_difference <= 1e-12,
        f"Maximum absolute difference is {max_difference:.3e} kWh.",
        f"Maximum absolute difference is {max_difference:.6e} kWh.",
    )
    _add_boolean_check(
        result,
        category,
        "Energy is non-negative",
        bool(transformed[ENERGY_COLUMN].ge(0).all()),
        "No negative per-minute energy value.",
        f"{int((transformed[ENERGY_COLUMN] < 0).sum()):,} negative values.",
    )

    feature_ranges = {
        "month": (1, 12),
        "day": (1, 31),
        "hour": (0, 23),
        "minute": (0, 59),
        "day_of_week": (0, 6),
    }
    for feature, (lower, upper) in feature_ranges.items():
        in_range = bool(
            transformed[feature].between(lower, upper, inclusive="both").all()
        )
        _add_boolean_check(
            result,
            category,
            f"{feature} is in range {lower}-{upper}",
            in_range,
            f"{feature} values are valid.",
            f"{feature} contains out-of-range values.",
        )

    weekend_ok = bool(
        transformed["is_weekend"]
        .eq(transformed["day_of_week"] >= 5)
        .all()
    )
    _add_boolean_check(
        result,
        category,
        "is_weekend is consistent with day_of_week",
        weekend_ok,
        "Weekend flags match Saturday/Sunday.",
        "Weekend flags disagree with day_of_week.",
    )
    day_name_ok = bool(
        transformed["day_name"]
        .eq(transformed[TIMESTAMP_COLUMN].dt.day_name())
        .all()
    )
    _add_boolean_check(
        result,
        category,
        "day_name matches the timestamp",
        day_name_ok,
        "All day names are consistent.",
        "One or more day names disagree with the timestamp.",
    )
    timestamp = transformed[TIMESTAMP_COLUMN]
    calendar_ok = bool(
        (
            (transformed["year"].astype("int32") == timestamp.dt.year)
            & (transformed["month"].astype("int8") == timestamp.dt.month)
            & (transformed["day"].astype("int8") == timestamp.dt.day)
            & (transformed["hour"].astype("int8") == timestamp.dt.hour)
            & (transformed["minute"].astype("int8") == timestamp.dt.minute)
        ).all()
    )
    _add_boolean_check(
        result,
        category,
        "Calendar features match the timestamp components",
        calendar_ok,
        "Year, month, day, hour and minute all match the timestamp.",
        "One or more calendar features disagree with the timestamp.",
    )

    imputed_count = int(transformed[IMPUTED_COLUMN].sum())
    _add_boolean_check(
        result,
        category,
        "Imputed-row flag matches the cleaning audit",
        imputed_count == cleaning_stats.interpolated_rows,
        f"{imputed_count:,} rows are flagged as imputed.",
        f"Expected {cleaning_stats.interpolated_rows:,} imputed rows, "
        f"found {imputed_count:,}.",
    )

    non_imputed_energy = float(
        transformed.loc[~transformed[IMPUTED_COLUMN], ENERGY_COLUMN].sum()
    )
    _add_boolean_check(
        result,
        category,
        "Measured energy matches the Phase 2 valid-reading total",
        bool(
            np.isclose(
                non_imputed_energy,
                cleaning_stats.original_valid_energy_kwh,
                rtol=1e-12,
                atol=1e-9,
            )
        ),
        f"{non_imputed_energy:,.6f} kWh of measured readings preserves the "
        f"Phase 2 total of {cleaning_stats.original_valid_energy_kwh:,.6f} kWh.",
        f"Measured energy is {non_imputed_energy:,.6f} kWh but the Phase 2 "
        f"valid-reading total is "
        f"{cleaning_stats.original_valid_energy_kwh:,.6f} kWh.",
    )

    total_energy = float(transformed[ENERGY_COLUMN].sum())
    decomposition_ok = bool(
        np.isclose(
            total_energy,
            non_imputed_energy + cleaning_stats.imputed_energy_kwh,
            rtol=1e-12,
            atol=1e-9,
        )
    ) and bool(
        np.isclose(
            transform_stats.non_imputed_energy_kwh,
            non_imputed_energy,
            rtol=0,
            atol=1e-9,
        )
    )
    _add_boolean_check(
        result,
        category,
        "Total energy equals measured plus imputed energy",
        decomposition_ok,
        f"{non_imputed_energy:,.6f} kWh measured + "
        f"{cleaning_stats.imputed_energy_kwh:,.6f} kWh imputed = "
        f"{total_energy:,.6f} kWh.",
        "Total energy does not decompose into measured plus imputed energy.",
    )

    _run_pandera_schema(
        result,
        transformed,
        build_minute_schema(),
        "Minute dataset",
    )


def _validate_aggregation(
    result: ValidationResult,
    name: str,
    aggregation: pd.DataFrame,
    transformed: pd.DataFrame,
    cleaning_stats: Any,
) -> None:
    """Validate one hourly, daily or monthly aggregation."""
    category = f"{name.capitalize()} aggregation"
    missing = [
        column
        for column in AGGREGATION_REQUIRED_COLUMNS
        if column not in aggregation.columns
    ]
    _add_boolean_check(
        result,
        category,
        "Required columns exist",
        not missing,
        f"All {len(AGGREGATION_REQUIRED_COLUMNS)} required columns are present.",
        "Missing columns: " + ", ".join(missing),
    )
    if missing:
        return

    _add_boolean_check(
        result,
        category,
        "Aggregation is not empty",
        len(aggregation) > 0,
        f"{len(aggregation):,} intervals.",
        "The aggregation contains no intervals.",
    )
    _add_boolean_check(
        result,
        category,
        "Period starts are valid and unique",
        pd.api.types.is_datetime64_any_dtype(aggregation["period_start"])
        and not aggregation["period_start"].isna().any()
        and not aggregation["period_start"].duplicated().any(),
        "Datetime period starts with no duplicates.",
        "Period starts are invalid, null or duplicated.",
    )
    _add_boolean_check(
        result,
        category,
        "Periods are sorted chronologically",
        aggregation["period_start"].is_monotonic_increasing,
        "Period starts are strictly increasing.",
        "Period starts are not sorted.",
    )

    expected = aggregation["expected_observation_count"]
    valid = aggregation["valid_observation_count"]
    imputed = aggregation["imputed_observation_count"]
    _add_boolean_check(
        result,
        category,
        "Expected observation counts are positive",
        bool(expected.gt(0).all()),
        f"Minimum expected count is {int(expected.min()):,}.",
        "One or more expected counts are zero or negative.",
    )
    _add_boolean_check(
        result,
        category,
        "Valid counts are within expected counts",
        bool(valid.between(0, expected).all()),
        "0 <= valid <= expected for every interval.",
        "One or more valid counts fall outside 0..expected.",
    )
    _add_boolean_check(
        result,
        category,
        "Imputed counts do not exceed valid counts",
        bool(imputed.le(valid).all()),
        "Imputed counts are bounded by valid counts.",
        "One or more imputed counts exceed valid counts.",
    )
    coverage_ok = bool(
        np.allclose(
            aggregation["coverage_percentage"].to_numpy(),
            (valid / expected * 100.0).to_numpy(),
            rtol=0,
            atol=1e-9,
        )
    )
    _add_boolean_check(
        result,
        category,
        "Coverage percentage is calculated correctly",
        coverage_ok,
        "Coverage equals valid / expected * 100 for every interval.",
        "Coverage does not match valid / expected * 100.",
    )
    complete_ok = bool(
        aggregation["is_complete"].eq(valid.eq(expected)).all()
    )
    _add_boolean_check(
        result,
        category,
        "is_complete matches the observation counts",
        complete_ok,
        "is_complete is true exactly when valid equals expected.",
        "is_complete disagrees with the observation counts.",
    )

    numeric_energy_columns = [
        "mean_global_active_power_kw",
        "max_global_active_power_kw",
        "min_global_active_power_kw",
        "total_energy_consumption_kwh",
        "mean_global_reactive_power_kw",
        "mean_voltage_v",
        "mean_global_intensity_a",
        "mean_sub_metering_1_wh",
        "mean_sub_metering_2_wh",
        "mean_sub_metering_3_wh",
        "total_sub_metering_1_kwh",
        "total_sub_metering_2_kwh",
        "total_sub_metering_3_kwh",
        "total_sub_metering_kwh",
    ]
    non_negative_ok = bool(
        aggregation[numeric_energy_columns].dropna().ge(0).all().all()
    )
    _add_boolean_check(
        result,
        category,
        "Energy and measurement metrics are non-negative",
        non_negative_ok,
        "No negative metric was found.",
        "One or more metrics are negative.",
    )

    _add_boolean_check(
        result,
        category,
        "Expected minute total matches the source grid",
        int(expected.sum()) == cleaning_stats.expected_grid_slots,
        f"{int(expected.sum()):,} expected minutes.",
        f"Expected {int(expected.sum()):,}, source grid is "
        f"{cleaning_stats.expected_grid_slots:,}.",
    )
    _add_boolean_check(
        result,
        category,
        "Valid minute total matches the minute dataset",
        int(valid.sum()) == len(transformed),
        f"{int(valid.sum()):,} valid minutes.",
        f"Expected {len(transformed):,}, found {int(valid.sum()):,}.",
    )
    _add_boolean_check(
        result,
        category,
        "Imputed minute total matches the minute dataset",
        int(imputed.sum()) == int(transformed[IMPUTED_COLUMN].sum()),
        f"{int(imputed.sum()):,} imputed minutes.",
        f"Expected {int(transformed[IMPUTED_COLUMN].sum()):,}, "
        f"found {int(imputed.sum()):,}.",
    )

    minute_energy = float(transformed[ENERGY_COLUMN].sum())
    aggregate_energy = float(
        aggregation["total_energy_consumption_kwh"].sum(min_count=1)
    )
    _add_boolean_check(
        result,
        category,
        "Aggregated energy matches the minute dataset",
        bool(np.isclose(aggregate_energy, minute_energy, rtol=1e-9, atol=1e-6)),
        f"{aggregate_energy:,.6f} kWh against {minute_energy:,.6f} kWh.",
        f"{aggregate_energy:,.6f} kWh differs from {minute_energy:,.6f} kWh.",
    )

    if name == "hourly":
        aligned = (
            aggregation["period_start"].dt.minute.eq(0)
            & aggregation["period_start"].dt.second.eq(0)
        )
    elif name == "daily":
        aligned = (
            aggregation["period_start"].dt.hour.eq(0)
            & aggregation["period_start"].dt.minute.eq(0)
            & aggregation["period_start"].dt.second.eq(0)
        )
    else:
        aligned = (
            aggregation["period_start"].dt.day.eq(1)
            & aggregation["period_start"].dt.hour.eq(0)
            & aggregation["period_start"].dt.minute.eq(0)
            & aggregation["period_start"].dt.second.eq(0)
        )
    _add_boolean_check(
        result,
        category,
        "Period starts align to the interval boundary",
        bool(aligned.all()),
        "All period starts are aligned.",
        "One or more period starts are misaligned.",
    )

    if name == "hourly":
        spacing_ok = bool(
            aggregation["period_start"]
            .diff()
            .dt.total_seconds()
            .dropna()
            .eq(3600)
            .all()
        )
    elif name == "daily":
        spacing_ok = bool(
            aggregation["period_start"]
            .diff()
            .dt.total_seconds()
            .dropna()
            .eq(86400)
            .all()
        )
    else:
        month_numbers = (
            aggregation["period_start"].dt.to_period("M").astype("int64")
        )
        spacing_ok = bool(month_numbers.diff().dropna().eq(1).all())
    _add_boolean_check(
        result,
        category,
        "Consecutive periods have a regular interval",
        spacing_ok,
        "No missing calendar period is hidden by irregular spacing.",
        "The period spacing is irregular.",
    )

    empty_intervals = int(valid.eq(0).sum())
    if empty_intervals:
        empty_detail = (
            f"{empty_intervals:,} intervals have no valid observation and carry "
            "missing metrics rather than zero energy."
        )
    else:
        empty_detail = (
            "No interval is entirely empty; every period contains at least one "
            "valid observation. Partial periods remain flagged by is_complete."
        )
    _add_boolean_check(
        result,
        category,
        "Empty intervals are represented",
        empty_intervals > 0 if name in ("hourly", "daily") else True,
        empty_detail,
        f"No empty interval was found; verify that missing periods were not "
        "silently dropped.",
    )

    _run_pandera_schema(
        result,
        aggregation,
        build_aggregate_schema(name),
        f"{name.capitalize()} aggregation",
    )


def validate_outputs(
    transformed: pd.DataFrame,
    aggregations: dict[str, pd.DataFrame],
    cleaning_stats: Any,
    transform_stats: Any,
    output_info: dict[str, dict[str, Any]] | None = None,
    readback: bool = True,
) -> ValidationResult:
    """Run all Phase 3 validation checks and return an auditable result."""
    result = ValidationResult()
    _validate_minute_dataset(result, transformed, cleaning_stats, transform_stats)

    for name in AGGREGATION_NAMES:
        _validate_aggregation(
            result,
            name,
            aggregations[name],
            transformed,
            cleaning_stats,
        )

    # Cross-aggregate checks
    category = "Cross-aggregate"
    minute_energy = float(transformed[ENERGY_COLUMN].sum())
    minute_valid = len(transformed)
    minute_imputed = int(transformed[IMPUTED_COLUMN].sum())
    hourly = aggregations["hourly"]
    daily = aggregations["daily"]
    monthly = aggregations["monthly"]
    _add_boolean_check(
        result,
        category,
        "Hourly, daily and monthly valid counts agree",
        int(hourly["valid_observation_count"].sum())
        == int(daily["valid_observation_count"].sum())
        == int(monthly["valid_observation_count"].sum())
        == minute_valid,
        f"All levels represent {minute_valid:,} valid minutes.",
        "The aggregation levels disagree on the number of valid minutes.",
    )
    _add_boolean_check(
        result,
        category,
        "Hourly, daily and monthly imputed counts agree",
        int(hourly["imputed_observation_count"].sum())
        == int(daily["imputed_observation_count"].sum())
        == int(monthly["imputed_observation_count"].sum())
        == minute_imputed,
        f"All levels represent {minute_imputed:,} imputed minutes.",
        "The aggregation levels disagree on the number of imputed minutes.",
    )
    hourly_energy = float(
        hourly["total_energy_consumption_kwh"].sum(min_count=1)
    )
    daily_energy = float(daily["total_energy_consumption_kwh"].sum(min_count=1))
    monthly_energy = float(
        monthly["total_energy_consumption_kwh"].sum(min_count=1)
    )
    energy_consistent = all(
        np.isclose(value, minute_energy, rtol=1e-9, atol=1e-6)
        for value in (hourly_energy, daily_energy, monthly_energy)
    )
    _add_boolean_check(
        result,
        category,
        "Hourly, daily and monthly energy totals agree",
        energy_consistent,
        f"All levels total {minute_energy:,.6f} kWh.",
        "The aggregation levels disagree on total energy.",
    )
    _add_boolean_check(
        result,
        category,
        "All levels preserve the full expected minute grid",
        int(hourly["expected_observation_count"].sum())
        == int(daily["expected_observation_count"].sum())
        == int(monthly["expected_observation_count"].sum())
        == cleaning_stats.expected_grid_slots,
        f"All levels preserve {cleaning_stats.expected_grid_slots:,} expected minutes.",
        "One or more levels lost expected minutes.",
    )

    # Parquet readback verification
    if readback and output_info:
        _validate_parquet_readback(result, output_info, transformed, aggregations)

    # Warnings are facts about the data quality and modelling caveats, not
    # hidden failures.
    result.add_warning(
        "Data quality",
        "Timestamps are naive local civil time",
        "The source has no UTC offset. Phase 3 deliberately preserves the "
        "local wall-clock timestamps and does not apply a daylight-saving "
        "shift. A UTC/DST policy must be approved before database loading.",
    )
    result.add_warning(
        "Data quality",
        f"{cleaning_stats.interpolated_rows:,} rows contain short-gap interpolation",
        f"{cleaning_stats.interpolated_cells:,} cells across "
        f"{cleaning_stats.interpolated_gap_runs:,} gaps were linearly "
        f"interpolated (limit {cleaning_stats.interpolation_limit_minutes} "
        f"minutes). They contribute {cleaning_stats.imputed_energy_kwh:,.6f} "
        "kWh and are flagged with is_imputed = True.",
    )
    result.add_warning(
        "Data quality",
        f"{cleaning_stats.removed_rows:,} unresolved rows were removed for modelling",
        "Long gaps were not interpolated and were not replaced with zero. "
        "They are excluded only from the final modelling dataset; the cleaning "
        "report records the unresolved counts.",
    )
    retained_outliers = sum(
        int(item["Outliers"]) for item in cleaning_stats.outlier_table
    )
    result.add_warning(
        "Data quality",
        "IQR outliers were retained",
        f"{retained_outliers:,} measurement-cell outliers were identified. "
        "No genuine consumption peak was deleted, capped or clipped; the "
        "outlier table documents the IQR thresholds.",
    )
    result.add_warning(
        "Data quality",
        f"{cleaning_stats.submetering_violation_rows:,} minutes have sub-metered "
        "energy above whole-house energy",
        f"{cleaning_stats.submetering_violation_percent:.4f}% of valid minutes "
        "show a known UCI measurement inconsistency. Values were retained and "
        "not corrected.",
    )
    incomplete_hourly = int((~hourly["is_complete"]).sum())
    incomplete_daily = int((~daily["is_complete"]).sum())
    incomplete_monthly = int((~monthly["is_complete"]).sum())
    result.add_warning(
        "Aggregation",
        "Incomplete intervals are present and explicitly flagged",
        f"Hourly: {incomplete_hourly:,}; daily: {incomplete_daily:,}; "
        f"monthly: {incomplete_monthly:,}. Totals for these intervals cover "
        "valid minutes only and must not be presented as complete periods.",
    )

    result.finished_utc = datetime.now(UTC)
    return result


def _validate_parquet_readback(
    result: ValidationResult,
    output_info: dict[str, dict[str, Any]],
    transformed: pd.DataFrame,
    aggregations: dict[str, pd.DataFrame],
) -> None:
    """Read every output file back and compare key facts with memory."""
    category = "Output files"
    expected_frames = {"minute": transformed, **aggregations}
    for name, info in output_info.items():
        path = info["path"]
        if not path.exists():
            result.add_fail(category, f"{name} Parquet exists", f"Missing {path}")
            continue
        try:
            readback = pd.read_parquet(path)
        except Exception as exc:
            result.add_fail(
                category,
                f"{name} Parquet readback",
                f"{type(exc).__name__}: {exc}",
            )
            continue

        expected = expected_frames[name]
        shape_ok = (
            readback.shape[0] == info["rows"]
            and readback.shape[1] == info["columns"]
        )
        _add_boolean_check(
            result,
            category,
            f"{name} Parquet row and column counts",
            shape_ok,
            f"{readback.shape[0]:,} rows x {readback.shape[1]} columns.",
            f"Expected {info['rows']:,} x {info['columns']}, "
            f"found {readback.shape[0]:,} x {readback.shape[1]}.",
        )

        if name == "minute":
            time_ok = (
                pd.api.types.is_datetime64_any_dtype(readback[TIMESTAMP_COLUMN])
                and not readback[TIMESTAMP_COLUMN].isna().any()
                and readback[TIMESTAMP_COLUMN].is_monotonic_increasing
            )
            missing_ok = int(readback[NUMERIC_COLUMNS].isna().sum().sum()) == 0
            energy_ok = bool(
                np.isclose(
                    float(readback[ENERGY_COLUMN].sum()),
                    float(expected[ENERGY_COLUMN].sum()),
                    rtol=1e-12,
                    atol=1e-9,
                )
            )
            _add_boolean_check(
                result,
                category,
                "Minute Parquet preserves timestamps, values and energy",
                time_ok and missing_ok and energy_ok,
                "Timestamp order, completeness and total energy match the "
                "in-memory dataset.",
                "Timestamp order, completeness or total energy differs.",
            )
        else:
            valid_ok = int(readback["valid_observation_count"].sum()) == int(
                expected["valid_observation_count"].sum()
            )
            energy_ok = bool(
                np.isclose(
                    float(
                        readback["total_energy_consumption_kwh"].sum(min_count=1)
                    ),
                    float(
                        expected["total_energy_consumption_kwh"].sum(min_count=1)
                    ),
                    rtol=1e-9,
                    atol=1e-6,
                )
            )
            period_ok = (
                pd.api.types.is_datetime64_any_dtype(readback["period_start"])
                and readback["period_start"].is_monotonic_increasing
                and not readback["period_start"].duplicated().any()
            )
            _add_boolean_check(
                result,
                category,
                f"{name} Parquet preserves periods, counts and energy",
                valid_ok and energy_ok and period_ok,
                "Periods, valid counts and total energy match the in-memory "
                "aggregation.",
                "Periods, valid counts or total energy differ.",
            )


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------


def write_validation_report(
    result: ValidationResult,
    cleaning_stats: Any,
    transform_stats: Any,
    output_info: dict[str, dict[str, Any]],
    path: Path | None = None,
) -> Path:
    """Write the Phase 3 data validation report."""
    output_path = path or (REPORT_DIR / "data_validation_report.txt")
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    categories = [
        "Minute dataset",
        "Hourly aggregation",
        "Daily aggregation",
        "Monthly aggregation",
        "Cross-aggregate",
        "Pandera",
        "Output files",
        "Data quality",
        "Aggregation",
    ]

    lines = [
        "=" * 78,
        f"{PROJECT_NAME.upper()} - PHASE 3 DATA VALIDATION REPORT",
        "=" * 78,
        f"Generated (UTC): {generated}",
        f"Dataset: {DATASET_NAME}",
        "Scope: validated Phase 3 cleaning, features, energy and aggregations.",
        "",
        "1. SUMMARY",
        "-" * 78,
        f"Total checks:          {len(result.checks):,}",
        f"Passed checks:         {len(result.passed):,}",
        f"Failed checks:         {len(result.failed):,}",
        f"Warnings:              {len(result.warnings):,}",
        f"Final validation status: {result.final_status}",
        "",
        "2. DATASET CONTEXT",
        "-" * 78,
        f"Original rows:         {cleaning_stats.raw_rows:,}",
        f"Final modelling rows:  {cleaning_stats.final_rows:,}",
        f"Interpolated rows:     {cleaning_stats.interpolated_rows:,}",
        f"Unresolved rows removed: {cleaning_stats.removed_rows:,}",
        f"Measured energy:       {transform_stats.non_imputed_energy_kwh:,.6f} kWh",
        f"Imputed energy:        {transform_stats.imputed_energy_kwh:,.6f} kWh",
        f"Total energy:          {transform_stats.total_energy_kwh:,.6f} kWh",
        f"Phase 2 valid energy:  {cleaning_stats.original_valid_energy_kwh:,.6f} kWh",
        f"Expected minute grid:  {cleaning_stats.expected_grid_slots:,}",
        f"Output files validated:{len(output_info):>4}",
        "",
        "3. VALIDATION CHECKS",
        "-" * 78,
    ]

    for category in categories:
        category_checks = [
            check for check in result.checks if check.category == category
        ]
        if not category_checks:
            continue
        lines.append("")
        lines.append(category)
        lines.append("." * len(category))
        for check in category_checks:
            lines.append(f"[{check.status}] {check.name}")
            if check.detail:
                for detail_line in str(check.detail).splitlines():
                    if not detail_line.strip():
                        continue
                    wrapped = textwrap.wrap(
                        detail_line,
                        width=74,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                    lines.extend(f"       {part}" for part in wrapped)

    lines.extend(
        [
            "",
            "4. WARNINGS",
            "-" * 78,
        ]
    )
    if result.warnings:
        for warning in result.warnings:
            lines.append(f"[WARN] {warning.category}: {warning.name}")
            if warning.detail:
                for detail_line in str(warning.detail).splitlines():
                    wrapped = textwrap.wrap(
                        detail_line,
                        width=74,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                    lines.extend(f"       {part}" for part in wrapped)
    else:
        lines.append("None.")

    lines.extend(
        [
            "",
            "5. FAILURES",
            "-" * 78,
        ]
    )
    if result.failed:
        for failure in result.failed:
            lines.append(f"[FAIL] {failure.category}: {failure.name}")
            if failure.detail:
                for detail_line in str(failure.detail).splitlines():
                    wrapped = textwrap.wrap(
                        detail_line,
                        width=74,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                    lines.extend(f"       {part}" for part in wrapped)
    else:
        lines.append("None. No validation check failed.")

    lines.extend(
        [
            "",
            "6. VALIDATION ENVIRONMENT",
            "-" * 78,
            f"pandas:                {pd.__version__}",
            f"numpy:                 {np.__version__}",
            f"pandera:               {pandera.__version__}",
            f"pyarrow:               {pyarrow.__version__}",
            f"Validation started:    {result.started_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            f"Validation finished:   {result.finished_utc.strftime('%Y-%m-%dT%H:%M:%SZ') if result.finished_utc else 'n/a'}",
            "",
            "7. FINAL STATUS",
            "-" * 78,
            f"{result.final_status}",
            "",
            "Interpretation: warnings describe documented data limitations and "
            "required modelling caveats. They do not hide failed checks; every "
            "failure is listed in section 5.",
            "=" * 78,
            "",
        ]
    )
    return write_text_report(output_path, lines)


# ---------------------------------------------------------------------------
# ETL execution report
# ---------------------------------------------------------------------------


def write_etl_execution_report(
    *,
    started_utc: datetime,
    finished_utc: datetime,
    duration_seconds: float,
    stage_times: dict[str, float],
    input_info: dict[str, Any],
    cleaning_stats: Any | None,
    transform_stats: Any | None,
    validation_result: ValidationResult | None,
    output_info: dict[str, dict[str, Any]],
    report_paths: list[Path],
    status: str,
    error_message: str | None = None,
    error_traceback: str | None = None,
    path: Path | None = None,
) -> Path:
    """Write the Phase 3 ETL execution report."""
    output_path = path or (REPORT_DIR / "etl_execution_report.txt")

    stage_rows = []
    for stage in ("Extract", "Clean", "Transform", "Load", "Validate"):
        if stage in stage_times:
            stage_rows.append(
                {
                    "Stage": stage,
                    "Status": "COMPLETED",
                    "Duration (s)": f"{stage_times[stage]:.3f}",
                }
            )
        else:
            stage_rows.append(
                {
                    "Stage": stage,
                    "Status": "NOT COMPLETED",
                    "Duration (s)": "n/a",
                }
            )
    stage_table = pd.DataFrame(stage_rows)

    output_rows = []
    for item in output_info.values():
        output_rows.append(
            {
                "File": item["relative_path"],
                "Rows": f"{item['rows']:,}",
                "Columns": item["columns"],
                "Size": format_bytes(item["bytes"]),
                "SHA-256": item["sha256"],
            }
        )
    output_table = (
        pd.DataFrame(output_rows)
        if output_rows
        else pd.DataFrame([{"File": "None", "Rows": "n/a", "Columns": "n/a",
                            "Size": "n/a", "SHA-256": "n/a"}])
    )

    report_rows = []
    for report_path in report_paths:
        report_rows.append(
            {
                "Report": report_path.relative_to(PROJECT_ROOT).as_posix(),
                "Exists": "YES" if report_path.exists() else "NO",
                "Size": format_bytes(report_path.stat().st_size)
                if report_path.exists()
                else "n/a",
            }
        )
    report_table = (
        pd.DataFrame(report_rows)
        if report_rows
        else pd.DataFrame([{"Report": "None", "Exists": "NO", "Size": "n/a"}])
    )

    lines = [
        "=" * 78,
        f"{PROJECT_NAME.upper()} - PHASE 3 ETL EXECUTION REPORT",
        "=" * 78,
        f"Execution started (UTC):  {started_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"Execution finished (UTC): {finished_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"Duration:                 {duration_seconds:.3f} seconds",
        f"Final execution status:   {status}",
        "",
        "1. INPUT",
        "-" * 78,
        f"Input file:        {input_info.get('relative_path', 'data/raw/household_power_consumption.txt')}",
        f"File size:         {format_bytes(input_info.get('size', 0))}",
        f"SHA-256:           {input_info.get('sha256', 'n/a')}",
        f"Expected SHA-256:  {input_info.get('expected_sha256', 'n/a')}",
        f"Checksum match:    {'YES' if input_info.get('checksum_matches') else 'NO'}",
        "Input policy:      read-only; the raw file was not modified.",
        "",
        "2. EXECUTION STAGES",
        "-" * 78,
        stage_table.to_string(index=False),
        "",
        "3. RECORD COUNTS",
        "-" * 78,
    ]

    if cleaning_stats is not None:
        lines.extend(
            [
                f"Original records:             {cleaning_stats.raw_rows:,}",
                f"Fully missing records:        {cleaning_stats.original_fully_missing_rows:,}",
                f"Interpolated records:         {cleaning_stats.interpolated_rows:,}",
                f"Unresolved records removed:   {cleaning_stats.removed_rows:,}",
                f"Final cleaned records:        {cleaning_stats.final_rows:,}",
                f"Duplicate records removed:    {cleaning_stats.duplicate_rows_removed:,}",
                f"Outliers removed:             {cleaning_stats.outliers_removed:,}",
            ]
        )
        if transform_stats is not None:
            lines.append(
                f"Measured energy:              "
                f"{transform_stats.non_imputed_energy_kwh:,.6f} kWh"
            )
            lines.append(
                f"Imputed energy:               "
                f"{transform_stats.imputed_energy_kwh:,.6f} kWh"
            )
            lines.append(
                f"Total energy:                 "
                f"{transform_stats.total_energy_kwh:,.6f} kWh"
            )
    else:
        lines.append("Cleaning statistics are unavailable because the pipeline failed.")

    lines.extend(
        [
            "",
            "4. OUTPUT FILES",
            "-" * 78,
            output_table.to_string(index=False),
            "",
            "5. GENERATED REPORTS",
            "-" * 78,
            report_table.to_string(index=False),
            "This execution report: reports/data-engineering/etl_execution_report.txt",
            "",
            "6. ERRORS AND WARNINGS",
            "-" * 78,
        ]
    )

    if error_message:
        lines.append(f"ERROR: {error_message}")
        if error_traceback:
            lines.append("")
            lines.append("Traceback:")
            lines.extend(error_traceback.rstrip().splitlines())
    else:
        lines.append("Errors: None.")

    if validation_result is not None and validation_result.warnings:
        lines.append("")
        lines.append(f"Validation warnings: {len(validation_result.warnings)}")
        for warning in validation_result.warnings:
            lines.append(f"  - {warning.category}: {warning.name}")
    else:
        lines.append("Validation warnings: None.")

    if validation_result is not None and validation_result.failed:
        lines.append("")
        lines.append(f"Validation failures: {len(validation_result.failed)}")
        for failure in validation_result.failed:
            lines.append(f"  - {failure.category}: {failure.name}")
    else:
        lines.append("Validation failures: None.")

    lines.extend(
        [
            "",
            "7. REPRODUCIBILITY",
            "-" * 78,
            "- The pipeline is safe to rerun: derived columns and Parquet files are",
            "  recreated from the immutable raw file.",
            "- The raw SHA-256 checksum is verified before processing.",
            "- Cleaning and transformation are deterministic for the same input.",
            "- Validation includes Pandera schemas and Parquet readback checks.",
            "",
            "8. FINAL STATUS",
            "-" * 78,
            status,
            "=" * 78,
            "",
        ]
    )
    return write_text_report(output_path, lines)


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Run extract, clean, transform, load, validate and report stages."""
    print("=" * 78)
    print(f"{PROJECT_NAME.upper()} - PHASE 3 ETL PIPELINE")
    print("=" * 78)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Raw dataset:  {RAW_PATH}")

    cleaner = _load_module("phase3_clean_dataset", "02_clean_dataset.py")
    transformer = _load_module("phase3_transform_dataset", "03_transform_dataset.py")

    started_utc = datetime.now(UTC)
    pipeline_start = time.perf_counter()
    stage_times: dict[str, float] = {}
    input_info: dict[str, Any] = {
        "relative_path": "data/raw/household_power_consumption.txt",
        "size": 0,
        "sha256": "",
        "expected_sha256": cleaner.EXPECTED_RAW_SHA256,
        "checksum_matches": False,
    }
    cleaning_stats = None
    transform_stats = None
    output_info: dict[str, dict[str, Any]] = {}
    validation_result: ValidationResult | None = None
    report_paths: list[Path] = []
    error_message: str | None = None
    error_traceback: str | None = None
    status = "FAILED"

    try:
        # ------------------------------------------------------------------
        # Extract
        # ------------------------------------------------------------------
        stage_start = time.perf_counter()
        if not RAW_PATH.exists():
            raise FileNotFoundError(
                f"Raw dataset not found at {RAW_PATH}. Place the official UCI "
                "file there and run the pipeline again."
            )
        input_info["size"] = RAW_PATH.stat().st_size
        input_info["sha256"] = cleaner.sha256sum(RAW_PATH)
        input_info["checksum_matches"] = (
            input_info["sha256"] == cleaner.EXPECTED_RAW_SHA256
        )
        if not input_info["checksum_matches"]:
            raise ValueError(
                "Raw dataset checksum does not match the Phase 2 baseline. "
                f"Expected {cleaner.EXPECTED_RAW_SHA256}, got {input_info['sha256']}."
            )
        raw_dataframe = cleaner.load_raw_dataset(RAW_PATH)
        stage_times["Extract"] = time.perf_counter() - stage_start
        print(
            f"Extract:   {len(raw_dataframe):,} rows in "
            f"{stage_times['Extract']:.2f} seconds"
        )

        # ------------------------------------------------------------------
        # Clean
        # ------------------------------------------------------------------
        stage_start = time.perf_counter()
        cleaned, cleaning_stats = cleaner.clean_dataset(raw_dataframe)
        cleaning_stats.raw_file_size = input_info["size"]
        cleaning_stats.raw_sha256 = input_info["sha256"]
        cleaning_stats.checksum_matches = input_info["checksum_matches"]
        cleaning_stats.load_seconds = stage_times["Extract"]
        del raw_dataframe
        cleaning_report = cleaner.write_cleaning_report(cleaning_stats)
        missing_report = cleaner.write_missing_values_report(cleaned)
        report_paths.extend([cleaning_report, missing_report])
        stage_times["Clean"] = time.perf_counter() - stage_start
        print(
            f"Clean:     {len(cleaned):,} rows retained, "
            f"{cleaning_stats.removed_rows:,} unresolved rows removed in "
            f"{stage_times['Clean']:.2f} seconds"
        )

        # ------------------------------------------------------------------
        # Transform
        # ------------------------------------------------------------------
        stage_start = time.perf_counter()
        transformed, aggregations, transform_stats = transformer.transform_dataset(
            cleaned,
            grid_start=cleaning_stats.first_timestamp,
            grid_end=cleaning_stats.last_timestamp,
        )
        del cleaned
        stage_times["Transform"] = time.perf_counter() - stage_start
        print(
            f"Transform: {len(transformed):,} rows, "
            f"{sum(len(frame) for frame in aggregations.values()):,} aggregate "
            f"intervals in {stage_times['Transform']:.2f} seconds"
        )

        # ------------------------------------------------------------------
        # Load
        # ------------------------------------------------------------------
        stage_start = time.perf_counter()
        output_info = transformer.save_outputs(transformed, aggregations)
        transformation_report = transformer.write_transformation_report(
            transform_stats, output_info
        )
        report_paths.append(transformation_report)
        stage_times["Load"] = time.perf_counter() - stage_start
        print(
            f"Load:      {len(output_info)} Parquet files in "
            f"{stage_times['Load']:.2f} seconds"
        )

        # ------------------------------------------------------------------
        # Validate
        # ------------------------------------------------------------------
        stage_start = time.perf_counter()
        validation_result = validate_outputs(
            transformed,
            aggregations,
            cleaning_stats,
            transform_stats,
            output_info=output_info,
            readback=True,
        )
        validation_report = write_validation_report(
            validation_result,
            cleaning_stats,
            transform_stats,
            output_info,
        )
        report_paths.append(validation_report)
        stage_times["Validate"] = time.perf_counter() - stage_start
        print(
            f"Validate:  {len(validation_result.passed):,} passed, "
            f"{len(validation_result.failed):,} failed, "
            f"{len(validation_result.warnings):,} warnings in "
            f"{stage_times['Validate']:.2f} seconds"
        )

        if validation_result.failed:
            status = "FAILED"
        elif validation_result.warnings:
            status = "SUCCESS WITH WARNINGS"
        else:
            status = "SUCCESS"

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        error_traceback = traceback.format_exc()
        status = "FAILED"
        print(f"\nPIPELINE ERROR: {error_message}")
        print(error_traceback)

    finally:
        finished_utc = datetime.now(UTC)
        duration = time.perf_counter() - pipeline_start
        if validation_result is not None and validation_result.failed:
            status = "FAILED"
        etl_report = write_etl_execution_report(
            started_utc=started_utc,
            finished_utc=finished_utc,
            duration_seconds=duration,
            stage_times=stage_times,
            input_info=input_info,
            cleaning_stats=cleaning_stats,
            transform_stats=transform_stats,
            validation_result=validation_result,
            output_info=output_info,
            report_paths=report_paths,
            status=status,
            error_message=error_message,
            error_traceback=error_traceback,
        )
        print(f"Report:    {etl_report.relative_to(PROJECT_ROOT).as_posix()}")

    print("\n" + "=" * 78)
    print(f"PHASE 3 ETL STATUS: {status}")
    print(f"Duration: {duration:.2f} seconds")
    print(f"Reports:  {REPORT_DIR}")
    print("=" * 78)
    return 0 if status in ("SUCCESS", "SUCCESS WITH WARNINGS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
