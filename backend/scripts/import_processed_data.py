r"""Import the Phase 3 cleaned minute dataset into PostgreSQL in batches.

The script streams Parquet row groups with PyArrow so the full file is never
materialised at once.  Inserts use PostgreSQL ``ON CONFLICT (timestamp) DO
NOTHING``, which makes repeated runs idempotent and protects against duplicate
observations.

Example (run from ``backend/``):

    .\.venv\Scripts\Activate.ps1
    python scripts\import_processed_data.py --dry-run
    python scripts\import_processed_data.py

The default source is ``data/processed/household_power_cleaned.parquet`` at the
repository root.  Use ``--limit`` for a quick smoke import.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models.energy import EnergyReading  # noqa: E402

DEFAULT_PARQUET = PROJECT_ROOT / "data" / "processed" / "household_power_cleaned.parquet"

SOURCE_COLUMNS = {
    "timestamp": "timestamp",
    "Global_active_power": "global_active_power",
    "Global_reactive_power": "global_reactive_power",
    "Voltage": "voltage",
    "Global_intensity": "global_intensity",
    "Sub_metering_1": "sub_metering_1",
    "Sub_metering_2": "sub_metering_2",
    "Sub_metering_3": "sub_metering_3",
    "energy_consumption_kwh": "energy_consumption_kwh",
    "is_imputed": "is_imputed",
}

NON_NEGATIVE_COLUMNS = [
    "global_active_power",
    "global_reactive_power",
    "global_intensity",
    "sub_metering_1",
    "sub_metering_2",
    "sub_metering_3",
    "energy_consumption_kwh",
]


class ImportValidationError(RuntimeError):
    """Raised when the source file does not match the expected schema."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import the cleaned Phase 3 minute dataset into the "
            "energy_readings table."
        )
    )
    parser.add_argument(
        "--parquet",
        type=Path,
        default=DEFAULT_PARQUET,
        help=f"Source Parquet file (default: {DEFAULT_PARQUET})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Rows per insert batch (default: IMPORT_BATCH_SIZE or 5000).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Import at most this many matching source rows.",
    )
    parser.add_argument(
        "--start",
        type=datetime.fromisoformat,
        default=None,
        help="Inclusive naive local start timestamp.",
    )
    parser.add_argument(
        "--end",
        type=datetime.fromisoformat,
        default=None,
        help="Inclusive naive local end timestamp.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=None,
        help="Print progress after this many batches (default: 10).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count the source without writing to PostgreSQL.",
    )
    return parser.parse_args()


def _validate_schema(parquet: Path, parquet_file: pq.ParquetFile) -> None:
    if not parquet.is_file():
        raise ImportValidationError(f"Parquet file not found: {parquet}")

    source_names = set(parquet_file.schema_arrow.names)
    missing = [column for column in SOURCE_COLUMNS if column not in source_names]
    if missing:
        raise ImportValidationError(
            "Source Parquet is missing required columns: " + ", ".join(missing)
        )


def _validate_batch(batch: pd.DataFrame) -> pd.DataFrame:
    renamed = batch.rename(columns=SOURCE_COLUMNS).loc[:, list(SOURCE_COLUMNS.values())]
    if renamed.isna().any().any():
        raise ImportValidationError("Source batch contains null values.")

    timestamps = renamed["timestamp"]
    if not pd.api.types.is_datetime64_any_dtype(timestamps):
        raise ImportValidationError("Source timestamp column is not datetime64.")
    if getattr(timestamps.dt, "tz", None) is not None:
        raise ImportValidationError(
            "Source timestamps must be naive local civil time."
        )

    numeric = renamed.drop(columns=["timestamp", "is_imputed"])
    try:
        numeric = numeric.astype("float64")
    except (TypeError, ValueError) as exc:
        raise ImportValidationError(
            "Source batch contains non-numeric measurement values."
        ) from exc
    if numeric.isna().any().any():
        raise ImportValidationError("Source batch contains non-finite measurements.")
    for column in NON_NEGATIVE_COLUMNS:
        if (numeric[column] < 0).any():
            raise ImportValidationError(
                f"Source batch contains negative values in {column}."
            )
    if (numeric["voltage"] <= 0).any():
        raise ImportValidationError("Source batch contains non-positive voltage.")

    renamed["is_imputed"] = renamed["is_imputed"].astype(bool)
    renamed["timestamp"] = [value.to_pydatetime() for value in timestamps]
    return renamed


def _insert_batch(engine: Engine, rows: list[dict[str, Any]]) -> int:
    """Insert one batch as a single multi-row statement.

    The driver does not expose a usable ``rowcount`` for this statement, so
    ``RETURNING id`` is used to count rows that were actually inserted rather
    than skipped by ``ON CONFLICT``.
    """

    statement = (
        insert(EnergyReading.__table__)
        .values(rows)
        .on_conflict_do_nothing(
            index_elements=[EnergyReading.__table__.c.timestamp]
        )
        .returning(EnergyReading.id)
    )
    with engine.begin() as connection:
        result = connection.execute(statement)
        return len(result.scalars().all())


