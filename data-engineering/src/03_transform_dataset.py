"""Transform the cleaned EcoPulse AI dataset into analysis-ready features.

The transformation layer adds deterministic calendar features and per-minute
energy in kWh, then builds hourly, daily and monthly aggregates.  Every
aggregate records how many one-minute slots were expected, how many were valid
and how many were imputed, so an incomplete interval is never presented as a
complete measurement.

Run from any directory after cleaning::

    python data-engineering/src/03_transform_dataset.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Paths and shared schema
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "household_power_consumption.txt"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORT_DIR = PROJECT_ROOT / "reports" / "data-engineering"
CLEANED_PATH = PROCESSED_DIR / "household_power_cleaned.parquet"

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
DERIVED_COLUMNS = [*DATETIME_COLUMNS, ENERGY_COLUMN]

AGGREGATION_FREQUENCIES = {
    "hourly": "h",
    "daily": "D",
    "monthly": "MS",
}
AGGREGATION_FILENAMES = {
    "minute": "household_power_cleaned.parquet",
    "hourly": "household_power_hourly.parquet",
    "daily": "household_power_daily.parquet",
    "monthly": "household_power_monthly.parquet",
}

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
# Transformation
# ---------------------------------------------------------------------------


@dataclass
class TransformStats:
    """Counts and checks recorded by the transformation stage."""

    input_rows: int = 0
    input_columns: int = 0
    output_rows: int = 0
    output_columns: int = 0
    first_timestamp: pd.Timestamp | None = None
    last_timestamp: pd.Timestamp | None = None
    imputed_rows: int = 0
    imputed_energy_kwh: float = 0.0
    non_imputed_energy_kwh: float = 0.0
    total_energy_kwh: float = 0.0
    total_submetering_kwh: float = 0.0
    submetered_share_percent: float = 0.0
    grid_expected_slots: int = 0
    minute_features: list[dict[str, str]] = field(default_factory=list)
    aggregation_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    transform_seconds: float = 0.0


def _require_columns(dataframe: pd.DataFrame, required: list[str], label: str) -> None:
    """Raise a clear error when an input dataset is incomplete."""
    missing = [column for column in required if column not in dataframe.columns]
    if missing:
        raise ValueError(
            f"{label} is missing required columns: " + ", ".join(missing)
        )


def add_datetime_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add calendar features derived only from the timestamp itself."""
    timestamp = dataframe[TIMESTAMP_COLUMN]
    if not pd.api.types.is_datetime64_any_dtype(timestamp):
        raise TypeError("The timestamp column must be datetime64 before transformation.")
    if timestamp.isna().any():
        raise ValueError("The timestamp column contains invalid values.")

    dataframe["year"] = timestamp.dt.year.astype("int16")
    dataframe["month"] = timestamp.dt.month.astype("int8")
    dataframe["day"] = timestamp.dt.day.astype("int8")
    dataframe["hour"] = timestamp.dt.hour.astype("int8")
    dataframe["minute"] = timestamp.dt.minute.astype("int8")
    dataframe["day_of_week"] = timestamp.dt.dayofweek.astype("int8")
    dataframe["day_name"] = timestamp.dt.day_name()
    dataframe["is_weekend"] = dataframe["day_of_week"] >= 5
    return dataframe


