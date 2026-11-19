"""Train and compare Phase 4 hourly energy-forecasting models.

All models see the same 24 causal features.  Training uses the chronological
train split only; model selection uses the validation split only.  The test
split is predicted once, after the best model has been selected, and is saved
for the separate evaluation stage.  Only the selected model is persisted as a
Joblib artefact.
"""

from __future__ import annotations

import gc
import hashlib
import json
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACHINE_LEARNING_DIR = PROJECT_ROOT / "machine-learning"
ML_DATA_DIR = PROJECT_ROOT / "data" / "processed" / "ml"
MODEL_DIR = MACHINE_LEARNING_DIR / "models" / "forecasting"

if str(MACHINE_LEARNING_DIR) not in sys.path:
    sys.path.insert(0, str(MACHINE_LEARNING_DIR))

from utils.features import (  # noqa: E402
    FORECAST_FEATURES,
    TARGET_COLUMN,
    LagBaseline,
    split_summary,
)
from utils.metrics import regression_metrics  # noqa: E402
from utils.validation import (  # noqa: E402
    FAIL,
    check_lines,
    validate_forecast_dataset,
)

PROJECT_NAME = "EcoPulse AI"
RANDOM_SEED = 42
MODEL_VERSION = "1.0.0"
FORECAST_DATASET_PATH = ML_DATA_DIR / "forecasting_dataset.parquet"
PREDICTIONS_PATH = ML_DATA_DIR / "forecasting_predictions.parquet"
TRAINING_SUMMARY_PATH = ML_DATA_DIR / "forecasting_training_summary.json"
BEST_MODEL_PATH = MODEL_DIR / "best_forecasting_model.joblib"
METADATA_PATH = MODEL_DIR / "forecasting_metadata.json"
FEATURES_PATH = MODEL_DIR / "forecasting_features.json"
PREPROCESSOR_PATH = MODEL_DIR / "forecasting_preprocessor.joblib"

MODEL_NAMES = (
    "Naive (lag 1)",
    "Seasonal Naive (lag 24)",
    "Linear Regression",
    "Random Forest",
    "HistGradientBoosting",
)


def sha256sum(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _build_estimators() -> dict[str, Any]:
    """Create fresh estimators with fixed random seeds."""
    return {
        "Linear Regression": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                ("regressor", LinearRegression(fit_intercept=True)),
            ]
        ),
        "Random Forest": RandomForestRegressor(
            n_estimators=300,
            max_depth=20,
            min_samples_leaf=2,
            max_features=0.5,
            n_jobs=-1,
            random_state=RANDOM_SEED,
        ),
        "HistGradientBoosting": HistGradientBoostingRegressor(
            max_iter=400,
            learning_rate=0.05,
            max_leaf_nodes=31,
            min_samples_leaf=20,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=RANDOM_SEED,
        ),
    }


def _model_parameters(model: Any) -> dict[str, Any]:
    """Return JSON-safe estimator parameters for the experiment record."""
    if isinstance(model, LagBaseline):
        return {"lag": int(model.lag)}
    parameters = model.get_params(deep=True)
    safe: dict[str, Any] = {}
    for key, value in parameters.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe


def _model_descriptions() -> dict[str, str]:
    """Return human-readable configuration notes for each model."""
    return {
        "Naive (lag 1)": "Persistence baseline: prediction equals the previous hour.",
        "Seasonal Naive (lag 24)": (
            "Seasonal persistence baseline: prediction equals the same hour on the "
            "previous day."
        ),
        "Linear Regression": (
            "Ordinary least squares on the 24 causal features; StandardScaler fitted "
            "on the training split only."
        ),
        "Random Forest": (
            "300 bootstrapped regression trees, maximum depth 20, minimum leaf size 2, "
            "50% of features considered per split."
        ),
        "HistGradientBoosting": (
            "400 boosting iterations, learning rate 0.05, 31 leaves, L2 penalty 1.0, "
            "early stopping disabled to avoid a random internal split."
        ),
    }


