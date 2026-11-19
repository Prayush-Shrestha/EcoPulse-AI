"""Regression metrics used by the Phase 4 forecasting evaluation.

The implementation is intentionally explicit about metric validity:

* MAE and RMSE are always defined for finite predictions.
* R2 is undefined when the actual values have zero variance.
* MAPE is undefined when any actual value is zero and is reported only when the
  complete evaluated sample is strictly positive.
* sMAPE is reported for every sample except pairs where both values are zero.

All metrics are computed from the actual and predicted values only; no metric
is hard-coded or copied from a previous run.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

PREDICTION_COLUMNS = ["model", "split", "timestamp", "actual", "predicted"]


def _finite_arrays(
    actual: np.ndarray | pd.Series,
    predicted: np.ndarray | pd.Series,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Return aligned finite arrays plus the number of excluded pairs."""
    actual_array = np.asarray(actual, dtype=np.float64)
    predicted_array = np.asarray(predicted, dtype=np.float64)
    if actual_array.shape != predicted_array.shape:
        raise ValueError("Actual and predicted arrays must have the same shape.")
    mask = np.isfinite(actual_array) & np.isfinite(predicted_array)
    excluded = int((~mask).sum())
    return actual_array[mask], predicted_array[mask], excluded


def regression_metrics(
    actual: np.ndarray | pd.Series,
    predicted: np.ndarray | pd.Series,
) -> dict[str, Any]:
    """Calculate MAE, RMSE, R2, MAPE and sMAPE for one prediction sample.

    MAPE is returned as ``None`` when the sample contains a zero actual value,
    because the percentage error is then mathematically undefined.  The number
    of zero actuals is always reported so the limitation is visible.
    """
    actual_array, predicted_array, excluded = _finite_arrays(actual, predicted)
    if actual_array.size == 0:
        raise ValueError("No finite actual/predicted pairs are available for metrics.")

    errors = predicted_array - actual_array
    absolute_errors = np.abs(errors)
    mae = float(np.mean(absolute_errors))
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    max_error = float(np.max(absolute_errors))

    sum_squared_residuals = float(np.sum(np.square(errors)))
    sum_squared_total = float(np.sum(np.square(actual_array - np.mean(actual_array))))
    r2: float | None
    if sum_squared_total > 0.0:
        r2 = 1.0 - sum_squared_residuals / sum_squared_total
    else:
        r2 = None

    zero_actuals = int(np.count_nonzero(actual_array == 0.0))
    nonzero = actual_array != 0.0
    if zero_actuals == 0:
        mape_pct: float | None = float(
            np.mean(np.abs(errors / actual_array)) * 100.0
        )
        mape_note = "valid: all actual values are non-zero"
    else:
        mape_pct = None
        mape_note = (
            "undefined: zero actual values are present; use MAE/RMSE/sMAPE instead"
        )

    smape_denominator = np.abs(actual_array) + np.abs(predicted_array)
    smape_valid = smape_denominator > 0.0
    if np.any(smape_valid):
        smape_pct: float | None = float(
            np.mean(
                2.0
                * absolute_errors[smape_valid]
                / smape_denominator[smape_valid]
            )
            * 100.0
        )
    else:
        smape_pct = None

    return {
        "n": int(actual_array.size),
        "excluded_non_finite": excluded,
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "mape_pct": mape_pct,
        "smape_pct": smape_pct,
        "max_error": max_error,
        "mape_valid_points": int(np.count_nonzero(nonzero)),
        "zero_actuals": zero_actuals,
        "mape_note": mape_note,
    }


def metrics_by_group(
    predictions: pd.DataFrame,
    group_columns: tuple[str, ...] = ("model", "split"),
) -> pd.DataFrame:
    """Calculate metrics for every model/split group in a predictions table."""
    missing = [
        column
        for column in [*group_columns, "actual", "predicted"]
        if column not in predictions.columns
    ]
    if missing:
        raise ValueError("Predictions table is missing columns: " + ", ".join(missing))
    if predictions.empty:
        raise ValueError("Predictions table is empty.")

    rows: list[dict[str, Any]] = []
    for keys, group in predictions.groupby(list(group_columns), sort=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        metrics = regression_metrics(group["actual"], group["predicted"])
        row = dict(zip(group_columns, keys, strict=True))
        row.update(metrics)
        rows.append(row)

    return pd.DataFrame(rows)


def improvement_pct(baseline_error: float, candidate_error: float) -> float:
    """Return the percentage reduction of a candidate error over a baseline."""
    if baseline_error == 0.0:
        raise ValueError("Baseline error is zero; relative improvement is undefined.")
    return (baseline_error - candidate_error) / baseline_error * 100.0


def format_metric(value: Any, digits: int = 4) -> str:
    """Format one metric consistently for text reports."""
    if value is None:
        return "N/A"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):,.{digits}f}"
    return str(value)
