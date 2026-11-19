"""Evaluate the Phase 4 forecasting candidates and produce evidence artefacts.

Metrics are recomputed from the saved prediction table rather than copied from
training.  Model selection is reconstructed from validation RMSE.  The test
period is reported only for final evaluation and is never used to re-rank the
candidates for deployment.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACHINE_LEARNING_DIR = PROJECT_ROOT / "machine-learning"
ML_DATA_DIR = PROJECT_ROOT / "data" / "processed" / "ml"
MODEL_DIR = MACHINE_LEARNING_DIR / "models" / "forecasting"
REPORT_DIR = PROJECT_ROOT / "reports" / "machine-learning"
FIGURE_DIR = REPORT_DIR / "figures"

if str(MACHINE_LEARNING_DIR) not in sys.path:
    sys.path.insert(0, str(MACHINE_LEARNING_DIR))

from utils.features import FORECAST_FEATURES, TARGET_COLUMN  # noqa: E402
from utils.metrics import (  # noqa: E402
    format_metric,
    improvement_pct,
    metrics_by_group,
    regression_metrics,
)
from utils.validation import (  # noqa: E402
    FAIL,
    check_lines,
    validate_forecasting_model_artifact,
)

PROJECT_NAME = "EcoPulse AI"
FORECAST_DATASET_PATH = ML_DATA_DIR / "forecasting_dataset.parquet"
PREDICTIONS_PATH = ML_DATA_DIR / "forecasting_predictions.parquet"
TRAINING_SUMMARY_PATH = ML_DATA_DIR / "forecasting_training_summary.json"
BEST_MODEL_PATH = MODEL_DIR / "best_forecasting_model.joblib"
METADATA_PATH = MODEL_DIR / "forecasting_metadata.json"
FEATURES_PATH = MODEL_DIR / "forecasting_features.json"

METRICS_CSV = REPORT_DIR / "forecasting_metrics.csv"
COMPARISON_CSV = REPORT_DIR / "forecasting_comparison.csv"
REPORT_PATH = REPORT_DIR / "forecasting_report.txt"

SPLIT_ORDER = {"train": 0, "validation": 1, "test": 2}
PALETTE = "tab10"


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON document."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_figure(figure: plt.Figure, filename: str) -> Path:
    """Save one figure in the shared report folder."""
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURE_DIR / filename
    figure.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return path


def _metric_table_lines(
    metrics: pd.DataFrame,
    split: str,
    model_order: list[str],
) -> list[str]:
    """Format one split's metrics as a fixed-width text table."""
    lines = [
        f"{'Model':<24}{'MAE':>9}{'RMSE':>9}{'R2':>9}{'MAPE %':>10}{'sMAPE %':>10}",
        "-" * 71,
    ]
    subset = metrics.loc[metrics["split"] == split].set_index("model")
    for model_name in model_order:
        if model_name not in subset.index:
            continue
        row = subset.loc[model_name]
        r2 = "N/A" if pd.isna(row["r2"]) else f"{row['r2']:.4f}"
        mape = "N/A" if pd.isna(row["mape_pct"]) else f"{row['mape_pct']:.2f}"
        smape = "N/A" if pd.isna(row["smape_pct"]) else f"{row['smape_pct']:.2f}"
        lines.append(
            f"{model_name:<24}{row['mae']:>9.4f}{row['rmse']:>9.4f}"
            f"{r2:>9}{mape:>10}{smape:>10}"
        )
    return lines


