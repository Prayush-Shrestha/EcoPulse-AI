"""Validation tests for the parquet import script (no database writes)."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.import_processed_data import (
    SOURCE_COLUMNS,
    ImportValidationError,
    _validate_batch,
)


def _valid_batch() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2010-11-26T21:00:00"),
                pd.Timestamp("2010-11-26T21:01:00"),
            ],
            "Global_active_power": [1.2, 0.9],
            "Global_reactive_power": [0.1, 0.1],
            "Voltage": [240.1, 240.0],
            "Global_intensity": [5.0, 3.8],
            "Sub_metering_1": [0.0, 0.0],
            "Sub_metering_2": [0.0, 1.0],
            "Sub_metering_3": [2.0, 1.0],
            "energy_consumption_kwh": [0.02, 0.015],
            "is_imputed": [False, False],
        }
    )


def test_valid_batch_is_renamed_to_database_columns() -> None:
    validated = _validate_batch(_valid_batch())

    assert list(validated.columns) == list(SOURCE_COLUMNS.values())
    assert validated["timestamp"].tolist() == [
        pd.Timestamp("2010-11-26T21:00:00").to_pydatetime(),
        pd.Timestamp("2010-11-26T21:01:00").to_pydatetime(),
    ]
    assert validated["is_imputed"].dtype == bool


def test_negative_measurements_are_rejected() -> None:
    batch = _valid_batch()
    batch.loc[0, "Global_active_power"] = -0.1

    with pytest.raises(ImportValidationError, match="negative"):
        _validate_batch(batch)


def test_null_values_are_rejected() -> None:
    batch = _valid_batch()
    batch.loc[1, "Voltage"] = None

    with pytest.raises(ImportValidationError, match="null"):
        _validate_batch(batch)


def test_non_numeric_values_are_rejected() -> None:
    batch = _valid_batch()
    batch["Global_active_power"] = ["not-a-number", "still-not-a-number"]

    with pytest.raises(ImportValidationError, match="non-numeric"):
        _validate_batch(batch)


def test_timezone_aware_timestamps_are_rejected() -> None:
    batch = _valid_batch()
    batch["timestamp"] = [
        pd.Timestamp("2010-11-26T21:00:00", tz="UTC"),
        pd.Timestamp("2010-11-26T21:01:00", tz="UTC"),
    ]

    with pytest.raises(ImportValidationError, match="naive"):
        _validate_batch(batch)


def test_non_positive_voltage_is_rejected() -> None:
    batch = _valid_batch()
    batch.loc[0, "Voltage"] = 0.0

    with pytest.raises(ImportValidationError, match="voltage"):
        _validate_batch(batch)
