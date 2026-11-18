"""Inspect the UCI household power consumption dataset.

Phase 2 of EcoPulse AI only inspects and describes the raw dataset. This script
does not clean, impute, filter, or otherwise modify any observation. It writes
five reports to ``reports/eda`` at the repository root:

* ``dataset_inspection_report.txt``
* ``missing_values_report.csv``
* ``statistical_summary.csv``
* ``duplicate_records_report.csv``
* ``data_quality_report.txt``

Run from anywhere::

    python data-engineering/src/01_inspect_dataset.py
"""

from __future__ import annotations

import hashlib
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths and dataset metadata
# ---------------------------------------------------------------------------

# ``src`` -> ``data-engineering`` -> repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = PROJECT_ROOT / "data" / "raw" / "household_power_consumption.txt"
REPORT_DIR = PROJECT_ROOT / "reports" / "eda"

PROJECT_NAME = "EcoPulse AI"
DATASET_NAME = "Individual Household Electric Power Consumption"
DATASET_SOURCE = (
    "UCI Machine Learning Repository - "
    "https://archive.ics.uci.edu/dataset/235/"
    "individual+household+electric+power+consumption"
)
DATASET_LICENSE = "CC BY 4.0 (UCI Machine Learning Repository)"
DATASET_DESCRIPTION = (
    "Minute-level electricity measurements from one household in Sceaux, France, "
    "recorded between December 2006 and November 2010."
)

TIMESTAMP_FORMAT = "%d/%m/%Y %H:%M:%S"
RAW_DELIMITER = ";"
RAW_MISSING_VALUE = "?"

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

STATISTIC_LABELS = {
    "count": "Count",
    "mean": "Mean",
    "std": "Standard Deviation",
    "min": "Minimum",
    "25%": "25th Percentile",
    "50%": "Median",
    "75%": "75th Percentile",
    "max": "Maximum",
}


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


def format_bytes(size_bytes: int) -> str:
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