def _comparison_table(
    metrics: pd.DataFrame,
    training_summary: dict[str, Any],
) -> pd.DataFrame:
    """Build the validation-ranked comparison table, including test results."""
    validation = metrics.loc[metrics["split"] == "validation"].set_index("model")
    test = metrics.loc[metrics["split"] == "test"].set_index("model")
    model_order = list(training_summary["models"])
    validation_ranking = list(training_summary["validation_ranking"])
    naive_name = "Naive (lag 1)"
    seasonal_name = "Seasonal Naive (lag 24)"

    rows: list[dict[str, Any]] = []
    for model_name in model_order:
        validation_row = validation.loc[model_name]
        test_row = test.loc[model_name]
        rows.append(
            {
                "model": model_name,
                "validation_rank": validation_ranking.index(model_name) + 1,
                "selected_best": model_name == training_summary["best_model"],
                "train_seconds": float(
                    training_summary["training_seconds"].get(model_name, 0.0)
                ),
                "validation_mae": validation_row["mae"],
                "validation_rmse": validation_row["rmse"],
                "validation_r2": validation_row["r2"],
                "validation_mape_pct": validation_row["mape_pct"],
                "validation_smape_pct": validation_row["smape_pct"],
                "test_mae": test_row["mae"],
                "test_rmse": test_row["rmse"],
                "test_r2": test_row["r2"],
                "test_mape_pct": test_row["mape_pct"],
                "test_smape_pct": test_row["smape_pct"],
                "validation_rmse_improvement_vs_naive_pct": improvement_pct(
                    validation.loc[naive_name, "rmse"], validation_row["rmse"]
                ),
                "test_rmse_improvement_vs_naive_pct": improvement_pct(
                    test.loc[naive_name, "rmse"], test_row["rmse"]
                ),
                "validation_rmse_improvement_vs_seasonal_pct": improvement_pct(
                    validation.loc[seasonal_name, "rmse"], validation_row["rmse"]
                ),
                "test_rmse_improvement_vs_seasonal_pct": improvement_pct(
                    test.loc[seasonal_name, "rmse"], test_row["rmse"]
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("validation_rank").reset_index(drop=True)


def _plot_actual_vs_predicted(
    best_name: str,
    test_predictions: pd.DataFrame,
    test_metrics: dict[str, Any],
    model_colors: dict[str, Any],
) -> Path:
    """Scatter actual against predicted values for the selected model."""
    figure, axis = plt.subplots(figsize=(7.2, 6.2))
    hexbin = axis.hexbin(
        test_predictions["actual"],
        test_predictions["predicted"],
        gridsize=38,
        cmap="viridis",
        mincnt=1,
        linewidths=0.2,
    )
    maximum = float(
        max(test_predictions["actual"].max(), test_predictions["predicted"].max())
    )
    minimum = float(
        min(test_predictions["actual"].min(), test_predictions["predicted"].min())
    )
    axis.plot(
        [minimum, maximum],
        [minimum, maximum],
        color="crimson",
        linestyle="--",
        linewidth=1.2,
        label="Perfect forecast",
    )
    axis.set_xlabel("Actual hourly energy (kWh)")
    axis.set_ylabel("Predicted hourly energy (kWh)")
    axis.set_title(
        f"{best_name}: actual vs predicted (test)\n"
        f"MAE {test_metrics['mae']:.4f} kWh | RMSE {test_metrics['rmse']:.4f} kWh"
    )
    axis.legend(loc="upper left")
    figure.colorbar(hexbin, ax=axis, label="Hours")
    figure.tight_layout()
    return _save_figure(figure, "forecasting_actual_vs_predicted.png")


def _plot_model_comparison(
    metrics: pd.DataFrame,
    model_order: list[str],
    model_colors: dict[str, Any],
) -> Path:
    """Compare validation and test errors across all candidates."""
    plot_rows = []
    for model_name in model_order:
        for split in ("validation", "test"):
            row = metrics.loc[
                (metrics["model"] == model_name) & (metrics["split"] == split)
            ].iloc[0]
            plot_rows.append(
                {
                    "Model": model_name,
                    "Split": split.title(),
                    "MAE": row["mae"],
                    "RMSE": row["rmse"],
                }
            )
    plot_frame = pd.DataFrame(plot_rows)
    figure, axes = plt.subplots(1, 2, figsize=(14, 5.6), sharey=False)
    for axis, metric in zip(axes, ("MAE", "RMSE"), strict=True):
        sns.barplot(
            data=plot_frame,
            x="Model",
            y=metric,
            hue="Split",
            palette={"Validation": "#4c72b0", "Test": "#dd8452"},
            ax=axis,
        )
        axis.set_title(f"{metric} by model and split")
        axis.set_xlabel("")
        axis.set_ylabel(f"{metric} (kWh)")
        axis.tick_params(axis="x", rotation=18)
        for container in axis.containers:
            axis.bar_label(container, fmt="%.3f", fontsize=7, padding=2)
        axis.legend(title="")
    figure.suptitle("Forecasting model comparison (test evaluated once after selection)")
    figure.tight_layout()
    return _save_figure(figure, "forecasting_model_comparison.png")


def _plot_error_distribution(
    predictions: pd.DataFrame,
    model_order: list[str],
    model_colors: dict[str, Any],
) -> Path:
    """Overlay test-error densities for all models on a shared clipped range."""
    test = predictions.loc[predictions["split"] == "test"].copy()
    test["error"] = test["predicted"] - test["actual"]
    lower, upper = np.percentile(test["error"], [1, 99])
    figure, axis = plt.subplots(figsize=(9.2, 5.4))
    for model_name in model_order:
        errors = test.loc[test["model"] == model_name, "error"]
        sns.kdeplot(
            errors,
            ax=axis,
            color=model_colors[model_name],
            label=model_name,
            linewidth=1.8,
            clip=(lower, upper),
        )
    axis.axvline(0.0, color="black", linestyle="--", linewidth=1.0)
    axis.set_xlim(lower, upper)
    axis.set_xlabel("Forecast error (predicted - actual, kWh)")
    axis.set_ylabel("Density")
    axis.set_title(
        "Test error distribution by model (density clipped to 1st-99th percentile)"
    )
    axis.legend()
    figure.tight_layout()
    return _save_figure(figure, "forecasting_error_distribution.png")


def _plot_residual_analysis(
    test_predictions: pd.DataFrame,
    best_name: str,
    model_colors: dict[str, Any],
) -> Path:
    """Show residual structure and distribution for the selected model."""
    residuals = test_predictions["predicted"] - test_predictions["actual"]
    color = model_colors[best_name]
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.2))
    axes[0].scatter(
        test_predictions["predicted"],
        residuals,
        s=10,
        alpha=0.35,
        color=color,
        edgecolors="none",
    )
    axes[0].axhline(0.0, color="black", linestyle="--", linewidth=1.0)
    axes[0].set_xlabel("Predicted energy (kWh)")
    axes[0].set_ylabel("Residual (predicted - actual, kWh)")
    axes[0].set_title("Residuals vs predicted values")
    sns.histplot(
        residuals,
        bins=60,
        kde=True,
        color=color,
        ax=axes[1],
        edgecolor="white",
        linewidth=0.4,
    )
    axes[1].axvline(
        float(residuals.mean()),
        color="crimson",
        linestyle="--",
        linewidth=1.2,
        label=f"Mean {residuals.mean():.4f}",
    )
    axes[1].axvline(0.0, color="black", linestyle=":", linewidth=1.0)
    axes[1].set_xlabel("Residual (kWh)")
    axes[1].set_ylabel("Hours")
    axes[1].set_title(
        f"Residual distribution | std {residuals.std(ddof=0):.4f} kWh"
    )
    axes[1].legend()
    figure.suptitle(f"{best_name}: test residual analysis")
    figure.tight_layout()
    return _save_figure(figure, "forecasting_residual_analysis.png")


def _plot_performance_over_time(
    test_predictions: pd.DataFrame,
    best_name: str,
    model_colors: dict[str, Any],
) -> Path:
    """Plot test forecasts over time and monthly RMSE for the best model."""
    ordered = test_predictions.sort_values("timestamp")
    monthly = ordered.assign(month=ordered["timestamp"].dt.to_period("M")).copy()
    monthly["squared_error"] = (monthly["predicted"] - monthly["actual"]) ** 2
    monthly_rmse = (
        monthly.groupby("month", observed=True)["squared_error"]
        .mean()
        .pow(0.5)
        .rename("rmse")
        .reset_index()
    )
    monthly_rmse["month_label"] = monthly_rmse["month"].astype(str)
    color = model_colors[best_name]

    figure, axes = plt.subplots(2, 1, figsize=(14, 8.2), sharex=False)
    axes[0].plot(
        ordered["timestamp"],
        ordered["actual"],
        color="#4b5563",
        linewidth=0.8,
        alpha=0.85,
        label="Actual",
    )
    axes[0].plot(
        ordered["timestamp"],
        ordered["predicted"],
        color=color,
        linewidth=0.8,
        alpha=0.8,
        label="Predicted",
    )
    axes[0].set_ylabel("Hourly energy (kWh)")
    axes[0].set_title(f"{best_name}: forecasts across the full test period")
    axes[0].legend(loc="upper right")

    axes[1].bar(
        monthly_rmse["month_label"],
        monthly_rmse["rmse"],
        color=color,
        alpha=0.85,
    )
    axes[1].set_ylabel("Monthly RMSE (kWh)")
    axes[1].set_xlabel("Test month")
    axes[1].set_title("Monthly forecast RMSE in the held-out test period")
    axes[1].tick_params(axis="x", rotation=30)
    for position, value in enumerate(monthly_rmse["rmse"]):
        axes[1].text(
            position,
            value,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=7,
        )
    figure.tight_layout()
    return _save_figure(figure, "forecasting_performance_over_time.png")


def _feature_importance(
    bundle: dict[str, Any],
    validation_features: pd.DataFrame,
    validation_target: np.ndarray,
) -> tuple[pd.Series, str]:
    """Return feature importance scores and the method used."""
    model = bundle["model"]
    if isinstance(model, Pipeline):
        regressor = model.named_steps["regressor"]
        if hasattr(regressor, "coef_"):
            coefficients = np.asarray(regressor.coef_, dtype=float)
            return (
                pd.Series(np.abs(coefficients), index=FORECAST_FEATURES).sort_values(
                    ascending=False
                ),
                "absolute standardised linear coefficients",
            )

    if hasattr(model, "feature_importances_"):
        return (
            pd.Series(
                np.asarray(model.feature_importances_, dtype=float),
                index=FORECAST_FEATURES,
            ).sort_values(ascending=False),
            "native impurity-based importance",
        )

    sample_size = min(3000, len(validation_features))
    sample = validation_features.iloc[-sample_size:]
    target = validation_target[-sample_size:]
    importance = permutation_importance(
        model,
        sample,
        target,
        n_repeats=5,
        random_state=42,
        scoring="neg_root_mean_squared_error",
        n_jobs=-1,
    )
    return (
        pd.Series(importance.importances_mean, index=FORECAST_FEATURES).sort_values(
            ascending=False
        ),
        f"permutation importance on the last {sample_size:,} validation rows",
    )


def _plot_feature_importance(
    importance: pd.Series,
    method: str,
    best_name: str,
    model_colors: dict[str, Any],
) -> Path:
    """Plot the 15 most important features for the selected model."""
    top = importance.head(15).sort_values(ascending=True)
    figure, axis = plt.subplots(figsize=(8.6, 6.2))
    axis.barh(top.index, top.to_numpy(), color=model_colors[best_name], alpha=0.85)
    axis.set_xlabel("Importance")
    axis.set_title(f"{best_name}: feature importance\n{method}")
    figure.tight_layout()
    return _save_figure(figure, "forecasting_feature_importance.png")


def run_evaluation(verbose: bool = True) -> dict[str, Any]:
    """Evaluate saved predictions, write reports and create real figures."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    for path in (
        FORECAST_DATASET_PATH,
        PREDICTIONS_PATH,
        TRAINING_SUMMARY_PATH,
        BEST_MODEL_PATH,
        METADATA_PATH,
        FEATURES_PATH,
    ):
        if not path.is_file():
            raise FileNotFoundError(
                f"Required forecasting artefact is missing: {path}. Run the earlier stages."
            )

    forecast = pd.read_parquet(FORECAST_DATASET_PATH)
    predictions = pd.read_parquet(PREDICTIONS_PATH)
    training_summary = _load_json(TRAINING_SUMMARY_PATH)
    metadata = _load_json(METADATA_PATH)
    feature_document = _load_json(FEATURES_PATH)
    bundle = joblib.load(BEST_MODEL_PATH)

    model_order = list(training_summary["models"])
    best_name = str(training_summary["best_model"])
    test_frame = forecast.loc[
        (forecast["is_modeling_row"]) & (forecast["split"] == "test")
    ].sort_values("timestamp")
    validation_frame = forecast.loc[
        (forecast["is_modeling_row"]) & (forecast["split"] == "validation")
    ].sort_values("timestamp")

    checks = validate_forecasting_model_artifact(
        BEST_MODEL_PATH,
        METADATA_PATH,
        FEATURES_PATH,
        predictions,
        best_name,
        FORECAST_FEATURES,
        feature_frame=test_frame,
    )
    if any(check.status == FAIL for check in checks):
        raise RuntimeError(
            "Saved forecasting model validation failed:\n"
            + "\n".join(check_lines(checks, include_passed=False))
        )

    expected_sizes = {
        split: int(len(forecast.loc[forecast["split"] == split]))
        for split in ("train", "validation", "test")
    }
    size_rows = []
    for model_name in model_order:
        for split in ("train", "validation", "test"):
            count = int(
                len(
                    predictions.loc[
                        (predictions["model"] == model_name)
                        & (predictions["split"] == split)
                    ]
                )
            )
            size_rows.append(
                {
                    "model": model_name,
                    "split": split,
                    "rows": count,
                    "expected": expected_sizes[split],
                }
            )
    size_frame = pd.DataFrame(size_rows)
    if (size_frame["rows"] != size_frame["expected"]).any():
        raise RuntimeError("Prediction row counts do not match the prepared split sizes.")
    if not np.isfinite(predictions["predicted"]).all():
        raise RuntimeError("Prediction table contains non-finite values.")

    metrics = metrics_by_group(predictions, ("model", "split"))
    metrics["split_order"] = metrics["split"].map(SPLIT_ORDER)
    metrics["model_order"] = metrics["model"].map(
        {name: index for index, name in enumerate(model_order)}
    )
    metrics = metrics.sort_values(["split_order", "model_order"]).drop(
        columns=["split_order", "model_order"]
    )
    metrics.to_csv(METRICS_CSV, index=False, float_format="%.6f")

    comparison = _comparison_table(metrics, training_summary)
    comparison.to_csv(COMPARISON_CSV, index=False, float_format="%.6f")

    validation_ranking = sorted(
        model_order,
        key=lambda name: (
            float(
                metrics.loc[
                    (metrics["model"] == name) & (metrics["split"] == "validation"),
                    "rmse",
                ].iloc[0]
            ),
            float(
                metrics.loc[
                    (metrics["model"] == name) & (metrics["split"] == "validation"),
                    "mae",
                ].iloc[0]
            ),
        ),
    )
    if validation_ranking[0] != best_name:
        raise RuntimeError(
            "The stored best model does not match the validation RMSE ranking."
        )

    best_validation = metrics.loc[
        (metrics["model"] == best_name) & (metrics["split"] == "validation")
    ].iloc[0]
    best_test = metrics.loc[
        (metrics["model"] == best_name) & (metrics["split"] == "test")
    ].iloc[0]
    test_sorted = metrics.loc[metrics["split"] == "test"].sort_values("rmse")
    lowest_test_model = str(test_sorted.iloc[0]["model"])
    seasonal_validation_rmse = float(
        metrics.loc[
            (metrics["model"] == "Seasonal Naive (lag 24)")
            & (metrics["split"] == "validation"),
            "rmse",
        ].iloc[0]
    )
    seasonal_test_rmse = float(
        metrics.loc[
            (metrics["model"] == "Seasonal Naive (lag 24)")
            & (metrics["split"] == "test"),
            "rmse",
        ].iloc[0]
    )
    improvement_validation = improvement_pct(
        seasonal_validation_rmse, float(best_validation["rmse"])
    )
    improvement_test = improvement_pct(
        seasonal_test_rmse, float(best_test["rmse"])
    )

    model_colors = dict(
        zip(model_order, sns.color_palette(PALETTE, n_colors=len(model_order)), strict=True)
    )
    best_test_predictions = predictions.loc[
        (predictions["model"] == best_name) & (predictions["split"] == "test")
    ].sort_values("timestamp")
    if best_test_predictions.empty:
        raise RuntimeError("No test predictions are available for the selected model.")

    figure_paths = [
        _plot_actual_vs_predicted(
            best_name,
            best_test_predictions,
            regression_metrics(
                best_test_predictions["actual"], best_test_predictions["predicted"]
            ),
            model_colors,
        ),
        _plot_model_comparison(metrics, model_order, model_colors),
        _plot_error_distribution(predictions, model_order, model_colors),
        _plot_residual_analysis(best_test_predictions, best_name, model_colors),
        _plot_performance_over_time(best_test_predictions, best_name, model_colors),
    ]

    importance, importance_method = _feature_importance(
        bundle,
        validation_frame[FORECAST_FEATURES],
        validation_frame[TARGET_COLUMN].to_numpy(dtype=float),
    )
    figure_paths.append(
        _plot_feature_importance(
            importance,
            importance_method,
            best_name,
            model_colors,
        )
    )

    target_values = forecast.loc[forecast["is_modeling_row"], TARGET_COLUMN]
    lines: list[str] = []

    def add(line: str = "") -> None:
        lines.append(line)

    add("=" * 78)
    add("ECOPULSE AI - PHASE 4 FORECASTING REPORT")
    add("=" * 78)
    add(f"Generated (UTC): {datetime.now(UTC).isoformat()}")
    add("Dataset: Individual Household Electric Power Consumption")
    add("Scope: hourly energy forecasting only; no anomaly-detection results here.")
    add("")
    add("1. DATASET AND TARGET")
    add("-" * 78)
    add(f"Source hourly intervals:       {len(forecast):,}")
    add(f"Supervised modelling rows:     {len(target_values):,}")
    add(
        "Target:                        total_energy_consumption_kwh for complete "
        "clock-hours"
    )
    add(
        "Target rule:                   exactly 60 valid one-minute observations; "
        "incomplete/partial hours are NaN"
    )
    add(
        f"Target range (modelling rows): {target_values.min():.4f} - "
        f"{target_values.max():.4f} kWh"
    )
    add(
        f"Target mean / median:          {target_values.mean():.4f} / "
        f"{target_values.median():.4f} kWh"
    )
    add(f"Prepared dataset:              {FORECAST_DATASET_PATH.relative_to(PROJECT_ROOT)}")
    add(f"Prepared dataset SHA-256:      {metadata['dataset_sha256']}")
    add(
        "Excluded before supervision:   feature warm-up and hours without a complete "
        "60-minute target"
    )
    add("")
    add("2. FEATURES")
    add("-" * 78)
    add(f"Feature count: {len(FORECAST_FEATURES)}")
    add("Time features:      " + ", ".join(feature_document["feature_groups"]["time"]))
    add(
        "Cyclical features:  "
        + ", ".join(feature_document["feature_groups"]["cyclical"])
    )
    add("Lag features:       " + ", ".join(feature_document["feature_groups"]["lag"]))
    add(
        "Rolling features:   "
        + ", ".join(feature_document["feature_groups"]["rolling"])
    )
    add(f"Causality:          {feature_document['causality']}")
    add("")
    add("3. CHRONOLOGICAL SPLIT")
    add("-" * 78)
    add(f"{'Split':<12}{'Rows':>9}  {'Start':<20}{'End':<20}{'Share':>8}")
    add("-" * 78)
    for row in training_summary["splits"]:
        add(
            f"{row['split']:<12}{row['rows']:>9,}  {row['start'][:19]:<20}"
            f"{row['end'][:19]:<20}{row['rows'] / len(target_values) * 100:>7.2f}%"
        )
    add(
        "Policy: 70% train / 15% validation / 15% test assigned by chronological "
        "row position."
    )
    add(
        "No shuffling, no overlap, and the validation split alone drives model "
        "selection."
    )
    add("")
    add("4. MODELS")
    add("-" * 78)
    for model_name in model_order:
        add(
            f"{model_name:<24} {training_summary['model_descriptions'][model_name]}"
        )
    add("")
    add("5. TRAIN METRICS (reference only)")
    add("-" * 78)
    for line in _metric_table_lines(metrics, "train", model_order):
        add(line)
    add("")
    add("6. VALIDATION METRICS AND RANKING")
    add("-" * 78)
    for line in _metric_table_lines(metrics, "validation", model_order):
        add(line)
    add("")
    add("Ranking by validation RMSE (lower is better):")
    for position, model_name in enumerate(validation_ranking, start=1):
        row = metrics.loc[
            (metrics["model"] == model_name) & (metrics["split"] == "validation")
        ].iloc[0]
        add(
            f"  {position}. {model_name:<24} RMSE {row['rmse']:.4f} | "
            f"MAE {row['mae']:.4f}"
        )
    add("")
    add("7. ONE-TIME TEST EVALUATION")
    add("-" * 78)
    add(
        "The test split was predicted only after the validation-based selection. "
        "All test metrics below are reported for final evaluation; they did not "
        "influence the selected model."
    )
    add("")
    for line in _metric_table_lines(metrics, "test", model_order):
        add(line)
    add("")
    add("8. SELECTED MODEL")
    add("-" * 78)
    add(f"Selected model:        {best_name}")
    add("Selection metric:      validation RMSE")
    add(
        f"Validation MAE / RMSE: {best_validation['mae']:.4f} / "
        f"{best_validation['rmse']:.4f} kWh"
    )
    add(
        f"Validation R2 / sMAPE: {format_metric(best_validation['r2'])} / "
        f"{best_validation['smape_pct']:.2f}%"
    )
    add(
        f"Test MAE / RMSE:       {best_test['mae']:.4f} / "
        f"{best_test['rmse']:.4f} kWh"
    )
    add(
        f"Test R2 / sMAPE:       {format_metric(best_test['r2'])} / "
        f"{best_test['smape_pct']:.2f}%"
    )
    add(
        f"Validation gain vs seasonal naive: {improvement_validation:.2f}% lower RMSE"
    )
    add(f"Test gain vs seasonal naive:       {improvement_test:.2f}% lower RMSE")
    add(f"Lowest test RMSE model:            {lowest_test_model} (reported, not selected)")
    add("")
    add("9. KEY FINDINGS")
    add("-" * 78)
    add(
        f"- {best_name} produced the lowest validation RMSE "
        f"({best_validation['rmse']:.4f} kWh), so it is the persisted model."
    )
    if improvement_validation > 0:
        add(
            f"- The selected model reduced validation RMSE by "
            f"{improvement_validation:.2f}% versus the 24-hour seasonal naive "
            f"baseline."
        )
    else:
        add(
            f"- The selected model did not beat the seasonal naive baseline on "
            f"validation RMSE; the negative gain is reported honestly."
        )
    add(
        f"- On the held-out test period the selected model reached R2 "
        f"{format_metric(best_test['r2'])} with MAE {best_test['mae']:.4f} kWh."
    )
    add(
        "- MAPE is defined for every evaluated sample because all complete-hour "
        "targets are non-zero; sMAPE is also reported because MAPE is sensitive "
        "when consumption is close to zero."
    )
    if lowest_test_model != best_name:
        add(
            f"- {lowest_test_model} had a lower test RMSE than the selected model. "
            "This is a passive observation after the one-time test evaluation and "
            "was not used to change the model."
        )
    else:
        add(
            f"- The validation-selected model also had the lowest test RMSE, which "
            "supports the selection."
        )
    add("")
    add("10. LIMITATIONS")
    add("-" * 78)
    add("- The experiment forecasts one hour ahead from observed history; recursive")
    add("  multi-day forecasts were not evaluated.")
    add("- The household data contain no weather, occupancy, holiday or tariff")
    add("  variables, so exogenous drivers are absent.")
    add("- Only one household (France, 2006-2010) is modelled; results do not")
    add("  automatically generalise to other homes or regions.")
    add(
        f"- Feature warm-up and incomplete hours remove "
        f"{len(forecast) - len(target_values):,} hourly rows; the remaining rows "
        f"are not a random sample of the original period."
    )
    add("- A single chronological hold-out is used, not rolling-origin backtesting.")
    add("- Hyperparameters were fixed a priori; no exhaustive tuning was performed.")
    add("- Random Forest and HistGradientBoosting cannot extrapolate to consumption")
    add("  levels outside their training range.")
    add("- MAPE divides by actual consumption and becomes unstable for very small")
    add("  hourly values even when it is mathematically defined.")
    add("")
    add("11. FIGURES AND ARTEFACTS")
    add("-" * 78)
    add(f"Metrics CSV:      {METRICS_CSV.relative_to(PROJECT_ROOT)}")
    add(f"Comparison CSV:   {COMPARISON_CSV.relative_to(PROJECT_ROOT)}")
    add(f"Best model:       {BEST_MODEL_PATH.relative_to(PROJECT_ROOT)}")
    add(f"Metadata:         {METADATA_PATH.relative_to(PROJECT_ROOT)}")
    add(f"Feature list:     {FEATURES_PATH.relative_to(PROJECT_ROOT)}")
    if (MODEL_DIR / "forecasting_preprocessor.joblib").exists():
        add(
            "Preprocessor:     "
            + str(
                (MODEL_DIR / "forecasting_preprocessor.joblib").relative_to(
                    PROJECT_ROOT
                )
            )
        )
    else:
        add("Preprocessor:     none required by the selected model")
    for path in figure_paths:
        add(f"Figure:           {path.relative_to(PROJECT_ROOT)}")
    add("")
    add("12. REPRODUCIBILITY AND VERIFICATION")
    add("-" * 78)
    add(f"Random seed:      {training_summary['random_seed']}")
    add(f"Model version:    {training_summary['model_version']}")
    add(
        "Saved-model check: reloaded Joblib bundle reproduces stored test "
        "predictions and metadata metrics."
    )
    for line in check_lines(checks, include_passed=True):
        add(line)
    add("")
    add("Final forecasting evaluation status: PASSED")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if verbose:
        print("=" * 78)
        print(f"{PROJECT_NAME.upper()} - PHASE 4 FORECASTING EVALUATION")
        print("=" * 78)
        add_summary = (
            f"Best model: {best_name} | validation RMSE "
            f"{best_validation['rmse']:.4f} | test RMSE {best_test['rmse']:.4f}"
        )
        print(add_summary)
        print(
            f"Test MAE {best_test['mae']:.4f} kWh | R2 "
            f"{format_metric(best_test['r2'])} | sMAPE "
            f"{best_test['smape_pct']:.2f}%"
        )
        for line in check_lines(checks):
            print("  " + line)
        print(f"Report: {REPORT_PATH.relative_to(PROJECT_ROOT)}")
        print(f"Figures: {len(figure_paths)} written to {FIGURE_DIR.relative_to(PROJECT_ROOT)}")

    return {
        "best_model": best_name,
        "validation_metrics": best_validation.to_dict(),
        "test_metrics": best_test.to_dict(),
        "validation_ranking": validation_ranking,
        "figures": [str(path.relative_to(PROJECT_ROOT)) for path in figure_paths],
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
            }
            for check in checks
        ],
        "metrics_csv": str(METRICS_CSV.relative_to(PROJECT_ROOT)),
        "comparison_csv": str(COMPARISON_CSV.relative_to(PROJECT_ROOT)),
        "report": str(REPORT_PATH.relative_to(PROJECT_ROOT)),
    }


def main() -> int:
    """Evaluate forecasting models from the command line."""
    try:
        result = run_evaluation(verbose=True)
    except Exception as error:  # pragma: no cover - surfaced with a clear message
        print(f"\nERROR: {error}")
        return 1
    print(f"\nPhase 4 forecasting evaluation status: PASSED ({result['best_model']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