def add_energy_feature(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add per-minute energy in kWh without filling or zeroing missing values.

    ``Global_active_power`` is a one-minute average in kW.  Dividing by 60
    gives the approximate energy contribution of that valid minute in kWh.
    """
    dataframe[ENERGY_COLUMN] = dataframe["Global_active_power"] / 60.0
    return dataframe


def _expected_minute_counts(
    start: pd.Timestamp,
    end: pd.Timestamp,
    frequency: str,
) -> pd.Series:
    """Count expected one-minute slots per calendar interval over the full range.

    The expected count is based on the source's complete one-minute grid, not
    on the rows that survived cleaning.  This is what exposes fully missing
    days and long gaps in the aggregates.
    """
    grid = pd.Series(
        1,
        index=pd.date_range(start=start, end=end, freq="min"),
        dtype="int8",
        name="expected_observation_count",
    )
    return grid.resample(frequency, label="left", closed="left").sum()


def _build_aggregation(
    indexed: pd.DataFrame,
    frequency: str,
    expected_counts: pd.Series,
) -> pd.DataFrame:
    """Build one gap-aware aggregation from a timestamp-indexed minute frame."""
    grouped = indexed.resample(frequency, label="left", closed="left")

    valid_counts = grouped[ENERGY_COLUMN].count().rename("valid_observation_count")
    imputed_counts = (
        grouped[IMPUTED_COLUMN].sum().rename("imputed_observation_count")
    )
    aggregation = pd.DataFrame(
        {
            "valid_observation_count": valid_counts,
            "imputed_observation_count": imputed_counts,
            "mean_global_active_power_kw": grouped["Global_active_power"].mean(),
            "max_global_active_power_kw": grouped["Global_active_power"].max(),
            "min_global_active_power_kw": grouped["Global_active_power"].min(),
            "total_energy_consumption_kwh": grouped[ENERGY_COLUMN].sum(
                min_count=1
            ),
            "mean_global_reactive_power_kw": grouped[
                "Global_reactive_power"
            ].mean(),
            "mean_voltage_v": grouped["Voltage"].mean(),
            "mean_global_intensity_a": grouped["Global_intensity"].mean(),
            "mean_sub_metering_1_wh": grouped["Sub_metering_1"].mean(),
            "mean_sub_metering_2_wh": grouped["Sub_metering_2"].mean(),
            "mean_sub_metering_3_wh": grouped["Sub_metering_3"].mean(),
            "total_sub_metering_1_kwh": grouped["Sub_metering_1"].sum(
                min_count=1
            )
            / 1000.0,
            "total_sub_metering_2_kwh": grouped["Sub_metering_2"].sum(
                min_count=1
            )
            / 1000.0,
            "total_sub_metering_3_kwh": grouped["Sub_metering_3"].sum(
                min_count=1
            )
            / 1000.0,
        }
    )

    aggregation = expected_counts.to_frame().join(aggregation, how="left")
    aggregation["valid_observation_count"] = (
        aggregation["valid_observation_count"].fillna(0).astype("int64")
    )
    aggregation["imputed_observation_count"] = (
        aggregation["imputed_observation_count"].fillna(0).astype("int64")
    )
    aggregation["expected_observation_count"] = aggregation[
        "expected_observation_count"
    ].astype("int64")
    aggregation["coverage_percentage"] = (
        aggregation["valid_observation_count"]
        / aggregation["expected_observation_count"]
        * 100.0
    )
    aggregation["is_complete"] = (
        aggregation["valid_observation_count"]
        == aggregation["expected_observation_count"]
    )
    aggregation["total_sub_metering_kwh"] = aggregation[
        [
            "total_sub_metering_1_kwh",
            "total_sub_metering_2_kwh",
            "total_sub_metering_3_kwh",
        ]
    ].sum(axis=1, min_count=1)
    aggregation.index.name = "period_start"
    aggregation = aggregation.reset_index()

    ordered_columns = [
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
    return aggregation[ordered_columns].sort_values("period_start").reset_index(
        drop=True
    )


def _aggregation_summary(name: str, aggregation: pd.DataFrame) -> dict[str, Any]:
    """Collect report-ready facts about one aggregation level."""
    valid = aggregation["valid_observation_count"]
    expected = aggregation["expected_observation_count"]
    total_energy = aggregation["total_energy_consumption_kwh"].sum(min_count=1)
    return {
        "name": name,
        "rows": len(aggregation),
        "complete_intervals": int(aggregation["is_complete"].sum()),
        "incomplete_intervals": int((~aggregation["is_complete"]).sum()),
        "empty_intervals": int((valid == 0).sum()),
        "expected_minutes": int(expected.sum()),
        "valid_minutes": int(valid.sum()),
        "imputed_minutes": int(aggregation["imputed_observation_count"].sum()),
        "total_energy_kwh": float(total_energy) if pd.notna(total_energy) else 0.0,
        "first_period": aggregation["period_start"].min(),
        "last_period": aggregation["period_start"].max(),
        "min_coverage": float(aggregation["coverage_percentage"].min()),
        "mean_coverage": float(aggregation["coverage_percentage"].mean()),
    }


def transform_dataset(
    cleaned_dataframe: pd.DataFrame,
    grid_start: pd.Timestamp | None = None,
    grid_end: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], TransformStats]:
    """Create features, energy and hourly/daily/monthly aggregates.

    The function is idempotent: derived columns are removed before being
    recreated, so a transformed Parquet file can safely be transformed again.
    """
    start_time = time.perf_counter()
    required = [TIMESTAMP_COLUMN, *NUMERIC_COLUMNS, IMPUTED_COLUMN]
    _require_columns(cleaned_dataframe, required, "Cleaned dataset")

    dataframe = cleaned_dataframe.drop(
        columns=[column for column in DERIVED_COLUMNS if column in cleaned_dataframe],
        errors="ignore",
    ).copy()
    dataframe = dataframe.sort_values(TIMESTAMP_COLUMN, kind="mergesort").reset_index(
        drop=True
    )

    if dataframe[TIMESTAMP_COLUMN].duplicated().any():
        raise ValueError("The cleaned dataset contains duplicate timestamps.")
    if dataframe[NUMERIC_COLUMNS].isna().any().any():
        raise ValueError(
            "The cleaned dataset contains unresolved measurement values; "
            "resolve or exclude them before transformation."
        )

    dataframe = add_datetime_features(dataframe)
    dataframe = add_energy_feature(dataframe)

    minute_columns = [
        TIMESTAMP_COLUMN,
        *DATETIME_COLUMNS,
        *NUMERIC_COLUMNS,
        ENERGY_COLUMN,
        IMPUTED_COLUMN,
    ]
    dataframe = dataframe[minute_columns]

    if grid_start is None:
        grid_start = dataframe[TIMESTAMP_COLUMN].min()
    if grid_end is None:
        grid_end = dataframe[TIMESTAMP_COLUMN].max()
    grid_start = pd.Timestamp(grid_start)
    grid_end = pd.Timestamp(grid_end)

    indexed = dataframe.set_index(TIMESTAMP_COLUMN, drop=True)
    aggregations: dict[str, pd.DataFrame] = {}
    for name, frequency in AGGREGATION_FREQUENCIES.items():
        expected_counts = _expected_minute_counts(grid_start, grid_end, frequency)
        aggregations[name] = _build_aggregation(
            indexed,
            frequency,
            expected_counts,
        )

    total_energy = float(dataframe[ENERGY_COLUMN].sum())
    total_submetering = float(
        dataframe[SUB_METERING_COLUMNS].sum().sum() / 1000.0
    )
    imputed_energy = float(
        dataframe.loc[dataframe[IMPUTED_COLUMN], ENERGY_COLUMN].sum()
    )
    non_imputed_energy = float(
        dataframe.loc[~dataframe[IMPUTED_COLUMN], ENERGY_COLUMN].sum()
    )
    submetered_share = (
        total_submetering / total_energy * 100.0 if total_energy else 0.0
    )

    minute_features = [
        {"Feature": "year", "Type": "int16", "Source": "timestamp.dt.year"},
        {"Feature": "month", "Type": "int8", "Source": "timestamp.dt.month"},
        {"Feature": "day", "Type": "int8", "Source": "timestamp.dt.day"},
        {"Feature": "hour", "Type": "int8", "Source": "timestamp.dt.hour"},
        {"Feature": "minute", "Type": "int8", "Source": "timestamp.dt.minute"},
        {
            "Feature": "day_of_week",
            "Type": "int8",
            "Source": "timestamp.dt.dayofweek (Monday=0)",
        },
        {"Feature": "day_name", "Type": "string", "Source": "timestamp.dt.day_name()"},
        {
            "Feature": "is_weekend",
            "Type": "bool",
            "Source": "day_of_week >= 5",
        },
        {
            "Feature": ENERGY_COLUMN,
            "Type": "float64",
            "Source": "Global_active_power / 60",
        },
    ]

    stats = TransformStats(
        input_rows=len(cleaned_dataframe),
        input_columns=cleaned_dataframe.shape[1],
        output_rows=len(dataframe),
        output_columns=dataframe.shape[1],
        first_timestamp=dataframe[TIMESTAMP_COLUMN].min(),
        last_timestamp=dataframe[TIMESTAMP_COLUMN].max(),
        imputed_rows=int(dataframe[IMPUTED_COLUMN].sum()),
        imputed_energy_kwh=imputed_energy,
        non_imputed_energy_kwh=non_imputed_energy,
        total_energy_kwh=total_energy,
        total_submetering_kwh=total_submetering,
        submetered_share_percent=submetered_share,
        grid_expected_slots=int(
            (grid_end - grid_start).total_seconds() // 60
        )
        + 1,
        minute_features=minute_features,
        aggregation_stats={
            name: _aggregation_summary(name, aggregation)
            for name, aggregation in aggregations.items()
        },
        transform_seconds=time.perf_counter() - start_time,
    )
    return dataframe, aggregations, stats


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def save_outputs(
    transformed: pd.DataFrame,
    aggregations: dict[str, pd.DataFrame],
    output_dir: Path = PROCESSED_DIR,
) -> dict[str, dict[str, Any]]:
    """Write the four Phase 3 Parquet datasets and return file details."""
    output_dir.mkdir(parents=True, exist_ok=True)
    datasets = {"minute": transformed, **aggregations}
    output_info: dict[str, dict[str, Any]] = {}

    for name, dataframe in datasets.items():
        path = output_dir / AGGREGATION_FILENAMES[name]
        dataframe.to_parquet(
            path,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        output_info[name] = {
            "name": name,
            "path": path,
            "relative_path": path.relative_to(PROJECT_ROOT).as_posix(),
            "rows": len(dataframe),
            "columns": dataframe.shape[1],
            "bytes": path.stat().st_size,
            "sha256": sha256sum(path),
        }
    return output_info


def write_transformation_report(
    stats: TransformStats,
    output_info: dict[str, dict[str, Any]],
    path: Path | None = None,
) -> Path:
    """Write the transformation report from measured results."""
    output_path = path or (REPORT_DIR / "transformation_report.txt")
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    feature_table = pd.DataFrame(stats.minute_features)
    aggregation_rows = []
    for name in ("hourly", "daily", "monthly"):
        item = stats.aggregation_stats[name]
        aggregation_rows.append(
            {
                "Level": name,
                "Intervals": item["rows"],
                "Complete": item["complete_intervals"],
                "Incomplete": item["incomplete_intervals"],
                "Empty": item["empty_intervals"],
                "Expected minutes": item["expected_minutes"],
                "Valid minutes": item["valid_minutes"],
                "Imputed minutes": item["imputed_minutes"],
                "Total kWh": item["total_energy_kwh"],
                "Min coverage %": item["min_coverage"],
            }
        )
    aggregation_table = pd.DataFrame(aggregation_rows)

    output_rows = [
        {
            "File": item["relative_path"],
            "Rows": item["rows"],
            "Columns": item["columns"],
            "Size": format_bytes(item["bytes"]),
        }
        for item in output_info.values()
    ]
    output_table = pd.DataFrame(output_rows)

    lines = [
        "=" * 78,
        f"{PROJECT_NAME.upper()} - PHASE 3 DATA TRANSFORMATION REPORT",
        "=" * 78,
        f"Generated (UTC): {generated}",
        f"Dataset: {DATASET_NAME}",
        "Scope: feature engineering and aggregation only; no model was trained.",
        "",
        "1. INPUT",
        "-" * 78,
        "Input file:          data/processed/household_power_cleaned.parquet",
        f"Input rows:          {stats.input_rows:,}",
        f"Input columns:       {stats.input_columns}",
        "Input policy:        unresolved rows already excluded by the cleaning stage",
        f"First timestamp:     {format_timestamp(stats.first_timestamp)}",
        f"Last timestamp:      {format_timestamp(stats.last_timestamp)}",
        f"Expected minute slots in range: {stats.grid_expected_slots:,}",
        "",
        "2. NEW FEATURES",
        "-" * 78,
        "Datetime features are computed from the timestamp only. No lag, rolling",
        "window, future observation, target encoding or other leakage-prone feature",
        "is created in Phase 3.",
        "",
        feature_table.to_string(index=False),
        "",
        "3. DATETIME TRANSFORMATIONS",
        "-" * 78,
        "- Date and Time were parsed in the cleaning stage into one naive local",
        "  timestamp with format %d/%m/%Y %H:%M:%S.",
        "- year, month, day, hour and minute describe the local wall-clock value.",
        "- day_of_week uses Monday=0 and Sunday=6; day_name is the English name.",
        "- is_weekend is true for Saturday and Sunday.",
        "- The dataset is sorted chronologically by timestamp.",
        "- Timestamps remain naive local civil time. No UTC offset is invented and",
        "  no daylight-saving shift is applied in Phase 3.",
        "",
        "4. ENERGY CALCULATION",
        "-" * 78,
        f"Formula:             {ENERGY_COLUMN} = Global_active_power / 60",
        "Input unit:          Global_active_power is a one-minute average in kW",
        "Output unit:         kWh for that valid minute",
        "Missing readings:    energy is NaN; it is never replaced by zero",
        f"Total energy:        {stats.total_energy_kwh:,.6f} kWh",
        f"Valid-reading energy: {stats.non_imputed_energy_kwh:,.6f} kWh "
        f"(measured minutes only)",
        f"Imputed energy:      {stats.imputed_energy_kwh:,.6f} kWh "
        f"({stats.imputed_rows:,} rows flagged)",
        "Continuity:          total = valid-reading energy + imputed energy;",
        "                     the valid-reading total must match Phase 2.",
        f"Sub-metered total:   {stats.total_submetering_kwh:,.6f} kWh "
        f"({stats.submetered_share_percent:.2f}% of whole-house energy)",
        "Sub-metering units:  Wh per minute divided by 1000 for kWh",
        "",
        "5. AGGREGATION INFORMATION",
        "-" * 78,
        "Frequency labels: hourly=h, daily=D, monthly=MS (month start).",
        "Each aggregate includes every expected interval across the full source",
        "range, including intervals with no valid reading. Expected counts come",
        "from the complete one-minute grid, not from surviving rows.",
        "",
        aggregation_table.round(4).to_string(index=False),
        "",
        "Per-level details:",
    ]

    for name in ("hourly", "daily", "monthly"):
        item = stats.aggregation_stats[name]
        lines.extend(
            [
                f"  {name.upper()}",
                f"    Intervals:            {item['rows']:,}",
                f"    Complete intervals:   {item['complete_intervals']:,}",
                f"    Incomplete intervals: {item['incomplete_intervals']:,}",
                f"    Empty intervals:      {item['empty_intervals']:,}",
                f"    Expected minutes:     {item['expected_minutes']:,}",
                f"    Valid minutes:        {item['valid_minutes']:,}",
                f"    Imputed minutes:      {item['imputed_minutes']:,}",
                f"    Total energy:         {item['total_energy_kwh']:,.6f} kWh",
                f"    First period:         {format_timestamp(item['first_period'])}",
                f"    Last period:          {format_timestamp(item['last_period'])}",
                f"    Minimum coverage:     {item['min_coverage']:.4f}%",
                f"    Mean coverage:        {item['mean_coverage']:.4f}%",
                "",
            ]
        )

    lines.extend(
        [
            "Important interpretation:",
            "- A partial interval is a sum of its valid minutes only. Its",
            "  total_energy_consumption_kwh is not a complete-interval total.",
            "- is_complete is true only when valid_observation_count equals",
            "  expected_observation_count.",
            "- Empty intervals carry NaN energy totals, not zero.",
            "",
            "6. OUTPUT FILES",
            "-" * 78,
            output_table.to_string(index=False),
            "",
            "Output details:",
        ]
    )
    for item in output_info.values():
        lines.append(
            f"  - {item['relative_path']}: {format_bytes(item['bytes'])}, "
            f"SHA-256 {item['sha256']}"
        )

    lines.extend(
        [
            "",
            "7. REPRODUCIBILITY",
            "-" * 78,
            "- The transformation is deterministic for the same cleaned input and range.",
            "- Derived columns are removed and recreated, so rerunning is safe.",
            "- Parquet files use PyArrow with Snappy compression and no DataFrame index.",
            f"Transformation duration: {stats.transform_seconds:.3f} seconds",
            "Final status: SUCCESS",
            "=" * 78,
            "",
        ]
    )

    return write_text_report(output_path, lines)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


def _load_cleaning_module() -> Any:
    """Load the numbered cleaning script as a module for standalone execution."""
    cleaning_path = Path(__file__).with_name("02_clean_dataset.py")
    spec = importlib.util.spec_from_file_location("phase3_clean_dataset", cleaning_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load cleaning module from {cleaning_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["phase3_clean_dataset"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    """Transform the cleaned dataset and write all Phase 3 output datasets."""
    print("=" * 78)
    print(f"{PROJECT_NAME.upper()} - PHASE 3 DATA TRANSFORMATION")
    print("=" * 78)
    print(f"Project root: {PROJECT_ROOT}")

    if not CLEANED_PATH.exists():
        print("Cleaned dataset not found; running the cleaning stage first...")
        cleaner = _load_cleaning_module()
        result = cleaner.main()
        if result != 0 or not CLEANED_PATH.exists():
            print("\nERROR: cleaning stage did not produce the cleaned dataset.")
            return 1

    cleaned = pd.read_parquet(CLEANED_PATH)
    cleaned["timestamp"] = pd.to_datetime(cleaned["timestamp"])
    grid_start = cleaned["timestamp"].min()
    grid_end = cleaned["timestamp"].max()

    transformed, aggregations, stats = transform_dataset(
        cleaned,
        grid_start=grid_start,
        grid_end=grid_end,
    )
    output_info = save_outputs(transformed, aggregations)
    report_path = write_transformation_report(stats, output_info)

    print(f"Input rows:        {stats.input_rows:,}")
    print(f"Output rows:       {stats.output_rows:,}")
    print(f"Total energy:      {stats.total_energy_kwh:,.6f} kWh")
    print(f"Imputed rows:      {stats.imputed_rows:,}")
    for name in ("hourly", "daily", "monthly"):
        item = stats.aggregation_stats[name]
        print(
            f"{name.capitalize():<8} intervals: {item['rows']:>7,} "
            f"(complete {item['complete_intervals']:,}, "
            f"incomplete {item['incomplete_intervals']:,})"
        )
    for item in output_info.values():
        print(f"Wrote {item['relative_path']} ({format_bytes(item['bytes'])})")
    print(f"Wrote {report_path.relative_to(PROJECT_ROOT).as_posix()}")
    print("\nDATA TRANSFORMATION COMPLETED SUCCESSFULLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