def sha256sum(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a SHA-256 checksum without loading the whole file at once."""
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset(path: Path) -> pd.DataFrame:
    """Load the raw semicolon-delimited file, mapping ``?`` to missing values."""
    return pd.read_csv(
        path,
        sep=RAW_DELIMITER,
        na_values=[RAW_MISSING_VALUE],
        keep_default_na=True,
        low_memory=False,
    )


def convert_numeric_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Convert the seven measurement columns to numeric in a single pass."""
    for column in NUMERIC_COLUMNS:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")
    return dataframe


def build_missing_report(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Build the per-column missing-value table required by Phase 2."""
    total_records = len(dataframe)
    missing_values = dataframe.isna().sum()
    report = pd.DataFrame(
        {
            "Column": dataframe.columns,
            "Total Records": total_records,
            "Missing Values": [int(missing_values[column]) for column in dataframe.columns],
            "Non-Missing Values": [
                int(total_records - missing_values[column]) for column in dataframe.columns
            ],
            "Missing Percentage": [
                round(float(missing_values[column]) / total_records * 100, 4)
                for column in dataframe.columns
            ],
        }
    )
    return report


def build_statistical_summary(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Compute count, mean, standard deviation, quartiles and extremes."""
    summary = dataframe[NUMERIC_COLUMNS].describe(percentiles=[0.25, 0.5, 0.75]).T
    summary = summary.rename(columns=STATISTIC_LABELS)
    summary.index.name = "Column"
    summary["Count"] = summary["Count"].astype(int)
    return summary


def parse_timestamps(dataframe: pd.DataFrame) -> pd.Series:
    """Combine the Date and Time columns into parsed datetime values."""
    combined = dataframe["Date"] + " " + dataframe["Time"]
    return pd.to_datetime(combined, format=TIMESTAMP_FORMAT, errors="coerce")


def build_duplicate_report(dataframe: pd.DataFrame, timestamps: pd.Series) -> pd.DataFrame:
    """Summarise complete-row duplication and timestamp duplication.

    Invalid timestamps are excluded from the duplicate-timestamp count.
    """
    valid_timestamps = timestamps.dropna()
    metrics = [
        ("Total records", len(dataframe)),
        ("Duplicate complete rows", int(dataframe.duplicated().sum())),
        ("Total valid timestamps", int(valid_timestamps.size)),
        ("Duplicate valid timestamps", int(valid_timestamps.duplicated().sum())),
        ("Invalid timestamps", int(timestamps.isna().sum())),
    ]
    return pd.DataFrame(metrics, columns=["Metric", "Value"])


def timestamp_grid_coverage(
    first_timestamp: pd.Timestamp, last_timestamp: pd.Timestamp, valid_count: int
) -> tuple[int, float]:
    """Compare observed valid readings with an ideal one-minute timestamp grid."""
    expected = int((last_timestamp - first_timestamp).total_seconds() // 60) + 1
    coverage = valid_count / expected * 100 if expected else 0.0
    return expected, coverage


def submetering_balance(dataframe: pd.DataFrame) -> tuple[pd.Series, float, float, float]:
    """Compare metered circuit energy with whole-house active energy.

    ``Global_active_power`` is a one-minute average in kW, so dividing by 60
    yields kWh. Sub-metering values are watt-hours for the same minute, so
    dividing by 1000 yields kWh. Missing values are skipped, never treated as
    zero.
    """
    global_kwh = float(dataframe["Global_active_power"].sum() / 60)
    submetering_kwh = dataframe[SUB_METERING_COLUMNS].sum() / 1000
    submetered_total = float(submetering_kwh.sum())
    unmetered_kwh = global_kwh - submetered_total
    share = submetered_total / global_kwh * 100 if global_kwh else 0.0
    return submetering_kwh, global_kwh, unmetered_kwh, share


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------


def write_inspection_report(
    *,
    dataframe: pd.DataFrame,
    missing_report: pd.DataFrame,
    statistical_summary: pd.DataFrame,
    duplicate_report: pd.DataFrame,
    timestamps: pd.Series,
    checksum: str,
) -> Path:
    """Write the human-readable dataset inspection report."""
    report_path = REPORT_DIR / "dataset_inspection_report.txt"
    valid_timestamps = timestamps.dropna()
    first_timestamp = valid_timestamps.min()
    last_timestamp = valid_timestamps.max()
    duration = last_timestamp - first_timestamp
    expected_grid, coverage = timestamp_grid_coverage(
        first_timestamp, last_timestamp, int(valid_timestamps.size)
    )

    total_memory = int(dataframe.memory_usage(deep=True).sum())
    per_column_memory = dataframe.memory_usage(deep=True).drop("Index", errors="ignore")
    missing_cells = int(missing_report["Missing Values"].sum())
    rows_with_missing = int(dataframe.isna().any(axis=1).sum())
    complete_rows = len(dataframe) - rows_with_missing

    lines = [
        "=" * 78,
        f"{PROJECT_NAME.upper()} - PHASE 2 DATASET INSPECTION REPORT",
        "=" * 78,
        f"Generated (UTC): {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        "1. DATASET IDENTIFICATION",
        "-" * 78,
        f"Project name:       {PROJECT_NAME}",
        f"Dataset name:       {DATASET_NAME}",
        f"Dataset source:     {DATASET_SOURCE}",
        f"Licence:            {DATASET_LICENSE}",
        "Local path:         data/raw/household_power_consumption.txt",
        f"File size:          {format_bytes(DATASET_PATH.stat().st_size)}",
        f"SHA-256 checksum:   {checksum}",
        f"Description:        {DATASET_DESCRIPTION}",
        "",
        "2. DATASET DIMENSIONS",
        "-" * 78,
        f"Rows:               {len(dataframe):,}",
        f"Columns:            {dataframe.shape[1]}",
        f"Dataset shape:      {dataframe.shape[0]:,} rows x {dataframe.shape[1]} columns",
        f"Total missing cells: {missing_cells:,}",
        f"Rows with missing:  {rows_with_missing:,}",
        f"Complete rows:      {complete_rows:,}",
        "",
        "3. COLUMN NAMES",
        "-" * 78,
    ]
    lines.extend(
        f"{position:>2}. {column}" for position, column in enumerate(dataframe.columns, start=1)
    )

    lines.extend(
        [
            "",
            "4. DATA TYPES",
            "-" * 78,
            dataframe.dtypes.to_string(),
            "",
            "5. MEMORY USAGE",
            "-" * 78,
            f"Total (deep):       {format_bytes(total_memory)}",
            "Per column:",
            per_column_memory.apply(format_bytes).to_string(),
            "",
            "6. DATE AND TIME RANGE",
            "-" * 78,
            f"Timestamp format:   {TIMESTAMP_FORMAT} (Date column + Time column)",
            f"Invalid timestamps: {int(timestamps.isna().sum()):,}",
            f"Earliest valid:     {first_timestamp}",
            f"Latest valid:       {last_timestamp}",
            f"Date range:         {first_timestamp} to {last_timestamp}",
            f"Observed duration:  {duration} ({duration.total_seconds() / 86_400:,.2f} days)",
            f"Expected 1-min grid: {expected_grid:,} timestamps",
            f"Grid coverage:      {coverage:.4f}% of the ideal one-minute grid",
            "",
            "7. MISSING-VALUE OVERVIEW",
            "-" * 78,
            missing_report.to_string(index=False),
            "",
            "8. DUPLICATE-RECORD OVERVIEW",
            "-" * 78,
            duplicate_report.to_string(index=False),
            "",
            "9. STATISTICAL SUMMARY OVERVIEW",
            "-" * 78,
            statistical_summary.round(4).to_string(),
            "",
            "10. METHOD NOTES",
            "-" * 78,
            f"- Delimiter: semicolon ({RAW_DELIMITER!r}).",
            f"- Missing marker: {RAW_MISSING_VALUE!r} read as NaN; no value was imputed.",
            "- Duplicate timestamps exclude invalid (unparseable) timestamps.",
            "- Statistics use the seven measurement columns and pairwise-valid values.",
            "- The raw file was not modified; no rows, outliers or missing values were removed.",
            "- Global_active_power is a minute-average in kW; /60 approximates kWh per reading.",
            "=" * 78,
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_data_quality_report(
    *,
    dataframe: pd.DataFrame,
    missing_report: pd.DataFrame,
    duplicate_report: pd.DataFrame,
    timestamps: pd.Series,
    global_kwh: float,
    submetering_kwh: pd.Series,
    unmetered_kwh: float,
    submetered_share: float,
) -> Path:
    """Write a data-quality assessment derived from the measured results."""
    report_path = REPORT_DIR / "data_quality_report.txt"
    missing_cells = int(missing_report["Missing Values"].sum())
    rows_with_missing = int(dataframe.isna().any(axis=1).sum())
    rows_all_numeric_missing = int(dataframe[NUMERIC_COLUMNS].isna().all(axis=1).sum())
    rows_partial_numeric_missing = rows_with_missing - rows_all_numeric_missing
    complete_rows = len(dataframe) - rows_with_missing
    complete_share = complete_rows / len(dataframe) * 100

    day_index = timestamps.dt.normalize()
    daily_records = timestamps.notna().groupby(day_index).sum()
    complete_measurement_rows = dataframe[NUMERIC_COLUMNS].notna().all(axis=1)
    daily_complete = complete_measurement_rows.groupby(day_index).sum()
    daily_coverage = daily_complete / daily_records * 100
    days_without_measurement = int((daily_complete == 0).sum())
    days_below_90 = int((daily_coverage < 90).sum())

    valid_timestamps = timestamps.dropna()
    first_timestamp = valid_timestamps.min()
    last_timestamp = valid_timestamps.max()
    expected_grid, coverage = timestamp_grid_coverage(
        first_timestamp, last_timestamp, int(valid_timestamps.size)
    )
    duplicate_valid = int(valid_timestamps.duplicated().sum())
    invalid_timestamps = int(timestamps.isna().sum())
    duplicate_rows = int(
        duplicate_report.loc[
            duplicate_report["Metric"] == "Duplicate complete rows", "Value"
        ].iloc[0]
    )

    affected_missing = missing_report.loc[missing_report["Missing Values"] > 0]
    if affected_missing.empty:
        missing_pattern = "- No measurement column contains missing values."
    else:
        missing_min = int(affected_missing["Missing Values"].min())
        missing_max = int(affected_missing["Missing Values"].max())
        affected_names = ", ".join(affected_missing["Column"])
        if missing_min == missing_max:
            missing_pattern = (
                f"- All {len(affected_missing)} affected columns ({affected_names}) "
                f"contain the same {missing_min:,} missing values "
                f"({affected_missing.iloc[0]['Missing Percentage']:.4f}%)."
            )
        else:
            missing_pattern = (
                f"- {len(affected_missing)} affected columns ({affected_names}) contain "
                f"between {missing_min:,} and {missing_max:,} missing values."
            )

    submetering_lines = "\n".join(
        f"  - {column}: {value:,.2f} kWh" for column, value in submetering_kwh.items()
    )

    lines = [
        "=" * 78,
        f"{PROJECT_NAME.upper()} - PHASE 2 DATA QUALITY REPORT",
        "=" * 78,
        f"Generated (UTC): {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"Dataset: {DATASET_NAME}",
        "Scope: Phase 2 inspection only. No cleaning, imputation or outlier removal.",
        "",
        "1. MISSING-VALUE OBSERVATIONS",
        "-" * 78,
        f"- {missing_cells:,} missing cells were found across "
        f"{len(affected_missing)} of {len(dataframe.columns)} columns.",
        missing_pattern,
        f"- {rows_with_missing:,} rows contain at least one missing value; "
        f"{complete_rows:,} rows ({complete_share:.4f}%) are complete.",
        f"- In {rows_all_numeric_missing:,} of those rows, all seven measurement fields "
        f"are missing simultaneously; {rows_partial_numeric_missing:,} rows show partial "
        "numeric missingness.",
        f"- {days_without_measurement:,} calendar days contain no valid measurement at all; "
        f"{days_below_90:,} days have less than 90% complete measurement coverage.",
        "- The Date and Time columns contain no missing values.",
        "- Missing readings are blocks of unknown consumption, not measured zeros.",
        "",
        "2. DUPLICATE-RECORD OBSERVATIONS",
        "-" * 78,
        f"- Duplicate complete rows: {duplicate_rows:,}.",
        f"- Valid timestamps: {len(valid_timestamps):,}; duplicate valid timestamps: "
        f"{duplicate_valid:,}.",
        f"- Invalid timestamps excluded from duplicate checks: {invalid_timestamps:,}.",
        "",
        "3. INVALID TIMESTAMP OBSERVATIONS",
        "-" * 78,
        f"- {invalid_timestamps:,} Date/Time combinations failed parsing with "
        f"format {TIMESTAMP_FORMAT}.",
        f"- Earliest valid timestamp: {first_timestamp}.",
        f"- Latest valid timestamp: {last_timestamp}.",
        f"- The {len(valid_timestamps):,} valid readings cover {coverage:.4f}% of the "
        f"ideal one-minute grid ({expected_grid:,} slots).",
        "- The raw timestamps carry no UTC offset or timezone name. They are local "
        "wall-clock values for a household in France, so Europe/Paris time must be "
        "assumed and validated explicitly in Phase 3.",
        "- Local-time datasets can contain ambiguous or skipped readings around "
        "daylight-saving transitions; the checks above found "
        f"{duplicate_valid:,} duplicate valid timestamps.",
        "",
        "4. DATA TYPE OBSERVATIONS",
        "-" * 78,
        "- Date and Time are stored as text in the raw file and are combined into "
        "one timestamp during inspection.",
        "- The seven measurement columns are numeric after conversion; '?' values "
        "become NaN rather than zero.",
        "- Units: Global_active_power and Global_reactive_power in kW, Voltage in V, "
        "Global_intensity in A, and the three sub-metering columns in Wh per minute.",
        "- Memory usage (deep) of the loaded frame: "
        f"{format_bytes(int(dataframe.memory_usage(deep=True).sum()))}.",
        "",
        "5. POTENTIAL DATA QUALITY CONCERNS",
        "-" * 78,
        f"- Block missingness: the {rows_all_numeric_missing:,} fully missing rows "
        "would understate daily or monthly energy totals if treated as zero.",
        "- The sub-metering columns cover only selected circuits. Total metered "
        f"sub-metering is {submetering_kwh.sum():,.2f} kWh against "
        f"{global_kwh:,.2f} kWh of whole-house active energy "
        f"({submetered_share:.2f}% coverage), leaving {unmetered_kwh:,.2f} kWh "
        "unattributed to a monitored circuit.",
        "- Sub-metering values of zero are valid idle periods and must remain "
        "distinct from missing readings.",
        "- The one-minute timestamps are local civil time without an offset; "
        "daylight-saving transitions and any downstream UTC conversion need an "
        "explicit policy.",
        "- Measurements are rounded to three decimal places, which limits precision "
        "for very small per-minute values.",
        "- Extreme but plausible values remain in the raw data; Phase 2 does not "
        "remove or cap outliers.",
        "",
        "6. RECOMMENDATIONS FOR THE NEXT ETL PHASE",
        "-" * 78,
        "- Keep data/raw immutable and record the source URL, retrieval date, licence "
        "and SHA-256 checksum in the ingestion manifest.",
        "- Parse Date and Time once, attach the Europe/Paris source timezone, convert "
        "to UTC, and store the original local timestamp alongside it.",
        "- Enforce a unique timestamp constraint and sort chronologically before "
        "loading to PostgreSQL.",
        "- Preserve a missing-value mask; never convert '?' to zero. Decide and "
        "document whether gaps are flagged, imputed or excluded for each downstream "
        "use case.",
        "- Derive energy in kWh explicitly (Global_active_power / 60 per minute, "
        "sub-metering Wh / 1000) and aggregate with missing minutes tracked.",
        "- Validate physical ranges (non-negative power and energy, plausible voltage "
        "and current) and flag violations rather than silently dropping them.",
        "- Keep zero sub-metering readings separate from missing values during "
        "validation and transformation.",
        "- Store curated data as partitioned Parquet for analysis and in PostgreSQL "
        "for application access; both must be reproducible from the raw file.",
        "",
        "Sub-metering energy totals used in this assessment:",
        *submetering_lines.splitlines(),
        f"  - Whole-house active energy: {global_kwh:,.2f} kWh",
        "=" * 78,
        "",
    ]
    report_path.write_text("\n".join(wrap_report_lines(lines)), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the inspection and write all Phase 2 reports."""
    print("=" * 78)
    print(f"{PROJECT_NAME.upper()} - PHASE 2 DATASET INSPECTION")
    print("=" * 78)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Dataset:      {DATASET_PATH}")

    if not DATASET_PATH.exists():
        print("\nERROR: dataset not found.")
        print(f"Expected file: {DATASET_PATH}")
        print(
            "Place the official UCI file 'household_power_consumption.txt' in "
            "data/raw/ and run the script again."
        )
        return 1

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    file_size = DATASET_PATH.stat().st_size
    print(f"File size:    {format_bytes(file_size)}")
    print("\nCalculating SHA-256 checksum...")
    checksum = sha256sum(DATASET_PATH)
    print(f"SHA-256:      {checksum}")

    print("\nLoading dataset (delimiter=';', missing marker='?')...")
    dataframe = load_dataset(DATASET_PATH)
    dataframe = convert_numeric_columns(dataframe)
    print("Dataset loaded. No records were removed or modified.")

    print("\n" + "-" * 78)
    print("DATASET DIMENSIONS")
    print("-" * 78)
    print(f"Rows:    {len(dataframe):,}")
    print(f"Columns: {dataframe.shape[1]}")
    print(f"Shape:   {dataframe.shape}")

    print("\n" + "-" * 78)
    print("COLUMN NAMES")
    print("-" * 78)
    for position, column in enumerate(dataframe.columns, start=1):
        print(f"{position:>2}. {column}")

    print("\n" + "-" * 78)
    print("FIRST 10 RECORDS")
    print("-" * 78)
    print(dataframe.head(10).to_string())

    print("\n" + "-" * 78)
    print("LAST 10 RECORDS")
    print("-" * 78)
    print(dataframe.tail(10).to_string())

    print("\n" + "-" * 78)
    print("DATA TYPES")
    print("-" * 78)
    print(dataframe.dtypes.to_string())

    print("\n" + "-" * 78)
    print("MEMORY USAGE")
    print("-" * 78)
    print(f"Total (deep): {format_bytes(int(dataframe.memory_usage(deep=True).sum()))}")
    for column, size in dataframe.memory_usage(deep=True).drop("Index", errors="ignore").items():
        print(f"  {column:<24} {format_bytes(int(size))}")

    missing_report = build_missing_report(dataframe)
    print("\n" + "-" * 78)
    print("MISSING VALUES BY COLUMN")
    print("-" * 78)
    print(missing_report.to_string(index=False))

    duplicate_count = int(dataframe.duplicated().sum())
    print("\n" + "-" * 78)
    print("DUPLICATE COMPLETE ROWS")
    print("-" * 78)
    print(f"Duplicate complete rows: {duplicate_count:,}")

    print("\n" + "-" * 78)
    print("TIMESTAMP PARSING AND DUPLICATES")
    print("-" * 78)
    timestamps = parse_timestamps(dataframe)
    duplicate_report = build_duplicate_report(dataframe, timestamps)
    print(duplicate_report.to_string(index=False))

    valid_timestamps = timestamps.dropna()
    first_timestamp = valid_timestamps.min()
    last_timestamp = valid_timestamps.max()
    expected_grid, coverage = timestamp_grid_coverage(
        first_timestamp, last_timestamp, int(valid_timestamps.size)
    )
    print(f"Earliest valid timestamp: {first_timestamp}")
    print(f"Latest valid timestamp:   {last_timestamp}")
    print(f"Date range:               {first_timestamp} to {last_timestamp}")
    print(
        f"Observed duration:        {last_timestamp - first_timestamp} "
        f"({(last_timestamp - first_timestamp).total_seconds() / 86_400:,.2f} days)"
    )
    print(f"Expected 1-minute slots:  {expected_grid:,}")
    print(f"Grid coverage:            {coverage:.4f}%")

    statistical_summary = build_statistical_summary(dataframe)
    print("\n" + "-" * 78)
    print("STATISTICAL SUMMARY (NUMERICAL COLUMNS)")
    print("-" * 78)
    print(statistical_summary.round(4).to_string())

    submetering_kwh, global_kwh, unmetered_kwh, submetered_share = submetering_balance(
        dataframe
    )
    print("\n" + "-" * 78)
    print("SUB-METERING ENERGY BALANCE (KWH, VALID READINGS ONLY)")
    print("-" * 78)
    for column, value in submetering_kwh.items():
        print(f"  {column:<24} {value:,.2f} kWh")
    print(f"  {'Sub-metering total':<24} {submetering_kwh.sum():,.2f} kWh")
    print(f"  {'Whole-house total':<24} {global_kwh:,.2f} kWh")
    print(f"  {'Unmetered difference':<24} {unmetered_kwh:,.2f} kWh")
    print(f"  {'Sub-metered share':<24} {submetered_share:.2f}%")

    missing_path = REPORT_DIR / "missing_values_report.csv"
    missing_report.to_csv(missing_path, index=False)
    print(f"\nWrote {missing_path.relative_to(PROJECT_ROOT)}")

    statistical_path = REPORT_DIR / "statistical_summary.csv"
    statistical_summary.to_csv(
        statistical_path, index_label="Column", float_format="%.6f"
    )
    print(f"Wrote {statistical_path.relative_to(PROJECT_ROOT)}")

    duplicate_path = REPORT_DIR / "duplicate_records_report.csv"
    duplicate_report.to_csv(duplicate_path, index=False)
    print(f"Wrote {duplicate_path.relative_to(PROJECT_ROOT)}")

    inspection_path = write_inspection_report(
        dataframe=dataframe,
        missing_report=missing_report,
        statistical_summary=statistical_summary,
        duplicate_report=duplicate_report,
        timestamps=timestamps,
        checksum=checksum,
    )
    print(f"Wrote {inspection_path.relative_to(PROJECT_ROOT)}")

    quality_path = write_data_quality_report(
        dataframe=dataframe,
        missing_report=missing_report,
        duplicate_report=duplicate_report,
        timestamps=timestamps,
        global_kwh=global_kwh,
        submetering_kwh=submetering_kwh,
        unmetered_kwh=unmetered_kwh,
        submetered_share=submetered_share,
    )
    print(f"Wrote {quality_path.relative_to(PROJECT_ROOT)}")

    print("\n" + "=" * 78)
    print("DATASET INSPECTION COMPLETED SUCCESSFULLY")
    print(f"Reports directory: {REPORT_DIR}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
