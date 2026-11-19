"""Run the complete Phase 4 machine-learning pipeline reproducibly.

Stages:
1. Phase 3 input validation.
2. ML data preparation (forecasting and anomaly datasets).
3. Forecasting model training and validation-based selection.
4. Forecasting evaluation, reports and figures.
5. Anomaly-detection training and scoring.
6. Anomaly evaluation, reports and figures.
7. Final reload, leakage, report and artefact verification.

A failed critical stage stops the pipeline.  The model-evaluation report is
always written with the real outcome, including failures.
"""

from __future__ import annotations

import gc
import importlib.util
import json
import re
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACHINE_LEARNING_DIR = PROJECT_ROOT / "machine-learning"
SRC_DIR = MACHINE_LEARNING_DIR / "src"
UTILS_DIR = MACHINE_LEARNING_DIR / "utils"
DATA_DIR = PROJECT_ROOT / "data" / "processed"
ML_DATA_DIR = DATA_DIR / "ml"
REPORT_DIR = PROJECT_ROOT / "reports" / "machine-learning"
FIGURE_DIR = REPORT_DIR / "figures"
FORECAST_MODEL_DIR = MACHINE_LEARNING_DIR / "models" / "forecasting"
ANOMALY_MODEL_DIR = MACHINE_LEARNING_DIR / "models" / "anomaly_detection"

if str(MACHINE_LEARNING_DIR) not in sys.path:
    sys.path.insert(0, str(MACHINE_LEARNING_DIR))

from utils.features import ANOMALY_FEATURES, FORECAST_FEATURES  # noqa: E402
from utils.metrics import format_metric  # noqa: E402
from utils.validation import (  # noqa: E402
    FAIL,
    add_check,
    check_lines,
    summarize_checks,
    validate_anomaly_dataset,
    validate_anomaly_model_artifact,
    validate_forecast_dataset,
    validate_forecasting_model_artifact,
    validate_phase3_inputs,
)

PROJECT_NAME = "EcoPulse AI"
REPORT_PATH = REPORT_DIR / "model_evaluation_report.txt"

REQUIRED_REPORTS = (
    "forecasting_metrics.csv",
    "forecasting_comparison.csv",
    "forecasting_report.txt",
    "anomaly_detection_report.txt",
    "anomaly_summary.csv",
)
REQUIRED_FIGURES = (
    "forecasting_actual_vs_predicted.png",
    "forecasting_model_comparison.png",
    "forecasting_error_distribution.png",
    "forecasting_residual_analysis.png",
    "forecasting_performance_over_time.png",
    "forecasting_feature_importance.png",
    "anomaly_consumption_timeline.png",
    "anomaly_distribution_over_time.png",
    "anomaly_score_distribution.png",
    "anomaly_method_comparison.png",
    "anomaly_hourly_profile.png",
    "anomaly_normal_vs_anomalous.png",
)
REQUIRED_ARTEFACTS = (
    ML_DATA_DIR / "forecasting_dataset.parquet",
    ML_DATA_DIR / "anomaly_dataset.parquet",
    ML_DATA_DIR / "preparation_summary.json",
    ML_DATA_DIR / "forecasting_predictions.parquet",
    ML_DATA_DIR / "forecasting_training_summary.json",
    ML_DATA_DIR / "anomaly_predictions.parquet",
    ML_DATA_DIR / "anomaly_training_summary.json",
    FORECAST_MODEL_DIR / "best_forecasting_model.joblib",
    FORECAST_MODEL_DIR / "forecasting_metadata.json",
    FORECAST_MODEL_DIR / "forecasting_features.json",
    ANOMALY_MODEL_DIR / "isolation_forest.joblib",
    ANOMALY_MODEL_DIR / "anomaly_scaler.joblib",
    ANOMALY_MODEL_DIR / "anomaly_metadata.json",
    ANOMALY_MODEL_DIR / "anomaly_features.json",
)


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON document."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_stage_module(module_name: str, filename: str) -> Any:
    """Load a numbered script as an importable module."""
    path = SRC_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Pipeline stage script is missing: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _run_stage(
    label: str,
    function: Callable[..., dict[str, Any]],
    context: dict[str, Any],
    verbose: bool,
) -> dict[str, Any]:
    """Run one pipeline stage, record timing and stop on failure."""
    if verbose:
        print(f"\n[STAGE] {label}")
    started = time.perf_counter()
    try:
        result = function(verbose=verbose)
    except Exception as error:
        context["stages"].append(
            {
                "stage": label,
                "status": "FAILED",
                "seconds": time.perf_counter() - started,
                "detail": str(error)[:300],
            }
        )
        raise
    seconds = time.perf_counter() - started
    context["stages"].append(
        {
            "stage": label,
            "status": "COMPLETED",
            "seconds": seconds,
            "detail": "completed",
        }
    )
    if verbose:
        print(f"[STAGE] {label}: COMPLETED in {seconds:.2f} s")
    return result


