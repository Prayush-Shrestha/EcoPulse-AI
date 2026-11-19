"""Train unsupervised Phase 4 anomaly detectors on minute-level power data.

Two complementary methods are fitted or configured on the chronological train
split only:

1. A causal rolling z-score baseline on Global_active_power.  The 24-hour mean
   and standard deviation are shifted by one minute, and |z| >= 3 is flagged.
2. An Isolation Forest on 20 standardised measurement, calendar and historical
   features, with a 0.5% contamination assumption.

The test split is scored only for final evaluation.  No ground-truth labels are
available, so no accuracy, precision, recall or F1 score is produced.
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

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACHINE_LEARNING_DIR = PROJECT_ROOT / "machine-learning"
ML_DATA_DIR = PROJECT_ROOT / "data" / "processed" / "ml"
MODEL_DIR = MACHINE_LEARNING_DIR / "models" / "anomaly_detection"

if str(MACHINE_LEARNING_DIR) not in sys.path:
    sys.path.insert(0, str(MACHINE_LEARNING_DIR))

from utils.features import ANOMALY_FEATURES, split_summary  # noqa: E402
from utils.validation import (  # noqa: E402
    FAIL,
    check_lines,
    validate_anomaly_dataset,
)

PROJECT_NAME = "EcoPulse AI"
RANDOM_SEED = 42
MODEL_VERSION = "1.0.0"
CONTAMINATION = 0.005
ZSCORE_THRESHOLD = 3.0
N_ESTIMATORS = 200
MAX_SAMPLES = 256

ANOMALY_DATASET_PATH = ML_DATA_DIR / "anomaly_dataset.parquet"
PREPARATION_SUMMARY_PATH = ML_DATA_DIR / "preparation_summary.json"
PREDICTIONS_PATH = ML_DATA_DIR / "anomaly_predictions.parquet"
TRAINING_SUMMARY_PATH = ML_DATA_DIR / "anomaly_training_summary.json"
MODEL_PATH = MODEL_DIR / "isolation_forest.joblib"
SCALER_PATH = MODEL_DIR / "anomaly_scaler.joblib"
METADATA_PATH = MODEL_DIR / "anomaly_metadata.json"
FEATURES_PATH = MODEL_DIR / "anomaly_features.json"


def sha256sum(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _split_counts(
    frame: pd.DataFrame,
    iforest_flags: np.ndarray,
    zscore_flags: np.ndarray,
) -> list[dict[str, Any]]:
    """Count rows and flags for each chronological split."""
    rows: list[dict[str, Any]] = []
    split_values = frame["split"].to_numpy()
    for split in ("train", "validation", "test"):
        mask = split_values == split
        total = int(mask.sum())
        iforest_count = int(iforest_flags[mask].sum())
        zscore_count = int(zscore_flags[mask].sum())
        rows.append(
            {
                "split": split,
                "rows": total,
                "iforest_anomalies": iforest_count,
                "iforest_percentage": iforest_count / total * 100.0 if total else 0.0,
                "zscore_anomalies": zscore_count,
                "zscore_percentage": zscore_count / total * 100.0 if total else 0.0,
            }
        )
    return rows


def _json_timestamp(value: Any) -> str:
    """Format a pandas timestamp for JSON."""
    return pd.Timestamp(value).isoformat()


def run_training(verbose: bool = True) -> dict[str, Any]:
    """Fit the anomaly detectors, score every split and persist the artefacts."""
    started_utc = datetime.now(UTC)
    started = time.perf_counter()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    ML_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for path in (ANOMALY_DATASET_PATH, PREPARATION_SUMMARY_PATH):
        if not path.is_file():
            raise FileNotFoundError(
                f"Required preparation artefact not found: {path}. "
                "Run 01_prepare_ml_data.py first."
            )

    with PREPARATION_SUMMARY_PATH.open("r", encoding="utf-8") as handle:
        preparation = json.load(handle)
    source_summary = preparation["anomaly_detection"]

    frame = pd.read_parquet(ANOMALY_DATASET_PATH)
    checks = validate_anomaly_dataset(frame, ANOMALY_FEATURES)
    if any(check.status == FAIL for check in checks):
        raise RuntimeError(
            "Anomaly dataset validation failed:\n"
            + "\n".join(check_lines(checks, include_passed=False))
        )

    split_values = frame["split"].to_numpy()
    train_mask = split_values == "train"
    validation_mask = split_values == "validation"
    test_mask = split_values == "test"
    if not train_mask.any() or not validation_mask.any() or not test_mask.any():
        raise ValueError("Train, validation and test splits must all be non-empty.")

    if verbose:
        print("=" * 78)
        print(f"{PROJECT_NAME.upper()} - PHASE 4 ANOMALY DETECTION TRAINING")
        print("=" * 78)
        print(
            f"Usable minutes: {len(frame):,} | features: {len(ANOMALY_FEATURES)} "
            f"| contamination: {CONTAMINATION:.2%}"
        )
        for row in split_summary(frame):
            print(
                f"  {row['split']:<10} {row['rows']:>9,} rows "
                f"{pd.Timestamp(row['start'])} -> {pd.Timestamp(row['end'])}"
            )
        print("-" * 78)

    train_features = frame.loc[train_mask, ANOMALY_FEATURES].to_numpy(dtype=np.float32)
    scaler = StandardScaler()
    scaler_started = time.perf_counter()
    scaled_train = scaler.fit_transform(train_features)
    scaler_seconds = time.perf_counter() - scaler_started

    forest = IsolationForest(
        n_estimators=N_ESTIMATORS,
        max_samples=MAX_SAMPLES,
        contamination=CONTAMINATION,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    forest_started = time.perf_counter()
    forest.fit(scaled_train)
    forest_seconds = time.perf_counter() - forest_started

    score_started = time.perf_counter()
    train_scores = forest.decision_function(scaled_train).astype(np.float32)
    train_flags = train_scores < 0.0
    del scaled_train, train_features
    gc.collect()

    iforest_scores = np.empty(len(frame), dtype=np.float32)
    iforest_flags = np.zeros(len(frame), dtype=bool)
    iforest_scores[train_mask] = train_scores
    iforest_flags[train_mask] = train_flags

    for split, mask in (
        ("validation", validation_mask),
        ("test", test_mask),
    ):
        split_features = frame.loc[mask, ANOMALY_FEATURES].to_numpy(dtype=np.float32)
        scaled = scaler.transform(split_features)
        scores = forest.decision_function(scaled).astype(np.float32)
        iforest_scores[mask] = scores
        iforest_flags[mask] = scores < 0.0
        if verbose:
            print(
                f"Scored {split:<10} {int(mask.sum()):>9,} rows | "
                f"flagged {int(iforest_flags[mask].sum()):>6,} "
                f"({iforest_flags[mask].mean() * 100:.3f}%)"
            )
        del split_features, scaled, scores
        gc.collect()

    score_seconds = time.perf_counter() - score_started
    zscore_flags = (
        np.abs(frame["gap_z_24h"].to_numpy(dtype=np.float64)) >= ZSCORE_THRESHOLD
    )
    iforest_scores = iforest_scores.astype(np.float32)

    split_counts = _split_counts(frame, iforest_flags, zscore_flags)
    overall_iforest = int(iforest_flags.sum())
    overall_zscore = int(zscore_flags.sum())
    decision_quantile = float(
        np.quantile(train_scores, CONTAMINATION, method="linear")
    )
    offset = float(forest.offset_)
    decision_threshold = 0.0

    prediction_frame = pd.DataFrame(
        {
            "timestamp": frame["timestamp"].to_numpy(),
            "split": frame["split"].to_numpy(),
            "Global_active_power": frame["Global_active_power"].astype("float32").to_numpy(),
            "Global_reactive_power": frame["Global_reactive_power"]
            .astype("float32")
            .to_numpy(),
            "Voltage": frame["Voltage"].astype("float32").to_numpy(),
            "Global_intensity": frame["Global_intensity"].astype("float32").to_numpy(),
            "Sub_metering_1": frame["Sub_metering_1"].astype("float32").to_numpy(),
            "Sub_metering_2": frame["Sub_metering_2"].astype("float32").to_numpy(),
            "Sub_metering_3": frame["Sub_metering_3"].astype("float32").to_numpy(),
            "gap_z_24h": frame["gap_z_24h"].astype("float32").to_numpy(),
            "isolation_forest_score": iforest_scores,
            "isolation_forest_anomaly": iforest_flags,
            "zscore_anomaly": zscore_flags,
        }
    )
    prediction_frame.to_parquet(PREDICTIONS_PATH, index=False, compression="snappy")

    trained_at_utc = datetime.now(UTC).isoformat()
    bundle = {
        "model": forest,
        "scaler": scaler,
        "feature_names": list(ANOMALY_FEATURES),
        "threshold": offset,
        "contamination": CONTAMINATION,
        "model_name": "Isolation Forest",
        "model_version": MODEL_VERSION,
        "random_seed": RANDOM_SEED,
        "trained_at_utc": trained_at_utc,
        "training_split": "train",
    }
    joblib.dump(bundle, MODEL_PATH, compress=3)
    joblib.dump(scaler, SCALER_PATH, compress=3)

    feature_document = {
        "features": list(ANOMALY_FEATURES),
        "feature_groups": {
            "measurements": [
                "Global_active_power",
                "Global_reactive_power",
                "Voltage",
                "Global_intensity",
                "Sub_metering_1",
                "Sub_metering_2",
                "Sub_metering_3",
            ],
            "calendar": [
                "hour",
                "day_of_week",
                "is_weekend",
                "hour_sin",
                "hour_cos",
                "dow_sin",
                "dow_cos",
            ],
            "historical": [
                "gap_lag_1",
                "gap_mean_60",
                "gap_std_60",
                "gap_mean_1440",
                "gap_std_1440",
                "gap_z_24h",
            ],
        },
        "causality": (
            "The 60-minute and 24-hour statistics use values shifted by one minute; "
            "the current reading is never part of its own baseline or z-score."
        ),
        "generated_at_utc": trained_at_utc,
        "model_version": MODEL_VERSION,
    }
    with FEATURES_PATH.open("w", encoding="utf-8") as handle:
        json.dump(feature_document, handle, indent=2)

    metadata = {
        "model_name": "Isolation Forest",
        "model_version": MODEL_VERSION,
        "model_type": type(forest).__name__,
        "training_date_utc": trained_at_utc,
        "dataset": str(ANOMALY_DATASET_PATH.relative_to(PROJECT_ROOT)),
        "dataset_sha256": sha256sum(ANOMALY_DATASET_PATH),
        "source": {
            "cleaned_minutes": int(source_summary["cleaned_minutes"]),
            "imputed_rows_excluded": int(source_summary["imputed_rows_excluded"]),
            "warmup_or_gap_rows_excluded": int(
                source_summary["warmup_or_gap_rows_excluded"]
            ),
            "usable_minutes": int(source_summary["rows"]),
        },
        "feature_names": list(ANOMALY_FEATURES),
        "feature_count": len(ANOMALY_FEATURES),
        "training_period": {
            "start": _json_timestamp(frame.loc[train_mask, "timestamp"].min()),
            "end": _json_timestamp(frame.loc[train_mask, "timestamp"].max()),
            "rows": int(train_mask.sum()),
        },
        "validation_period": {
            "start": _json_timestamp(frame.loc[validation_mask, "timestamp"].min()),
            "end": _json_timestamp(frame.loc[validation_mask, "timestamp"].max()),
            "rows": int(validation_mask.sum()),
        },
        "test_period": {
            "start": _json_timestamp(frame.loc[test_mask, "timestamp"].min()),
            "end": _json_timestamp(frame.loc[test_mask, "timestamp"].max()),
            "rows": int(test_mask.sum()),
        },
        "algorithm": "sklearn.ensemble.IsolationForest",
        "contamination": CONTAMINATION,
        "contamination_rationale": (
            "0.5% was chosen a priori to surface roughly ten thousand candidate "
            "minutes across about two million observations: enough for investigation "
            "without declaring a large share of normal consumption anomalous. It is "
            "not an estimate of the unknown true fault rate."
        ),
        "isolation_forest": {
            "n_estimators": N_ESTIMATORS,
            "max_samples": MAX_SAMPLES,
            "random_state": RANDOM_SEED,
            "iforest_offset": offset,
            "decision_threshold": decision_threshold,
            "training_decision_quantile_0_005": decision_quantile,
            "score_interpretation": (
                "decision_function output; lower values are more anomalous. The "
                "decision threshold is 0.0; offset_ is the raw score_samples "
                "threshold used to centre the decision function."
            ),
        },
        "preprocessing": {
            "scaler": "StandardScaler",
            "fitted_on": "training split only",
            "means": scaler.mean_.astype(float).tolist(),
            "scales": scaler.scale_.astype(float).tolist(),
        },
        "zscore_baseline": {
            "threshold": ZSCORE_THRESHOLD,
            "method": (
                "absolute deviation from the previous 24-hour rolling mean divided "
                "by the previous 24-hour rolling standard deviation"
            ),
            "minimum_history_minutes": 720,
            "note": (
                "The z-score baseline uses Global_active_power only and assumes an "
                "approximately stable local distribution; it is not a fault detector."
            ),
        },
        "detection_counts": {
            "overall_rows": int(len(frame)),
            "iforest_anomalies": overall_iforest,
            "iforest_percentage": overall_iforest / len(frame) * 100.0,
            "zscore_anomalies": overall_zscore,
            "zscore_percentage": overall_zscore / len(frame) * 100.0,
            "by_split": split_counts,
        },
        "label_status": (
            "No reliable ground-truth anomaly labels exist. Detected observations are "
            "deviation candidates, not confirmed faults; accuracy, precision, recall "
            "and F1 are intentionally not reported."
        ),
        "environment": {
            "python": sys.version.split()[0],
            "scikit_learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    with METADATA_PATH.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, default=str)

    summary = {
        "started_at_utc": started_utc.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "total_seconds": time.perf_counter() - started,
        "scaler_seconds": scaler_seconds,
        "fit_seconds": forest_seconds,
        "score_seconds": score_seconds,
        "random_seed": RANDOM_SEED,
        "model_version": MODEL_VERSION,
        "rows": int(len(frame)),
        "features": list(ANOMALY_FEATURES),
        "contamination": CONTAMINATION,
        "zscore_threshold": ZSCORE_THRESHOLD,
        "iforest_offset": offset,
        "decision_threshold": decision_threshold,
        "training_decision_quantile_0_005": decision_quantile,
        "split_counts": split_counts,
        "overall": {
            "rows": int(len(frame)),
            "iforest_anomalies": overall_iforest,
            "iforest_percentage": overall_iforest / len(frame) * 100.0,
            "zscore_anomalies": overall_zscore,
            "zscore_percentage": overall_zscore / len(frame) * 100.0,
        },
        "predictions_file": str(PREDICTIONS_PATH.relative_to(PROJECT_ROOT)),
        "model_file": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
        "scaler_file": str(SCALER_PATH.relative_to(PROJECT_ROOT)),
        "metadata_file": str(METADATA_PATH.relative_to(PROJECT_ROOT)),
        "features_file": str(FEATURES_PATH.relative_to(PROJECT_ROOT)),
        "validation": {
            "passed": sum(check.status == "PASS" for check in checks),
            "failed": sum(check.status == "FAIL" for check in checks),
            "warnings": sum(check.status == "WARN" for check in checks),
        },
    }
    with TRAINING_SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    reloaded = joblib.load(MODEL_PATH)
    if "model" not in reloaded or "scaler" not in reloaded:
        raise RuntimeError("Saved anomaly model could not be reloaded correctly.")

    if verbose:
        print("-" * 78)
        print(
            f"Isolation Forest: {overall_iforest:,} anomalies "
            f"({overall_iforest / len(frame) * 100:.3f}%) | decision threshold "
            f"{decision_threshold:.1f} | raw-score offset {offset:.6f}"
        )
        print(
            f"Rolling z-score:  {overall_zscore:,} anomalies "
            f"({overall_zscore / len(frame) * 100:.3f}%) | threshold "
            f"|z| >= {ZSCORE_THRESHOLD:.1f}"
        )
        print(f"Saved model: {MODEL_PATH.relative_to(PROJECT_ROOT)}")
        print(f"Saved predictions: {PREDICTIONS_PATH.relative_to(PROJECT_ROOT)}")
        print(
            f"Validation: {summary['validation']['passed']} passed, "
            f"{summary['validation']['failed']} failed, "
            f"{summary['validation']['warnings']} warnings"
        )

    del frame, prediction_frame, forest, scaler, bundle, reloaded
    gc.collect()
    return summary


def main() -> int:
    """Train the anomaly detectors from the command line."""
    try:
        summary = run_training(verbose=True)
    except Exception as error:  # pragma: no cover - surfaced with a clear message
        print(f"\nERROR: {error}")
        return 1
    print(
        f"\nPhase 4 anomaly training status: COMPLETED "
        f"({summary['total_seconds']:.2f} s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