def _count_existing(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                select(func.count()).select_from(EnergyReading)
            ).scalar_one()
        )


def _print_progress(
    *,
    batches: int,
    source_rows: int,
    inserted: int,
    elapsed: float,
) -> None:
    rate = source_rows / elapsed if elapsed > 0 else 0.0
    print(
        f"  batch {batches:>5}  source {source_rows:>9,}  "
        f"inserted {inserted:>9,}  {rate:>9,.0f} rows/s",
        flush=True,
    )


def main() -> int:
    args = _parse_args()
    settings = get_settings()
    batch_size = args.batch_size or settings.import_batch_size
    progress_every = args.progress_every or settings.import_progress_every

    if batch_size < 1:
        print("ERROR: --batch-size must be at least 1.", file=sys.stderr)
        return 2
    if batch_size > 6000:
        print(
            "ERROR: --batch-size must not exceed 6000 "
            "(the multi-row insert parameter limit).",
            file=sys.stderr,
        )
        return 2
    if args.limit is not None and args.limit < 0:
        print("ERROR: --limit must not be negative.", file=sys.stderr)
        return 2
    if args.start and args.end and args.start > args.end:
        print("ERROR: --start must not be after --end.", file=sys.stderr)
        return 2

    parquet = args.parquet.resolve()
    try:
        parquet_file = pq.ParquetFile(parquet)
        _validate_schema(parquet, parquet_file)
    except (OSError, ImportValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    engine = create_engine(
        settings.database_url,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )
    existing_before = 0
    if not args.dry_run:
        try:
            existing_before = _count_existing(engine)
        except Exception as exc:  # noqa: BLE001 - CLI must report a clean error
            print(
                f"ERROR: cannot query energy_readings: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            engine.dispose()
            return 2

    print(f"Source: {parquet}")
    print(f"Rows in Parquet file: {parquet_file.metadata.num_rows:,}")
    print(f"Batch size: {batch_size:,}")
    if args.limit is not None:
        print(f"Row limit: {args.limit:,}")
    if args.start or args.end:
        print(f"Range: {args.start or 'beginning'} .. {args.end or 'end'}")
    if args.dry_run:
        print("Mode: dry run (no database writes)")
    else:
        print(f"Existing energy_readings rows: {existing_before:,}")
    print("Importing...", flush=True)

    started = time.perf_counter()
    source_rows = 0
    inserted = 0
    batches = 0
    stopped_at_limit = False

    try:
        for arrow_batch in parquet_file.iter_batches(
            batch_size=batch_size,
            columns=list(SOURCE_COLUMNS),
        ):
            frame = _validate_batch(arrow_batch.to_pandas())
            if args.start is not None:
                frame = frame.loc[frame["timestamp"] >= args.start]
            if args.end is not None:
                frame = frame.loc[frame["timestamp"] <= args.end]
            if frame.empty:
                continue

            if args.limit is not None:
                remaining = args.limit - source_rows
                if remaining <= 0:
                    stopped_at_limit = True
                    break
                if len(frame) > remaining:
                    frame = frame.iloc[:remaining]
                    stopped_at_limit = True

            rows = frame.to_dict(orient="records")
            source_rows += len(rows)
            batches += 1
            if not args.dry_run:
                inserted += _insert_batch(engine, rows)

            if batches % progress_every == 0:
                _print_progress(
                    batches=batches,
                    source_rows=source_rows,
                    inserted=inserted,
                    elapsed=time.perf_counter() - started,
                )
            if stopped_at_limit:
                break
    except ImportValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        engine.dispose()
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI must report a clean error
        print(
            f"ERROR: database import failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        engine.dispose()
        return 2

    elapsed = time.perf_counter() - started
    if not args.dry_run:
        existing_after = _count_existing(engine)
        engine.dispose()
    else:
        existing_after = existing_before

    print("\nSummary")
    print(f"  Source rows selected : {source_rows:,}")
    print(f"  Batches              : {batches:,}")
    if args.dry_run:
        print("  Database writes      : skipped (dry run)")
    else:
        print(f"  Inserted             : {inserted:,}")
        print(f"  Skipped / duplicates : {source_rows - inserted:,}")
        print(f"  Rows before          : {existing_before:,}")
        print(f"  Rows after           : {existing_after:,}")
    print(f"  Elapsed              : {elapsed:.2f} s")
    print(
        f"  Throughput           : "
        f"{(source_rows / elapsed if elapsed > 0 else 0):,.0f} source rows/s"
    )
    if stopped_at_limit:
        print("  Note                 : stopped after reaching --limit")
    if not args.dry_run and source_rows == 0:
        print("  Note                 : no matching source rows were selected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