def _check_required_file(
    checks: list[Any],
    category: str,
    path: Path,
    label: str,
    minimum_bytes: int = 1,
) -> None:
    """Check that a required output exists and is non-trivial."""
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    add_check(
        checks,
        category,
        label,
        exists and size >= minimum_bytes,
        f"{path.relative_to(PROJECT_ROOT)} ({size:,} bytes)"
        if exists
        else f"missing: {path.relative_to(PROJECT_ROOT)}",
    )


def _scan_for_absolute_paths(paths: list[Path]) -> list[str]:
    """Return source lines that contain a hard-coded drive-letter path."""
    pattern = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
    matches: list[str] = []
    for path in paths:
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                matches.append(f"{path.name}:{number}: {line.strip()}")
    return matches


def _final_verification(context: dict[str, Any]) -> tuple[list[Any], list[dict[str, Any]]]:
    """Reload artefacts, revalidate datasets and verify every output file."""
    checks: list[Any] = []
    inventory: list[dict[str, Any]] = []

    forecast_metadata = _load_json(FORECAST_MODEL_DIR / "forecasting_metadata.json")
    anomaly_metadata = _load_json(ANOMALY_MODEL_DIR / "anomaly_metadata.json")
    best_model_name = str(forecast_metadata["model_name"])

    forecast = pd.read_parquet(ML_DATA_DIR / "forecasting_dataset.parquet")
    checks.extend(validate_forecast_dataset(forecast, FORECAST_FEATURES))
    forecast_predictions = pd.read_parquet(
        ML_DATA_DIR / "forecasting_predictions.parquet"
    )
    checks.extend(
        validate_forecasting_model_artifact(
            FORECAST_MODEL_DIR / "best_forecasting_model.joblib",
            FORECAST_MODEL_DIR / "forecasting_metadata.json",
            FORECAST_MODEL_DIR / "forecasting_features.json",
            forecast_predictions,
            best_model_name,
            FORECAST_FEATURES,
            feature_frame=forecast,
        )
    )
    del forecast
    gc.collect()

    anomaly = pd.read_parquet(ML_DATA_DIR / "anomaly_dataset.parquet")
    checks.extend(validate_anomaly_dataset(anomaly, ANOMALY_FEATURES))
    anomaly_predictions = pd.read_parquet(ML_DATA_DIR / "anomaly_predictions.parquet")
    checks.extend(
        validate_anomaly_model_artifact(
            ANOMALY_MODEL_DIR / "isolation_forest.joblib",
            ANOMALY_MODEL_DIR / "anomaly_scaler.joblib",
            ANOMALY_MODEL_DIR / "anomaly_metadata.json",
            ANOMALY_MODEL_DIR / "anomaly_features.json",
            anomaly_predictions,
            ANOMALY_FEATURES,
            float(anomaly_metadata["zscore_baseline"]["threshold"]),
            feature_frame=anomaly.loc[anomaly["split"] == "test"],
        )
    )
    del anomaly, anomaly_predictions
    gc.collect()

    metrics = pd.read_csv(REPORT_DIR / "forecasting_metrics.csv")
    comparison = pd.read_csv(REPORT_DIR / "forecasting_comparison.csv")
    anomaly_summary = pd.read_csv(REPORT_DIR / "anomaly_summary.csv")
    add_check(
        checks,
        "REPORT",
        "forecasting metrics coverage",
        len(metrics) == 15,
        f"{len(metrics)} rows (expected 15 model/split combinations)",
    )
    add_check(
        checks,
        "REPORT",
        "forecasting comparison coverage",
        len(comparison) == 5,
        f"{len(comparison)} rows (expected five models)",
    )
    add_check(
        checks,
        "REPORT",
        "anomaly summary coverage",
        len(anomaly_summary) == 2,
        f"{len(anomaly_summary)} rows (expected two methods)",
    )
    required_metric_columns = {
        "model",
        "split",
        "n",
        "mae",
        "rmse",
        "r2",
        "mape_pct",
        "smape_pct",
    }
    add_check(
        checks,
        "REPORT",
        "forecasting metrics columns",
        required_metric_columns.issubset(metrics.columns),
        ", ".join(sorted(required_metric_columns)),
    )
    required_anomaly_columns = {
        "detection_method",
        "total_observations",
        "detected_anomalies",
        "anomaly_percentage",
    }
    add_check(
        checks,
        "REPORT",
        "anomaly summary columns",
        required_anomaly_columns.issubset(anomaly_summary.columns),
        ", ".join(sorted(required_anomaly_columns)),
    )

    for filename in REQUIRED_REPORTS:
        _check_required_file(
            checks,
            "REPORT",
            REPORT_DIR / filename,
            f"report {filename}",
            minimum_bytes=100,
        )
    for filename in REQUIRED_FIGURES:
        _check_required_file(
            checks,
            "FIGURE",
            FIGURE_DIR / filename,
            f"figure {filename}",
            minimum_bytes=5_000,
        )
    for path in REQUIRED_ARTEFACTS:
        _check_required_file(
            checks,
            "ARTEFACT",
            path,
            f"artefact {path.name}",
        )

    absolute_path_matches = _scan_for_absolute_paths(
        sorted(SRC_DIR.glob("*.py")) + sorted(UTILS_DIR.glob("*.py"))
    )
    add_check(
        checks,
        "CODE QUALITY",
        "scripts avoid hard-coded absolute paths",
        not absolute_path_matches,
        "no drive-letter paths found"
        if not absolute_path_matches
        else "; ".join(absolute_path_matches[:3]),
    )

    for path in (
        *[REPORT_DIR / name for name in REQUIRED_REPORTS],
        *[FIGURE_DIR / name for name in REQUIRED_FIGURES],
        *REQUIRED_ARTEFACTS,
    ):
        if path.exists():
            inventory.append(
                {
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "bytes": int(path.stat().st_size),
                }
            )
    return checks, inventory