def _prediction_frame(
    model_name: str,
    split: str,
    frame: pd.DataFrame,
    predictions: np.ndarray,
) -> pd.DataFrame:
    """Build a long-form prediction table for one model and split."""
    return pd.DataFrame(
        {
            "model": model_name,
            "split": split,
            "timestamp": frame["timestamp"].to_numpy(),
            "actual": frame[TARGET_COLUMN].to_numpy(dtype=float),
            "predicted": np.asarray(predictions, dtype=float),
        }
    )


def _json_timestamp(value: Any) -> str:
    """Format a pandas timestamp for JSON."""
    return pd.Timestamp(value).isoformat()


def run_training(verbose: bool = True) -> dict[str, Any]:
    """Fit all forecasting candidates and save the validation-selected model."""
    started_utc = datetime.now(UTC)
    started = time.perf_counter()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    ML_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not FORECAST_DATASET_PATH.is_file():
        raise FileNotFoundError(
            f"Prepared forecasting dataset not found: {FORECAST_DATASET_PATH}. "
            "Run 01_prepare_ml_data.py first."
        )

    forecast = pd.read_parquet(FORECAST_DATASET_PATH)
    checks = validate_forecast_dataset(forecast, FORECAST_FEATURES)
    if any(check.status == FAIL for check in checks):
        raise RuntimeError(
            "Forecasting dataset validation failed:\n"
            + "\n".join(check_lines(checks, include_passed=False))
        )

    modeling = forecast.loc[forecast["is_modeling_row"]].copy()
    train = modeling.loc[modeling["split"] == "train"].sort_values("timestamp")
    validation = modeling.loc[modeling["split"] == "validation"].sort_values(
        "timestamp"
    )
    test = modeling.loc[modeling["split"] == "test"].sort_values("timestamp")

    if train.empty or validation.empty or test.empty:
        raise ValueError("Train, validation and test splits must all be non-empty.")

    X_train = train[FORECAST_FEATURES]
    y_train = train[TARGET_COLUMN].to_numpy(dtype=float)
    X_validation = validation[FORECAST_FEATURES]
    y_validation = validation[TARGET_COLUMN].to_numpy(dtype=float)
    X_test = test[FORECAST_FEATURES]
    y_test = test[TARGET_COLUMN].to_numpy(dtype=float)

    if verbose:
        print("=" * 78)
        print(f"{PROJECT_NAME.upper()} - PHASE 4 FORECASTING TRAINING")
        print("=" * 78)
        print(
            f"Modelling rows: {len(modeling):,} | features: {len(FORECAST_FEATURES)} "
            f"| target: {TARGET_COLUMN}"
        )
        print(f"Train:      {len(train):,} rows")
        print(f"Validation: {len(validation):,} rows")
        print(f"Test:       {len(test):,} rows")
        print("-" * 78)

    estimators = _build_estimators()
    fitted_models: dict[str, Any] = {
        "Naive (lag 1)": LagBaseline(lag=1),
        "Seasonal Naive (lag 24)": LagBaseline(lag=24),
        **estimators,
    }

    prediction_parts: list[pd.DataFrame] = []
    validation_metrics: dict[str, dict[str, Any]] = {}
    training_metrics: dict[str, dict[str, Any]] = {}
    training_seconds: dict[str, float] = {}
    prediction_seconds: dict[str, float] = {}

    for model_name in MODEL_NAMES:
        model = fitted_models[model_name]
        model_started = time.perf_counter()
        if not isinstance(model, LagBaseline):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=FutureWarning)
                model.fit(X_train, y_train)
        training_seconds[model_name] = time.perf_counter() - model_started

        prediction_started = time.perf_counter()
        train_prediction = np.asarray(model.predict(X_train), dtype=float)
        validation_prediction = np.asarray(model.predict(X_validation), dtype=float)
        prediction_seconds[model_name] = time.perf_counter() - prediction_started

        if not np.isfinite(train_prediction).all() or not np.isfinite(
            validation_prediction
        ).all():
            raise ValueError(f"{model_name} produced non-finite train/validation predictions.")

        prediction_parts.append(
            _prediction_frame(model_name, "train", train, train_prediction)
        )
        prediction_parts.append(
            _prediction_frame(
                model_name,
                "validation",
                validation,
                validation_prediction,
            )
        )
        training_metrics[model_name] = regression_metrics(y_train, train_prediction)
        validation_metrics[model_name] = regression_metrics(
            y_validation, validation_prediction
        )

        if verbose:
            metrics = validation_metrics[model_name]
            print(
                f"{model_name:<24} fit {training_seconds[model_name]:>7.2f} s | "
                f"validation MAE {metrics['mae']:.4f} | "
                f"RMSE {metrics['rmse']:.4f} | R2 {metrics['r2']:.4f}"
            )

    ranking = sorted(
        MODEL_NAMES,
        key=lambda name: (
            validation_metrics[name]["rmse"],
            validation_metrics[name]["mae"],
        ),
    )
    best_model_name = ranking[0]

    # The test split is touched only after selection is complete.
    for model_name in MODEL_NAMES:
        model = fitted_models[model_name]
        prediction_started = time.perf_counter()
        test_prediction = np.asarray(model.predict(X_test), dtype=float)
        prediction_seconds[model_name] += time.perf_counter() - prediction_started
        if not np.isfinite(test_prediction).all():
            raise ValueError(f"{model_name} produced non-finite test predictions.")
        prediction_parts.append(
            _prediction_frame(model_name, "test", test, test_prediction)
        )

    predictions = pd.concat(prediction_parts, ignore_index=True)
    predictions = predictions.sort_values(["model", "split", "timestamp"]).reset_index(
        drop=True
    )
    predictions.to_parquet(PREDICTIONS_PATH, index=False, compression="snappy")

    best_model = fitted_models[best_model_name]
    validation_metric = validation_metrics[best_model_name]
    test_metric = regression_metrics(
        y_test,
        predictions.loc[
            (predictions["model"] == best_model_name)
            & (predictions["split"] == "test"),
            "predicted",
        ].to_numpy(dtype=float),
    )

    preprocessor = None
    if isinstance(best_model, Pipeline):
        preprocessor = best_model.named_steps["scaler"]
        joblib.dump(preprocessor, PREPROCESSOR_PATH, compress=3)
    elif PREPROCESSOR_PATH.exists():
        PREPROCESSOR_PATH.unlink()

    trained_at_utc = datetime.now(UTC).isoformat()
    bundle = {
        "model": best_model,
        "model_name": best_model_name,
        "model_version": MODEL_VERSION,
        "feature_names": list(FORECAST_FEATURES),
        "target": TARGET_COLUMN,
        "preprocessor": preprocessor,
        "trained_at_utc": trained_at_utc,
        "training_split": "train",
        "random_seed": RANDOM_SEED,
    }
    joblib.dump(bundle, BEST_MODEL_PATH, compress=3)

    split_information = []
    for row in split_summary(forecast):
        split_information.append(
            {
                "split": row["split"],
                "rows": int(row["rows"]),
                "start": _json_timestamp(row["start"]),
                "end": _json_timestamp(row["end"]),
            }
        )

    feature_document = {
        "target": TARGET_COLUMN,
        "features": list(FORECAST_FEATURES),
        "feature_groups": {
            "time": [
                "hour",
                "day_of_week",
                "day_of_month",
                "day_of_year",
                "week_of_year",
                "month",
                "is_weekend",
            ],
            "cyclical": [
                "hour_sin",
                "hour_cos",
                "dow_sin",
                "dow_cos",
                "month_sin",
                "month_cos",
            ],
            "lag": ["lag_1", "lag_2", "lag_3", "lag_24", "lag_48", "lag_168"],
            "rolling": [
                "rolling_mean_3",
                "rolling_mean_6",
                "rolling_mean_24",
                "rolling_mean_168",
                "rolling_std_24",
            ],
        },
        "causality": (
            "Every lag and rolling statistic is computed from values strictly before "
            "the forecasted hour; rolling windows are shifted by one hour first."
        ),
        "generated_at_utc": trained_at_utc,
        "model_version": MODEL_VERSION,
    }
    with FEATURES_PATH.open("w", encoding="utf-8") as handle:
        json.dump(feature_document, handle, indent=2)

    metadata = {
        "model_name": best_model_name,
        "model_version": MODEL_VERSION,
        "model_type": type(best_model).__name__,
        "training_date_utc": trained_at_utc,
        "target_variable": TARGET_COLUMN,
        "target_definition": (
            "Total energy consumption (kWh) of one complete clock-hour with exactly "
            "60 valid one-minute observations. Incomplete hours are missing targets, "
            "never zero consumption."
        ),
        "feature_names": list(FORECAST_FEATURES),
        "feature_count": len(FORECAST_FEATURES),
        "training_period": split_information[0],
        "validation_period": split_information[1],
        "test_period": split_information[2],
        "selection_metric": "validation RMSE",
        "validation_metrics": validation_metric,
        "test_metrics": test_metric,
        "train_metrics": training_metrics[best_model_name],
        "hyperparameters": _model_parameters(best_model),
        "preprocessing": (
            "StandardScaler fitted on the training split"
            if preprocessor is not None
            else "none required"
        ),
        "random_seed": RANDOM_SEED,
        "training_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "test_rows": int(len(test)),
        "dataset_file": str(FORECAST_DATASET_PATH.relative_to(PROJECT_ROOT)),
        "dataset_sha256": sha256sum(FORECAST_DATASET_PATH),
        "environment": {
            "python": sys.version.split()[0],
            "scikit_learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "notes": [
            "The model was fitted on the training split only.",
            "The test split was evaluated once, after validation-based selection.",
            "Only the selected model is persisted; candidate models are not duplicated.",
        ],
    }
    with METADATA_PATH.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, default=str)

    # Reload immediately so a corrupt artefact cannot reach the evaluation stage.
    reloaded = joblib.load(BEST_MODEL_PATH)
    if "model" not in reloaded or reloaded["model_name"] != best_model_name:
        raise RuntimeError("Saved forecasting model could not be reloaded correctly.")

    summary = {
        "started_at_utc": started_utc.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "total_seconds": time.perf_counter() - started,
        "random_seed": RANDOM_SEED,
        "model_version": MODEL_VERSION,
        "target": TARGET_COLUMN,
        "feature_count": len(FORECAST_FEATURES),
        "features": list(FORECAST_FEATURES),
        "splits": split_information,
        "models": list(MODEL_NAMES),
        "model_descriptions": _model_descriptions(),
        "training_seconds": training_seconds,
        "prediction_seconds": prediction_seconds,
        "validation_metrics": validation_metrics,
        "train_metrics": training_metrics,
        "validation_ranking": ranking,
        "best_model": best_model_name,
        "selection_metric": "validation RMSE",
        "best_validation_metrics": validation_metric,
        "best_test_metrics": test_metric,
        "predictions_file": str(PREDICTIONS_PATH.relative_to(PROJECT_ROOT)),
        "model_file": str(BEST_MODEL_PATH.relative_to(PROJECT_ROOT)),
        "metadata_file": str(METADATA_PATH.relative_to(PROJECT_ROOT)),
        "features_file": str(FEATURES_PATH.relative_to(PROJECT_ROOT)),
        "preprocessor_file": (
            str(PREPROCESSOR_PATH.relative_to(PROJECT_ROOT))
            if PREPROCESSOR_PATH.exists()
            else None
        ),
        "validation": {
            "passed": sum(check.status == "PASS" for check in checks),
            "failed": sum(check.status == "FAIL" for check in checks),
            "warnings": sum(check.status == "WARN" for check in checks),
        },
    }
    with TRAINING_SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    if verbose:
        print("-" * 78)
        print(
            f"Selected model: {best_model_name} "
            f"(validation RMSE {validation_metric['rmse']:.4f})"
        )
        print(
            f"One-time test result: MAE {test_metric['mae']:.4f} | "
            f"RMSE {test_metric['rmse']:.4f} | R2 {test_metric['r2']:.4f}"
        )
        print(f"Saved model: {BEST_MODEL_PATH.relative_to(PROJECT_ROOT)}")
        print(f"Saved predictions: {PREDICTIONS_PATH.relative_to(PROJECT_ROOT)}")

    del fitted_models, best_model, predictions, train, validation, test, modeling, forecast
    gc.collect()
    return summary


def main() -> int:
    """Train the forecasting models from the command line."""
    try:
        summary = run_training(verbose=True)
    except Exception as error:  # pragma: no cover - surfaced with a clear message
        print(f"\nERROR: {error}")
        return 1
    print(
        f"\nPhase 4 forecasting training status: COMPLETED "
        f"({summary['total_seconds']:.2f} s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
