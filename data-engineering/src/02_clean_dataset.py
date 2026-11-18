"""Clean the UCI household power consumption dataset for EcoPulse AI.

Phase 3 keeps the raw file immutable and applies a deliberately narrow cleaning
policy:

* ``?`` values are read as missing and are never replaced with zero.
* Invalid timestamps and duplicate timestamps are detected and handled
  explicitly.  In the actual dataset both counts are zero.
* Only internal gaps of at most five consecutive minutes are linearly
  interpolated in time.  Longer gaps stay missing.
* Outliers are measured with IQR and domain rules but are never removed or
  capped, because high consumption peaks are genuine observations.
* Rows with unresolved measurements are removed only from the final modelling
  dataset.  The number removed and the number of imputed cells are reported.

Run from any directory::

    python data-engineering/src/02_clean_dataset.py
"""

from __future__ import annotations

import hashlib
import textwrap
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths and dataset contract
# ---------------------------------------------------------------------------

# ``src`` -> ``data-engineering`` -> repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "household_power_consumption.txt"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORT_DIR = PROJECT_ROOT / "reports" / "data-engineering"
CLEANED_PATH = PROCESSED_DIR / "household_power_cleaned.parquet"

RAW_COLUMNS = [
    "Date",
    "Time",
    "Global_active_power",
    "Global_reactive_power",
    "Voltage",
    "Global_intensity",
    "Sub_metering_1",
    "Sub_metering_2",
    "Sub_metering_3",
]
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

RAW_DELIMITER = ";"
RAW_MISSING_VALUE = "?"
TIMESTAMP_FORMAT = "%d/%m/%Y %H:%M:%S"
INTERPOLATION_LIMIT_MINUTES = 5

EXPECTED_RAW_SHA256 = (
    "4259c9d7ece5dbee9ab8d53682baac68d791c864f0f64a52b4043cb3b90894b7"
)

PROJECT_NAME = "EcoPulse AI"
DATASET_NAME = "Individual Household Electric Power Consumption"


# ---------------------------------------------------------------------------
# Formatting and checksum helpers
# ---------------------------------------------------------------------------


def format_bytes(size_bytes: int | float) -> str:
    """Return a human-readable byte size."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:,.2f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def sha256sum(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a SHA-256 checksum without loading the whole file at once."""
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CleaningStats:
    """Auditable counts recorded during cleaning."""

    raw_rows: int = 0
    raw_columns: int = 0
    raw_file_size: int = 0
    raw_sha256: str = ""
    expected_sha256: str = EXPECTED_RAW_SHA256
    checksum_matches: bool = False

    invalid_timestamp_rows: int = 0
    invalid_timestamp_examples: list[str] = field(default_factory=list)
    duplicate_complete_rows: int = 0
    duplicate_timestamp_rows: int = 0
    duplicate_timestamp_groups: int = 0
    duplicate_timestamp_examples: list[str] = field(default_factory=list)
    duplicate_rows_removed: int = 0

    original_missing_cells: int = 0
    original_missing_rows: int = 0
    original_fully_missing_rows: int = 0
    original_partial_missing_rows: int = 0
    original_complete_rows: int = 0
    original_missing_by_column: dict[str, int] = field(default_factory=dict)

    missing_runs: int = 0
    short_gap_runs: int = 0
    short_gap_rows: int = 0
    long_gap_runs: int = 0
    long_gap_rows: int = 0
    longest_gap_rows: int = 0
    longest_gap_start: pd.Timestamp | None = None
    longest_gap_end: pd.Timestamp | None = None
    gap_bucket_table: list[dict[str, Any]] = field(default_factory=list)
    long_gap_examples: list[dict[str, Any]] = field(default_factory=list)

    interpolation_limit_minutes: int = INTERPOLATION_LIMIT_MINUTES
    original_valid_energy_kwh: float = 0.0
    interpolated_cells: int = 0
    interpolated_rows: int = 0
    interpolated_gap_runs: int = 0
    imputed_by_column: dict[str, int] = field(default_factory=dict)
    imputed_energy_kwh: float = 0.0
    interpolation_guard_passed: bool = True

    unresolved_rows: int = 0
    unresolved_cells: int = 0
    unresolved_fully_missing_rows: int = 0
    removed_rows: int = 0
    removed_cells: int = 0
    final_rows: int = 0
    final_missing_cells: int = 0
    final_missing_by_column: dict[str, int] = field(default_factory=dict)

    first_timestamp: pd.Timestamp | None = None
    last_timestamp: pd.Timestamp | None = None
    expected_grid_slots: int = 0
    grid_coverage_percent: float = 0.0

    outlier_table: list[dict[str, Any]] = field(default_factory=list)
    domain_checks: list[dict[str, Any]] = field(default_factory=list)
    submetering_violation_rows: int = 0
    submetering_violation_percent: float = 0.0
    outliers_removed: int = 0

    cleaned_file_size: int = 0
    load_seconds: float = 0.0
    clean_seconds: float = 0.0