def _format_stage_table(stages: list[dict[str, Any]]) -> list[str]:
    """Format pipeline stages as a fixed-width table."""
    lines = [
        f"{'Stage':<34}{'Status':<12}{'Seconds':>10}  Detail",
        "-" * 78,
    ]
    for stage in stages:
        lines.append(
            f"{stage['stage']:<34}{stage['status']:<12}"
            f"{stage['seconds']:>10.2f}  {stage['detail']}"
        )
    return lines


def _write_evaluation_report(
    context: dict[str, Any],
    final_checks: list[Any],
    inventory: list[dict[str, Any]],
    status: str,
) -> None:
    """Write the final model-evaluation and pipeline-verification report."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def add(line: str = "") -> None:
        lines.append(line)

    all_checks = [*context.get("input_checks", []), *final_checks]
    summary = summarize_checks(all_checks)
    finished = datetime.now(UTC)
    duration = (finished - context["started_utc"]).total_seconds()

    add("=" * 78)
    add("ECOPULSE AI - PHASE 4 MODEL EVALUATION AND PIPELINE REPORT")
    add("=" * 78)
    add(f"Generated (UTC):        {finished.isoformat()}")
    add(f"Pipeline started (UTC): {context['started_utc'].isoformat()}")
    add(f"Pipeline duration:      {duration:.3f} seconds")
    add(f"Final pipeline status:  {status}")
    add("")

    add("1. EXECUTION STAGES")
    add("-" * 78)
    for line in _format_stage_table(context.get("stages", [])):
        add(line)
    if context.get("error"):
        add("")
        add("Pipeline error:")
        add(context["error"])
    add("")

    if context.get("preparation"):
        preparation = context["preparation"]
        add("2. PREPARED MACHINE-LEARNING DATA")
        add("-" * 78)
        add(
            f"Phase 3 inputs: minute={preparation['inputs']['cleaned']['rows']:,}, "
            f"hourly={preparation['inputs']['hourly']['rows']:,}, "
            f"daily={preparation['inputs']['daily']['rows']:,}, "
            f"monthly={preparation['inputs']['monthly']['rows']:,}"
        )
        add(
            f"Energy totals: minute {preparation['inputs']['energy_totals_kwh']['minute']:.6f} "
            f"kWh, hourly {preparation['inputs']['energy_totals_kwh']['hourly']:.6f} kWh, "
            f"daily {preparation['inputs']['energy_totals_kwh']['daily']:.6f} kWh, "
            f"monthly {preparation['inputs']['energy_totals_kwh']['monthly']:.6f} kWh"
        )
        add(
            f"Forecasting: {preparation['forecasting']['hourly_intervals']:,} hourly "
            f"intervals -> {preparation['forecasting']['modeling_rows']:,} supervised "
            f"rows with {preparation['forecasting']['feature_count']} causal features"
        )
        for row in preparation["forecasting"]["splits"]:
            add(
                f"  {row['split']:<10} {row['rows']:>7,} rows  "
                f"{row['start']} -> {row['end']}"
            )
        add(
            f"Anomaly: {preparation['anomaly_detection']['cleaned_minutes']:,} cleaned "
            f"minutes -> {preparation['anomaly_detection']['rows']:,} usable minutes "
            f"({preparation['anomaly_detection']['imputed_rows_excluded']:,} imputed "
            f"and {preparation['anomaly_detection']['warmup_or_gap_rows_excluded']:,} "
            f"warm-up/gap rows excluded)"
        )
        for row in preparation["anomaly_detection"]["splits"]:
            add(
                f"  {row['split']:<10} {row['rows']:>7,} rows  "
                f"{row['start']} -> {row['end']}"
            )
        add("")

    if context.get("forecasting"):
        forecasting = context["forecasting"]
        add("3. FORECASTING RESULT")
        add("-" * 78)
        add(f"Selected model:   {forecasting['best_model']}")
        add(
            f"Validation RMSE:  "
            f"{format_metric(forecasting['validation_metrics']['rmse'])} kWh"
        )
        add(
            f"Validation MAE:   "
            f"{format_metric(forecasting['validation_metrics']['mae'])} kWh"
        )
        add(
            f"Test RMSE:        "
            f"{format_metric(forecasting['test_metrics']['rmse'])} kWh"
        )
        add(
            f"Test MAE:         "
            f"{format_metric(forecasting['test_metrics']['mae'])} kWh"
        )
        add(
            f"Test R2:          "
            f"{format_metric(forecasting['test_metrics']['r2'])}"
        )
        add(
            f"Validation ranking: {', '.join(forecasting['validation_ranking'])}"
        )
        add("")

    if context.get("anomaly"):
        anomaly_result = context["anomaly"]
        add("4. ANOMALY-DETECTION RESULT")
        add("-" * 78)
        for row in anomaly_result["counts"]:
            add(
                f"{row['detection_method']:<40} "
                f"{int(row['detected_anomalies']):>8,} "
                f"({row['anomaly_percentage']:.3f}%)"
            )
        overlap = anomaly_result["overlap"]
        add(
            f"Agreement: both {overlap['both']:,} | Jaccard "
            f"{overlap['jaccard_pct']:.2f}% | IF-only "
            f"{overlap['only_iforest']:,} | z-only {overlap['only_zscore']:,}"
        )
        add(
            "No accuracy, precision, recall or F1 is reported because no reliable "
            "ground-truth labels exist."
        )
        add("")

    add("5. MODEL RELOAD AND LEAKAGE VERIFICATION")
    add("-" * 78)
    if final_checks:
        for line in check_lines(final_checks, include_passed=False):
            add(line)
        if not any(
            check.status in {FAIL, "WARN"} for check in final_checks
        ):
            add(
                "All final checks passed: saved models reproduce stored predictions, "
                "splits are chronological, and lag/rolling features are causal."
            )
    else:
        add("Final verification did not run because an earlier stage failed.")
    add("")

    add("6. ARTEFACT INVENTORY")
    add("-" * 78)
    if inventory:
        for item in sorted(inventory, key=lambda entry: entry["path"]):
            add(f"{item['bytes']:>12,} bytes  {item['path']}")
    else:
        add("No verified artefacts are available.")
    add(
        f"{REPORT_PATH.relative_to(PROJECT_ROOT)} (written by this stage; "
        f"not included in the pre-write inventory)"
    )
    add("")

    add("7. VALIDATION SUMMARY")
    add("-" * 78)
    add(f"Total checks:  {summary['total']}")
    add(f"Passed:        {summary['passed']}")
    add(f"Failed:        {summary['failed']}")
    add(f"Warnings:      {summary['warnings']}")
    add(f"Status:        {summary['status']}")
    add("")
    if summary["failed"]:
        add("Failed checks:")
        for check in all_checks:
            if check.status == FAIL:
                add(f"  {check.category} / {check.name}: {check.detail}")
    if summary["warnings"]:
        add("Warnings:")
        for check in all_checks:
            if check.status == "WARN":
                add(f"  {check.category} / {check.name}: {check.detail}")
    add("")
    add("8. LIMITATIONS")
    add("-" * 78)
    add("- Forecast quality is measured on one chronological hold-out period for one")
    add("  household, not on rolling-origin backtests across many homes.")
    add("- Anomaly detection is unsupervised and unlabelled; detected observations")
    add("  are deviation candidates, not confirmed faults.")
    add("- Saved-model verification confirms reproducibility of the stored outputs,")
    add("  not correctness against unavailable ground truth.")
    add("- The notebooks are separate deliverables and are not executed by this")
    add("  pipeline command.")
    add("")
    add(f"FINAL PHASE 4 PIPELINE STATUS: {status}")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pipeline(verbose: bool = True) -> dict[str, Any]:
    """Execute every Phase 4 stage and return the verified outcome."""
    started_utc = datetime.now(UTC)
    context: dict[str, Any] = {
        "started_utc": started_utc,
        "stages": [],
        "input_checks": [],
        "preparation": None,
        "forecasting": None,
        "anomaly": None,
        "error": None,
    }
    final_checks: list[Any] = []
    inventory: list[dict[str, Any]] = []
    status = "FAILED"

    if verbose:
        print("=" * 78)
        print(f"{PROJECT_NAME.upper()} - PHASE 4 MACHINE-LEARNING PIPELINE")
        print("=" * 78)
        print(f"Project root: {PROJECT_ROOT}")
        print(f"ML data:      {ML_DATA_DIR}")
        print(f"Reports:      {REPORT_DIR}")

    try:
        prepare_module = _load_stage_module("phase4_prepare_ml_data", "01_prepare_ml_data.py")
        forecasting_training_module = _load_stage_module(
            "phase4_train_forecasting", "02_train_forecasting_models.py"
        )
        forecasting_evaluation_module = _load_stage_module(
            "phase4_evaluate_forecasting", "03_evaluate_forecasting_models.py"
        )
        anomaly_training_module = _load_stage_module(
            "phase4_train_anomaly", "04_train_anomaly_detection.py"
        )
        anomaly_evaluation_module = _load_stage_module(
            "phase4_evaluate_anomaly", "05_evaluate_anomaly_detection.py"
        )

        stage_started = time.perf_counter()
        if verbose:
            print("\n[STAGE] Phase 3 input validation")
        input_checks = validate_phase3_inputs(DATA_DIR, prepare_module.EXPECTED_INPUTS)
        context["input_checks"] = input_checks
        input_summary = summarize_checks(input_checks)
        input_status = (
            "COMPLETED" if input_summary["failed"] == 0 else "FAILED"
        )
        context["stages"].append(
            {
                "stage": "Phase 3 input validation",
                "status": input_status,
                "seconds": time.perf_counter() - stage_started,
                "detail": (
                    f"{input_summary['passed']} passed, "
                    f"{input_summary['failed']} failed, "
                    f"{input_summary['warnings']} warnings"
                ),
            }
        )
        if input_summary["failed"]:
            raise RuntimeError(
                "Phase 3 input validation failed: "
                + "; ".join(
                    f"{check.name} ({check.detail})"
                    for check in input_checks
                    if check.status == FAIL
                )
            )
        if verbose:
            print(
                f"[STAGE] Phase 3 input validation: COMPLETED "
                f"({context['stages'][-1]['seconds']:.2f} s)"
            )

        context["preparation"] = _run_stage(
            "ML data preparation",
            prepare_module.run_prepare_data,
            context,
            verbose,
        )
        forecasting_training = _run_stage(
            "Forecasting training",
            forecasting_training_module.run_training,
            context,
            verbose,
        )
        context["forecasting"] = _run_stage(
            "Forecasting evaluation",
            forecasting_evaluation_module.run_evaluation,
            context,
            verbose,
        )
        anomaly_training = _run_stage(
            "Anomaly detection training",
            anomaly_training_module.run_training,
            context,
            verbose,
        )
        context["anomaly"] = _run_stage(
            "Anomaly detection evaluation",
            anomaly_evaluation_module.run_evaluation,
            context,
            verbose,
        )

        if verbose:
            print("\n[STAGE] Final verification")
        verification_started = time.perf_counter()
        final_checks, inventory = _final_verification(context)
        context["stages"].append(
            {
                "stage": "Final verification",
                "status": "COMPLETED",
                "seconds": time.perf_counter() - verification_started,
                "detail": f"{len(final_checks)} checks, {len(inventory)} artefacts",
            }
        )
        if verbose:
            print(
                f"[STAGE] Final verification: COMPLETED "
                f"({context['stages'][-1]['seconds']:.2f} s)"
            )

        combined = summarize_checks([*input_checks, *final_checks])
        if combined["failed"]:
            status = "FAILED"
        elif combined["warnings"]:
            status = "PASSED WITH WARNINGS"
        else:
            status = "PASSED"

        context["forecasting_training"] = {
            "best_model": forecasting_training["best_model"],
            "selection_metric": forecasting_training["selection_metric"],
            "validation_ranking": forecasting_training["validation_ranking"],
            "total_seconds": forecasting_training["total_seconds"],
        }
        context["anomaly_training"] = {
            "contamination": anomaly_training["contamination"],
            "zscore_threshold": anomaly_training["zscore_threshold"],
            "iforest_offset": anomaly_training["iforest_offset"],
            "total_seconds": anomaly_training["total_seconds"],
        }
    except Exception:
        context["error"] = traceback.format_exc()
        status = "FAILED"

    _write_evaluation_report(context, final_checks, inventory, status)

    if verbose:
        print("\n" + "=" * 78)
        print(f"PHASE 4 PIPELINE STATUS: {status}")
        print(
            f"Duration: "
            f"{(datetime.now(UTC) - started_utc).total_seconds():.2f} seconds"
        )
        print(f"Report:   {REPORT_PATH.relative_to(PROJECT_ROOT)}")
        print("=" * 78)

    return {
        "status": status,
        "stages": context["stages"],
        "error": context["error"],
        "report": str(REPORT_PATH.relative_to(PROJECT_ROOT)),
        "forecasting": context["forecasting"],
        "anomaly": context["anomaly"],
    }


def main() -> int:
    """Run the complete Phase 4 pipeline from the command line."""
    result = run_pipeline(verbose=True)
    return 0 if result["status"] in {"PASSED", "PASSED WITH WARNINGS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