@dataclass
class MissingRun:
    """One consecutive block of fully missing measurements."""

    start_position: int
    end_position: int
    start_timestamp: pd.Timestamp
    end_timestamp: pd.Timestamp
    rows: int
    duration_minutes: int

    @property
    def is_short(self) -> bool:
        """Whether the gap is eligible for the five-minute interpolation rule."""
        return (
            self.rows <= INTERPOLATION_LIMIT_MINUTES
            and self.duration_minutes <= INTERPOLATION_LIMIT_MINUTES
        )


# ---------------------------------------------------------------------------
# Loading and cleaning
# ---------------------------------------------------------------------------


def load_raw_dataset(path: Path = RAW_PATH) -> pd.DataFrame:
    """Load the raw semicolon-delimited file and parse its timestamps.

    The raw file is opened read-only.  Numeric conversion is performed here so
    that every downstream component sees the same measurement types.
    """
    if not path.exists():
        raise FileNotFoundError(
            "Raw dataset not found. Expected "
            f"{path}. Place the official UCI file there and run the pipeline again."
        )

    dataframe = pd.read_csv(
        path,
        sep=RAW_DELIMITER,
        na_values=[RAW_MISSING_VALUE],
        keep_default_na=True,
        low_memory=False,
    )

    missing_columns = [column for column in RAW_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(
            "Raw dataset is missing required columns: " + ", ".join(missing_columns)
        )

    for column in NUMERIC_COLUMNS:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    timestamp_text = (
        dataframe["Date"].astype("string").str.strip()
        + " "
        + dataframe["Time"].astype("string").str.strip()
    )
    dataframe[TIMESTAMP_COLUMN] = pd.to_datetime(
        timestamp_text,
        format=TIMESTAMP_FORMAT,
        errors="coerce",
    )
    return dataframe


def _find_missing_runs(
    timestamps: pd.Series,
    fully_missing: pd.Series,
) -> list[MissingRun]:
    """Find consecutive runs of fully missing measurement rows."""
    flags = fully_missing.to_numpy(dtype=bool)
    run_records: list[MissingRun] = []
    start_position: int | None = None

    for position, is_missing in enumerate(flags):
        if is_missing and start_position is None:
            start_position = position
        elif not is_missing and start_position is not None:
            end_position = position - 1
            start_timestamp = pd.Timestamp(timestamps.iloc[start_position])
            end_timestamp = pd.Timestamp(timestamps.iloc[end_position])
            duration_minutes = int(
                (end_timestamp - start_timestamp).total_seconds() // 60
            ) + 1
            run_records.append(
                MissingRun(
                    start_position=start_position,
                    end_position=end_position,
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                    rows=end_position - start_position + 1,
                    duration_minutes=duration_minutes,
                )
            )
            start_position = None

    if start_position is not None:
        end_position = len(flags) - 1
        start_timestamp = pd.Timestamp(timestamps.iloc[start_position])
        end_timestamp = pd.Timestamp(timestamps.iloc[end_position])
        duration_minutes = int(
            (end_timestamp - start_timestamp).total_seconds() // 60
        ) + 1
        run_records.append(
            MissingRun(
                start_position=start_position,
                end_position=end_position,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                rows=end_position - start_position + 1,
                duration_minutes=duration_minutes,
            )
        )

    return run_records


def _gap_bucket_table(runs: list[MissingRun]) -> list[dict[str, Any]]:
    """Summarise gap-run counts by length bucket."""
    buckets = [
        ("1 minute", 1, 1),
        ("2 minutes", 2, 2),
        ("3-5 minutes", 3, 5),
        ("6-10 minutes", 6, 10),
        ("11-30 minutes", 11, 30),
        ("31-60 minutes", 31, 60),
        ("61 minutes-1 day", 61, 1440),
        ("More than 1 day", 1441, 10**9),
    ]
    table: list[dict[str, Any]] = []
    for label, lower, upper in buckets:
        matching = [run for run in runs if lower <= run.rows <= upper]
        table.append(
            {
                "Bucket": label,
                "Runs": len(matching),
                "Rows": sum(run.rows for run in matching),
            }
        )
    return table


def _outlier_summary(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    """Compute IQR-based outlier counts without removing any observation."""
    table: list[dict[str, Any]] = []
    for column in NUMERIC_COLUMNS:
        values = dataframe[column].dropna()
        q1 = float(values.quantile(0.25))
        q3 = float(values.quantile(0.75))
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        extreme_lower = q1 - 3.0 * iqr
        extreme_upper = q3 + 3.0 * iqr
        outlier_mask = (values < lower_bound) | (values > upper_bound)
        extreme_mask = (values < extreme_lower) | (values > extreme_upper)
        table.append(
            {
                "Column": column,
                "Q1": q1,
                "Q3": q3,
                "IQR": iqr,
                "Lower bound": lower_bound,
                "Upper bound": upper_bound,
                "Outliers": int(outlier_mask.sum()),
                "Outlier %": (
                    float(outlier_mask.mean() * 100) if len(values) else 0.0
                ),
                "Extreme outliers": int(extreme_mask.sum()),
                "Minimum": float(values.min()) if len(values) else float("nan"),
                "Maximum": float(values.max()) if len(values) else float("nan"),
            }
        )
    return table


def _domain_checks(dataframe: pd.DataFrame, stats: CleaningStats) -> list[dict[str, Any]]:
    """Validate broad physical ranges and record violations without changing data."""
    checks: list[dict[str, Any]] = []

    def add_check(name: str, violations: int, detail: str) -> None:
        checks.append(
            {
                "Check": name,
                "Violations": int(violations),
                "Status": "PASS" if violations == 0 else "REVIEW",
                "Detail": detail,
            }
        )

    add_check(
        "Global_active_power is non-negative",
        int((dataframe["Global_active_power"] < 0).sum()),
        "A negative whole-house active power reading is physically invalid.",
    )
    add_check(
        "Global_reactive_power is non-negative",
        int((dataframe["Global_reactive_power"] < 0).sum()),
        "A negative reactive power reading is physically invalid.",
    )
    add_check(
        "Voltage is in the plausible range 180-260 V",
        int(((dataframe["Voltage"] < 180) | (dataframe["Voltage"] > 260)).sum()),
        "Broad French low-voltage plausibility band; not a removal rule.",
    )
    add_check(
        "Global_intensity is in the plausible range 0-100 A",
        int(((dataframe["Global_intensity"] < 0) | (dataframe["Global_intensity"] > 100)).sum()),
        "Broad household current plausibility band; not a removal rule.",
    )
    add_check(
        "Global_active_power is at most 20 kW",
        int((dataframe["Global_active_power"] > 20).sum()),
        "A broad upper bound for a single household; not a removal rule.",
    )
    add_check(
        "Sub-metering values are non-negative",
        int((dataframe[SUB_METERING_COLUMNS] < 0).sum().sum()),
        "Sub-metering is reported in Wh per minute and cannot be negative.",
    )

    valid_measurements = dataframe[NUMERIC_COLUMNS].notna().all(axis=1)
    if valid_measurements.any():
        whole_house_wh = (
            dataframe.loc[valid_measurements, "Global_active_power"] * 1000.0 / 60.0
        )
        submetered_wh = dataframe.loc[
            valid_measurements, SUB_METERING_COLUMNS
        ].sum(axis=1)
        violations = int((submetered_wh > whole_house_wh + 1e-6).sum())
        stats.submetering_violation_rows = violations
        stats.submetering_violation_percent = (
            violations / int(valid_measurements.sum()) * 100
        )
        add_check(
            "Sub-metered energy does not exceed whole-house energy",
            violations,
            "Known UCI measurement inconsistency; retained and reported, not corrected.",
        )
    else:
        stats.submetering_violation_rows = 0
        stats.submetering_violation_percent = 0.0

    return checks


def clean_dataset(
    raw_dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, CleaningStats]:
    """Apply the documented Phase 3 cleaning policy.

    Returns the final modelling dataset and a complete audit record.
    """
    start_time = time.perf_counter()
    stats = CleaningStats(
        raw_rows=len(raw_dataframe),
        raw_columns=len(RAW_COLUMNS),
    )

    required = [*RAW_COLUMNS, TIMESTAMP_COLUMN]
    missing_required = [
        column for column in required if column not in raw_dataframe.columns
    ]
    if missing_required:
        raise ValueError(
            "Cleaning requires columns that are absent: " + ", ".join(missing_required)
        )

    # ------------------------------------------------------------------
    # 1. Timestamp validation and duplicate resolution
    # ------------------------------------------------------------------
    invalid_mask = raw_dataframe[TIMESTAMP_COLUMN].isna()
    stats.invalid_timestamp_rows = int(invalid_mask.sum())
    if stats.invalid_timestamp_rows:
        examples = raw_dataframe.loc[invalid_mask, ["Date", "Time"]].head(5)
        stats.invalid_timestamp_examples = [
            f"{row.Date} {row.Time}" for row in examples.itertuples(index=False)
        ]

    dataframe = raw_dataframe.loc[~invalid_mask].copy()

    stats.duplicate_complete_rows = int(dataframe.duplicated().sum())
    duplicate_mask = dataframe[TIMESTAMP_COLUMN].duplicated(keep=False)
    stats.duplicate_timestamp_groups = int(
        dataframe.loc[duplicate_mask, TIMESTAMP_COLUMN].nunique()
    )
    stats.duplicate_timestamp_rows = int(
        dataframe[TIMESTAMP_COLUMN].duplicated(keep="first").sum()
    )
    if stats.duplicate_timestamp_rows:
        examples = (
            dataframe.loc[duplicate_mask, [TIMESTAMP_COLUMN, *NUMERIC_COLUMNS]]
            .sort_values(TIMESTAMP_COLUMN)
            .head(5)
        )
        stats.duplicate_timestamp_examples = [
            f"{format_timestamp(row.timestamp)}" for row in examples.itertuples()
        ]
        # Deterministic policy: keep the first row for each timestamp.  The
        # actual dataset has no duplicate timestamps, so this removes nothing.
        dataframe = (
            dataframe.sort_values(TIMESTAMP_COLUMN, kind="mergesort")
            .drop_duplicates(subset=TIMESTAMP_COLUMN, keep="first")
        )
        stats.duplicate_rows_removed = stats.duplicate_timestamp_rows
    else:
        dataframe = dataframe.sort_values(TIMESTAMP_COLUMN, kind="mergesort")

    dataframe = dataframe.reset_index(drop=True)

    stats.first_timestamp = dataframe[TIMESTAMP_COLUMN].min()
    stats.last_timestamp = dataframe[TIMESTAMP_COLUMN].max()
    if pd.notna(stats.first_timestamp) and pd.notna(stats.last_timestamp):
        stats.expected_grid_slots = int(
            (stats.last_timestamp - stats.first_timestamp).total_seconds() // 60
        ) + 1
        stats.grid_coverage_percent = (
            len(dataframe) / stats.expected_grid_slots * 100
            if stats.expected_grid_slots
            else 0.0
        )

    # ------------------------------------------------------------------
    # 2. Missing-value audit before treatment
    # ------------------------------------------------------------------
    stats.original_missing_by_column = {
        column: int(dataframe[column].isna().sum()) for column in NUMERIC_COLUMNS
    }
    stats.original_missing_cells = int(sum(stats.original_missing_by_column.values()))
    full_missing_mask = dataframe[NUMERIC_COLUMNS].isna().all(axis=1)
    any_missing_mask = dataframe[NUMERIC_COLUMNS].isna().any(axis=1)
    stats.original_missing_rows = int(any_missing_mask.sum())
    stats.original_fully_missing_rows = int(full_missing_mask.sum())
    stats.original_partial_missing_rows = (
        stats.original_missing_rows - stats.original_fully_missing_rows
    )
    stats.original_complete_rows = len(dataframe) - stats.original_missing_rows
    stats.original_valid_energy_kwh = float(
        dataframe["Global_active_power"].sum() / 60.0
    )

    # ------------------------------------------------------------------
    # 3. Consecutive missing intervals
    # ------------------------------------------------------------------
    runs = _find_missing_runs(
        dataframe[TIMESTAMP_COLUMN],
        full_missing_mask,
    )
    stats.missing_runs = len(runs)
    short_runs = [run for run in runs if run.is_short]
    long_runs = [run for run in runs if not run.is_short]
    stats.short_gap_runs = len(short_runs)
    stats.short_gap_rows = sum(run.rows for run in short_runs)
    stats.long_gap_runs = len(long_runs)
    stats.long_gap_rows = sum(run.rows for run in long_runs)
    stats.interpolated_gap_runs = len(short_runs)
    stats.gap_bucket_table = _gap_bucket_table(runs)

    if runs:
        longest = max(runs, key=lambda run: run.rows)
        stats.longest_gap_rows = longest.rows
        stats.longest_gap_start = longest.start_timestamp
        stats.longest_gap_end = longest.end_timestamp
    for run in sorted(long_runs, key=lambda item: item.rows, reverse=True)[:10]:
        stats.long_gap_examples.append(
            {
                "Start": run.start_timestamp,
                "End": run.end_timestamp,
                "Rows": run.rows,
                "Duration (minutes)": run.duration_minutes,
            }
        )

    # ------------------------------------------------------------------
    # 4. Short-gap time interpolation
    # ------------------------------------------------------------------
    measurements = dataframe.set_index(TIMESTAMP_COLUMN)[NUMERIC_COLUMNS]
    missing_mask = measurements.isna()
    interpolated = measurements.interpolate(
        method="time",
        limit=INTERPOLATION_LIMIT_MINUTES,
        limit_area="inside",
    )

    # ``limit`` caps the number of filled values inside a gap, not the gap
    # length: pandas can partially fill a six-minute gap.  Accept interpolated
    # values only on rows that belong to an explicitly measured gap of <=5
    # minutes, and keep every longer gap unresolved.
    short_positions = np.zeros(len(dataframe), dtype=bool)
    long_positions = np.zeros(len(dataframe), dtype=bool)
    for run in short_runs:
        short_positions[run.start_position : run.end_position + 1] = True
    for run in long_runs:
        long_positions[run.start_position : run.end_position + 1] = True

    original_values = measurements.to_numpy(copy=True)
    interpolated_values = interpolated.to_numpy()
    accepted_values = original_values.copy()
    accepted_values[short_positions] = interpolated_values[short_positions]

    imputed_mask = (
        missing_mask.to_numpy()
        & ~np.isnan(accepted_values)
        & short_positions[:, None]
    )

    # Safety guard: a filled row must not belong to a gap longer than the limit.
    filled_positions = imputed_mask.any(axis=1)
    if np.any(filled_positions & long_positions):
        stats.interpolation_guard_passed = False
        raise RuntimeError(
            "Interpolation guard failed: a gap longer than "
            f"{INTERPOLATION_LIMIT_MINUTES} minutes was filled."
        )

    dataframe.loc[:, NUMERIC_COLUMNS] = accepted_values
    dataframe[IMPUTED_COLUMN] = filled_positions

    stats.interpolated_cells = int(imputed_mask.sum())
    stats.interpolated_rows = int(filled_positions.sum())
    stats.imputed_by_column = {
        column: int(imputed_mask[:, position].sum())
        for position, column in enumerate(NUMERIC_COLUMNS)
    }
    filled_short_runs = sum(
        1
        for run in short_runs
        if imputed_mask[run.start_position : run.end_position + 1].any()
    )
    stats.interpolated_gap_runs = filled_short_runs
    if stats.interpolated_rows:
        gap_position = NUMERIC_COLUMNS.index("Global_active_power")
        stats.imputed_energy_kwh = float(
            accepted_values[imputed_mask[:, gap_position], gap_position].sum() / 60.0
        )
    else:
        stats.imputed_energy_kwh = 0.0

    # ------------------------------------------------------------------
    # 5. Unresolved gaps and final modelling dataset
    # ------------------------------------------------------------------
    unresolved_mask = dataframe[NUMERIC_COLUMNS].isna().any(axis=1)
    stats.unresolved_rows = int(unresolved_mask.sum())
    stats.unresolved_cells = int(
        dataframe.loc[unresolved_mask, NUMERIC_COLUMNS].isna().sum().sum()
    )
    stats.unresolved_fully_missing_rows = int(
        dataframe.loc[unresolved_mask, NUMERIC_COLUMNS].isna().all(axis=1).sum()
    )

    final_dataframe = dataframe.loc[~unresolved_mask].copy()
    stats.removed_rows = int(unresolved_mask.sum())
    stats.removed_cells = stats.unresolved_cells
    stats.final_rows = len(final_dataframe)
    stats.final_missing_by_column = {
        column: int(final_dataframe[column].isna().sum()) for column in NUMERIC_COLUMNS
    }
    stats.final_missing_cells = int(sum(stats.final_missing_by_column.values()))

    # ------------------------------------------------------------------
    # 6. Outlier and physical-domain assessment (no removal)
    # ------------------------------------------------------------------
    stats.outlier_table = _outlier_summary(final_dataframe)
    stats.domain_checks = _domain_checks(final_dataframe, stats)
    stats.outliers_removed = 0

    final_dataframe = final_dataframe[
        [TIMESTAMP_COLUMN, *NUMERIC_COLUMNS, IMPUTED_COLUMN]
    ].sort_values(TIMESTAMP_COLUMN, kind="mergesort")
    final_dataframe[IMPUTED_COLUMN] = final_dataframe[IMPUTED_COLUMN].astype(bool)
    final_dataframe = final_dataframe.reset_index(drop=True)

    if final_dataframe[TIMESTAMP_COLUMN].duplicated().any():
        raise RuntimeError("Duplicate timestamps remain after cleaning.")
    if final_dataframe[NUMERIC_COLUMNS].isna().any().any():
        raise RuntimeError("Unresolved measurement values remain in the final dataset.")

    stats.clean_seconds = time.perf_counter() - start_time
    return final_dataframe, stats


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def save_cleaned_dataset(
    dataframe: pd.DataFrame,
    path: Path = CLEANED_PATH,
) -> dict[str, Any]:
    """Write the cleaned minute-level dataset as Parquet and return file details."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_parquet(
        path,
        engine="pyarrow",
        compression="snappy",
        index=False,
    )
    size = path.stat().st_size
    return {
        "Path": path,
        "Relative path": path.relative_to(PROJECT_ROOT).as_posix(),
        "Rows": len(dataframe),
        "Columns": dataframe.shape[1],
        "Bytes": size,
        "SHA-256": sha256sum(path),
    }


def build_missing_values_table(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Build the required after-cleaning missing-value table."""
    total = len(dataframe)
    missing = dataframe.isna().sum()
    return pd.DataFrame(
        {
            "Column": dataframe.columns,
            "Total Records": total,
            "Missing Values": [int(missing[column]) for column in dataframe.columns],
            "Non-Missing Values": [
                int(total - missing[column]) for column in dataframe.columns
            ],
            "Missing Percentage": [
                round(float(missing[column]) / total * 100, 4) if total else 0.0
                for column in dataframe.columns
            ],
        }
    )


def write_missing_values_report(
    dataframe: pd.DataFrame,
    path: Path | None = None,
) -> Path:
    """Write ``missing_values_after_cleaning.csv``."""
    output_path = path or (REPORT_DIR / "missing_values_after_cleaning.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table = build_missing_values_table(dataframe)
    table.to_csv(output_path, index=False)
    return output_path


def write_cleaning_report(
    stats: CleaningStats,
    path: Path | None = None,
) -> Path:
    """Write the human-readable cleaning report from measured counters."""
    output_path = path or (REPORT_DIR / "cleaning_report.txt")
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    missing_before = pd.DataFrame(
        [
            {
                "Column": column,
                "Missing": count,
                "Missing %": (
                    count / stats.raw_rows * 100 if stats.raw_rows else 0.0
                ),
            }
            for column, count in stats.original_missing_by_column.items()
        ]
    )
    imputed_table = pd.DataFrame(
        [
            {"Column": column, "Imputed cells": count}
            for column, count in stats.imputed_by_column.items()
        ]
    )
    gap_table = pd.DataFrame(stats.gap_bucket_table)
    outlier_table = pd.DataFrame(stats.outlier_table)
    domain_table = pd.DataFrame(stats.domain_checks)

    long_gap_lines: list[str] = []
    for item in stats.long_gap_examples:
        long_gap_lines.append(
            f"  - {format_timestamp(item['Start'])} to "
            f"{format_timestamp(item['End'])}: {item['Rows']:,} minutes"
        )
    if not long_gap_lines:
        long_gap_lines.append("  - None.")

    lines = [
        "=" * 78,
        f"{PROJECT_NAME.upper()} - PHASE 3 DATA CLEANING REPORT",
        "=" * 78,
        f"Generated (UTC): {generated}",
        f"Dataset: {DATASET_NAME}",
        "Scope: cleaning only; no machine learning, forecasting or anomaly detection.",
        "",
        "1. INPUT AND INTEGRITY",
        "-" * 78,
        "Raw file:           data/raw/household_power_consumption.txt",
        f"File size:          {format_bytes(stats.raw_file_size)}",
        f"SHA-256:            {stats.raw_sha256}",
        f"Expected SHA-256:   {stats.expected_sha256}",
        f"Checksum match:     {'YES' if stats.checksum_matches else 'NO'}",
        f"Original rows:      {stats.raw_rows:,}",
        f"Original columns:   {stats.raw_columns}",
        "Raw policy:         read-only; the source file was not modified.",
        "",
        "2. TIMESTAMP PARSING AND DUPLICATES",
        "-" * 78,
        f"Timestamp format:   {TIMESTAMP_FORMAT} (Date + Time)",
        f"Invalid timestamps: {stats.invalid_timestamp_rows:,}",
        f"Duplicate complete rows:      {stats.duplicate_complete_rows:,}",
        f"Duplicate timestamp rows:     {stats.duplicate_timestamp_rows:,}",
        f"Duplicate timestamp groups:   {stats.duplicate_timestamp_groups:,}",
        f"Rows removed for duplicates:  {stats.duplicate_rows_removed:,}",
        f"Earliest timestamp:           {format_timestamp(stats.first_timestamp)}",
        f"Latest timestamp:             {format_timestamp(stats.last_timestamp)}",
        f"Expected one-minute slots:    {stats.expected_grid_slots:,}",
        f"Timestamp row coverage:       {stats.grid_coverage_percent:.4f}% "
        "(raw slots present)",
        f"Final modelling coverage:     "
        f"{(stats.final_rows / stats.expected_grid_slots * 100) if stats.expected_grid_slots else 0.0:.4f}% "
        "(valid rows)",
        "Duplicate policy: keep the first chronological occurrence if duplicates",
        "exist. No duplicate timestamp was found in this dataset.",
        "",
        "3. MISSING VALUES BEFORE CLEANING",
        "-" * 78,
        f"Missing measurement cells:    {stats.original_missing_cells:,}",
        f"Rows with any missing value:  {stats.original_missing_rows:,}",
        f"Fully missing rows:           {stats.original_fully_missing_rows:,}",
        f"Partially missing rows:       {stats.original_partial_missing_rows:,}",
        f"Complete rows:                {stats.original_complete_rows:,}",
        "Missingness is block-wise: every affected row is missing all seven",
        "measurements at the same timestamp.",
        "",
        missing_before.round(4).to_string(index=False),
        "",
        "4. CONSECUTIVE MISSING INTERVALS",
        "-" * 78,
        f"Total missing runs:           {stats.missing_runs:,}",
        f"Short runs (<=5 minutes):     {stats.short_gap_runs:,} runs, "
        f"{stats.short_gap_rows:,} rows",
        f"Long runs (>5 minutes):       {stats.long_gap_runs:,} runs, "
        f"{stats.long_gap_rows:,} rows",
        f"Longest run:                  {stats.longest_gap_rows:,} minutes "
        f"({format_timestamp(stats.longest_gap_start)} to "
        f"{format_timestamp(stats.longest_gap_end)})",
        "",
        gap_table.to_string(index=False),
        "",
        "Longest long gaps:",
        *long_gap_lines,
        "",
        "5. SHORT-GAP INTERPOLATION",
        "-" * 78,
        "Method:             time-based linear interpolation on the one-minute index",
        f"Maximum gap:        {stats.interpolation_limit_minutes} consecutive minutes",
        "Fill boundary:      internal gaps only (no forward/backward extrapolation)",
        f"Eligible short runs:{stats.interpolated_gap_runs:>10,}",
        f"Imputed rows:       {stats.interpolated_rows:>10,}",
        f"Imputed cells:      {stats.interpolated_cells:>10,}",
        f"Imputed energy:     {stats.imputed_energy_kwh:>10.6f} kWh",
        f"Safety guard:       {'PASSED' if stats.interpolation_guard_passed else 'FAILED'}",
        "",
        imputed_table.to_string(index=False),
        "",
        "6. UNRESOLVED GAPS AND FINAL DATASET",
        "-" * 78,
        f"Unresolved rows:              {stats.unresolved_rows:,}",
        f"Unresolved cells:             {stats.unresolved_cells:,}",
        f"Fully unresolved rows:        {stats.unresolved_fully_missing_rows:,}",
        f"Rows removed for modelling:   {stats.removed_rows:,}",
        f"Final modelling rows:         {stats.final_rows:,}",
        f"Final missing cells:          {stats.final_missing_cells:,}",
        f"Valid-reading energy:         {stats.original_valid_energy_kwh:,.6f} kWh",
        f"Imputed energy:               {stats.imputed_energy_kwh:,.6f} kWh",
        f"Total including imputed:      "
        f"{stats.original_valid_energy_kwh + stats.imputed_energy_kwh:,.6f} kWh",
        "Final missing values are zero because unresolved rows were excluded",
        "from the modelling dataset. They were not filled or converted to zero.",
        "Rows retained with imputed values carry is_imputed = True.",
        "",
        "7. OUTLIER ANALYSIS (NO REMOVAL)",
        "-" * 78,
        "Method: IQR fences (Q1 - 1.5*IQR, Q3 + 1.5*IQR); extreme fences use 3*IQR.",
        "Outliers are documented and retained. Consumption peaks are real behaviour.",
        "",
        outlier_table.round(4).to_string(index=False),
        "",
        "Interpretation:",
        "- Global_active_power peaks are plausible household demand events, not errors.",
        "- Sub_metering_1 has an IQR of zero because most minutes are idle; every",
        "  nonzero value therefore appears as an IQR outlier. This is a property of",
        "  the circuit, not a reason to delete readings.",
        "- No negative measurement was found and no value was capped or clipped.",
        "",
        "8. PHYSICAL-DOMAIN CHECKS",
        "-" * 78,
        domain_table.to_string(index=False),
        f"Sub-metering above whole-house energy: {stats.submetering_violation_rows:,} "
        f"minutes ({stats.submetering_violation_percent:.4f}%).",
        "This is a known inconsistency in the source data. It is retained and",
        "reported as a warning; no correction was invented.",
        "",
        "9. CLEANING DECISIONS",
        "-" * 78,
        "- The raw file is immutable and its SHA-256 checksum is verified.",
        "- Date and Time are combined into one parsed timestamp; invalid values are",
        "  counted and would be removed explicitly.",
        "- Numeric columns are converted with errors='coerce'; '?' becomes NaN.",
        "- Duplicate complete rows and duplicate timestamps are measured separately.",
        "- Only internal gaps of at most five minutes are interpolated, using the",
        "  time index and all seven measurement columns.",
        "- Long gaps are not interpolated, zero-filled or otherwise fabricated.",
        "- Unresolved rows are removed only for the final modelling dataset, with",
        "  the removal count recorded above.",
        "- Outliers are retained; IQR and domain checks are documentation only.",
        "- Timestamps remain naive local civil time. Phase 3 does not shift them to",
        "  UTC because the source has no offset and a daylight-saving policy has not",
        "  been approved; this is recorded as a validation warning.",
        "- No future-derived feature, lag, rolling target or model input is created.",
        "",
        "10. CLEANING SUMMARY",
        "-" * 78,
        f"Original records:             {stats.raw_rows:,}",
        f"Records after cleaning:       {stats.final_rows:,}",
        f"Records removed:              {stats.removed_rows:,}",
        f"Interpolated cells:           {stats.interpolated_cells:,}",
        f"Unresolved missing cells:     {stats.removed_cells:,}",
        f"Duplicate rows removed:       {stats.duplicate_rows_removed:,}",
        f"Outliers removed:             {stats.outliers_removed:,}",
        f"Cleaning duration:            {stats.clean_seconds:.3f} seconds",
        "Final status:                 SUCCESS",
        "=" * 78,
        "",
    ]

    return write_text_report(output_path, lines)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Load, clean, save and report the dataset from the command line."""
    print("=" * 78)
    print(f"{PROJECT_NAME.upper()} - PHASE 3 DATA CLEANING")
    print("=" * 78)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Raw dataset:  {RAW_PATH}")

    if not RAW_PATH.exists():
        print("\nERROR: raw dataset not found.")
        print(f"Expected: {RAW_PATH}")
        print("Place household_power_consumption.txt in data/raw/ and retry.")
        return 1

    load_start = time.perf_counter()
    raw_dataframe = load_raw_dataset(RAW_PATH)
    load_seconds = time.perf_counter() - load_start
    print(f"Loaded {len(raw_dataframe):,} raw rows in {load_seconds:.2f} seconds.")

    cleaned, stats = clean_dataset(raw_dataframe)
    stats.load_seconds = load_seconds
    stats.raw_file_size = RAW_PATH.stat().st_size
    stats.raw_sha256 = sha256sum(RAW_PATH)
    stats.checksum_matches = stats.raw_sha256 == stats.expected_sha256
    if not stats.checksum_matches:
        print("\nERROR: raw dataset checksum does not match the Phase 2 baseline.")
        print(f"Expected: {stats.expected_sha256}")
        print(f"Actual:   {stats.raw_sha256}")
        return 1

    output = save_cleaned_dataset(cleaned)
    stats.cleaned_file_size = output["Bytes"]
    report_path = write_cleaning_report(stats)
    missing_path = write_missing_values_report(cleaned)

    print(f"\nOriginal rows:                 {stats.raw_rows:,}")
    print(f"Fully missing rows:            {stats.original_fully_missing_rows:,}")
    print(
        f"Interpolated rows:             {stats.interpolated_rows:,} "
        f"({stats.interpolated_cells:,} cells)"
    )
    print(f"Unresolved rows removed:       {stats.removed_rows:,}")
    print(f"Final modelling rows:          {stats.final_rows:,}")
    print(f"Final missing cells:           {stats.final_missing_cells:,}")
    print(f"Outlier cells retained:        "
          f"{sum(item['Outliers'] for item in stats.outlier_table):,}")
    print(f"\nWrote {output['Relative path']} "
          f"({format_bytes(output['Bytes'])})")
    print(f"Wrote {report_path.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"Wrote {missing_path.relative_to(PROJECT_ROOT).as_posix()}")
    print("\nDATA CLEANING COMPLETED SUCCESSFULLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
