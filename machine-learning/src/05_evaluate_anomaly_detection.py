"""Evaluate the Phase 4 anomaly detectors using counts, scores and patterns.

No ground-truth labels exist, so this stage deliberately avoids accuracy,
precision, recall and F1.  It compares detection volume, agreement, temporal
patterns and score distributions, and it visualises flagged minutes against the
observed load without calling them confirmed faults.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACHINE_LEARNING_DIR = PROJECT_ROOT / "machine-learning"
ML_DATA_DIR = PROJECT_ROOT / "data" / "processed" / "ml"
MODEL_DIR = MACHINE_LEARNING_DIR / "models" / "anomaly_detection"
REPORT_DIR = PROJECT_ROOT / "reports" / "machine-learning"
FIGURE_DIR = REPORT_DIR / "figures"

if str(MACHINE_LEARNING_DIR) not in sys.path:
    sys.path.insert(0, str(MACHINE_LEARNING_DIR))

from utils.features import ANOMALY_FEATURES  # noqa: E402
from utils.validation import (  # noqa: E402
    FAIL,
    check_lines,
    validate_anomaly_model_artifact,
)

PROJECT_NAME = "EcoPulse AI"
ANOMALY_DATASET_PATH = ML_DATA_DIR / "anomaly_dataset.parquet"
PREDICTIONS_PATH = ML_DATA_DIR / "anomaly_predictions.parquet"
TRAINING_SUMMARY_PATH = ML_DATA_DIR / "anomaly_training_summary.json"
MODEL_PATH = MODEL_DIR / "isolation_forest.joblib"
SCALER_PATH = MODEL_DIR / "anomaly_scaler.joblib"
METADATA_PATH = MODEL_DIR / "anomaly_metadata.json"
FEATURES_PATH = MODEL_DIR / "anomaly_features.json"

SUMMARY_CSV = REPORT_DIR / "anomaly_summary.csv"
REPORT_PATH = REPORT_DIR / "anomaly_detection_report.txt"

ZSCORE_METHOD = "Rolling z-score (|z| >= 3.0)"
IFOREST_METHOD = "Isolation Forest (contamination=0.005)"
SPLITS = ("train", "validation", "test")
IFOREST_COLOR = "#c0392b"
ZSCORE_COLOR = "#e67e22"
NORMAL_COLOR = "#9aa5b1"


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


def _count_table(predictions: pd.DataFrame) -> pd.DataFrame:
    """Build one row per detection method with overall and split counts."""
    rows: list[dict[str, Any]] = []
    for method, column in (
        (ZSCORE_METHOD, "zscore_anomaly"),
        (IFOREST_METHOD, "isolation_forest_anomaly"),
    ):
        row: dict[str, Any] = {
            "detection_method": method,
            "total_observations": int(len(predictions)),
            "detected_anomalies": int(predictions[column].sum()),
            "anomaly_percentage": float(predictions[column].mean() * 100.0),
        }
        for split in SPLITS:
            part = predictions.loc[predictions["split"] == split, column]
            row[f"{split}_observations"] = int(len(part))
            row[f"{split}_anomalies"] = int(part.sum())
            row[f"{split}_anomaly_percentage"] = float(part.mean() * 100.0)
        rows.append(row)
    return pd.DataFrame(rows)


def _overlap_table(predictions: pd.DataFrame) -> dict[str, Any]:
    """Quantify agreement between the two unsupervised methods."""
    iforest = predictions["isolation_forest_anomaly"].to_numpy(dtype=bool)
    zscore = predictions["zscore_anomaly"].to_numpy(dtype=bool)
    both = int(np.count_nonzero(iforest & zscore))
    only_iforest = int(np.count_nonzero(iforest & ~zscore))
    only_zscore = int(np.count_nonzero(~iforest & zscore))
    neither = int(np.count_nonzero(~iforest & ~zscore))
    union = both + only_iforest + only_zscore
    return {
        "both": both,
        "only_iforest": only_iforest,
        "only_zscore": only_zscore,
        "neither": neither,
        "union": union,
        "jaccard_pct": both / union * 100.0 if union else 0.0,
        "overlap_of_iforest_pct": (
            both / int(iforest.sum()) * 100.0 if iforest.any() else 0.0
        ),
        "overlap_of_zscore_pct": (
            both / int(zscore.sum()) * 100.0 if zscore.any() else 0.0
        ),
    }


def _plot_timeline(predictions: pd.DataFrame) -> Path:
    """Highlight flagged minutes in the busiest test week."""
    test = predictions.loc[predictions["split"] == "test"].copy()
    test["date"] = test["timestamp"].dt.floor("D")
    daily = (
        test.assign(
            combined=test["isolation_forest_anomaly"].astype(int)
            + test["zscore_anomaly"].astype(int)
        )
        .groupby("date", observed=True)["combined"]
        .sum()
    )
    if daily.empty or daily.max() == 0:
        peak_date = test["timestamp"].min()
    else:
        peak_date = daily.idxmax()
    week_start = (peak_date - pd.DateOffset(days=3)).normalize()
    week_end = week_start + pd.DateOffset(days=7)
    window = test.loc[
        (test["timestamp"] >= week_start) & (test["timestamp"] < week_end)
    ].sort_values("timestamp")
    if window.empty:
        window = test.sort_values("timestamp").iloc[: 7 * 24 * 60]

    figure, axis = plt.subplots(figsize=(14, 5.6))
    axis.plot(
        window["timestamp"],
        window["Global_active_power"],
        color="#374151",
        linewidth=0.7,
        label="Global active power",
    )
    iforest_window = window.loc[window["isolation_forest_anomaly"]]
    zscore_window = window.loc[window["zscore_anomaly"]]
    axis.scatter(
        iforest_window["timestamp"],
        iforest_window["Global_active_power"],
        s=22,
        color=IFOREST_COLOR,
        label="Isolation Forest flag",
        zorder=3,
    )
    axis.scatter(
        zscore_window["timestamp"],
        zscore_window["Global_active_power"],
        s=16,
        facecolors="none",
        edgecolors=ZSCORE_COLOR,
        linewidths=0.8,
        label="Rolling z-score flag",
        zorder=2,
    )
    axis.set_ylabel("Global active power (kW)")
    axis.set_xlabel("Timestamp")
    axis.set_title(
        f"Detected deviation candidates in the busiest test week "
        f"({week_start.date()} to {week_end.date()})"
    )
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    axis.legend(loc="upper right")
    figure.tight_layout()
    return _save_figure(figure, "anomaly_consumption_timeline.png")


def _plot_distribution_over_time(predictions: pd.DataFrame, summary: dict[str, Any]) -> Path:
    """Show monthly anomaly percentages and chronological split boundaries."""
    frame = predictions.copy()
    frame["month"] = frame["timestamp"].dt.to_period("M")
    grouped = frame.groupby("month", observed=True).agg(
        rows=("timestamp", "size"),
        iforest=("isolation_forest_anomaly", "sum"),
        zscore=("zscore_anomaly", "sum"),
    )
    grouped["iforest_pct"] = grouped["iforest"] / grouped["rows"] * 100.0
    grouped["zscore_pct"] = grouped["zscore"] / grouped["rows"] * 100.0
    dates = grouped.index.to_timestamp()

    figure, axis = plt.subplots(figsize=(14, 5.4))
    axis.plot(
        dates,
        grouped["zscore_pct"],
        color=ZSCORE_COLOR,
        marker="o",
        markersize=3,
        linewidth=1.4,
        label=ZSCORE_METHOD,
    )
    axis.plot(
        dates,
        grouped["iforest_pct"],
        color=IFOREST_COLOR,
        marker="s",
        markersize=3,
        linewidth=1.4,
        label=IFOREST_METHOD,
    )
    for split, style in (("validation", "--"), ("test", ":")):
        boundary = predictions.loc[
            predictions["split"] == split, "timestamp"
        ].min()
        axis.axvline(
            boundary,
            color="#4b5563",
            linestyle=style,
            linewidth=1.0,
            label=f"{split.title()} starts",
        )
    axis.set_ylabel("Anomalies (% of monthly observations)")
    axis.set_xlabel("Month")
    axis.set_title("Monthly anomaly percentages by detection method")
    axis.legend(ncol=2)
    figure.tight_layout()
    return _save_figure(figure, "anomaly_distribution_over_time.png")


def _plot_score_distribution(predictions: pd.DataFrame) -> Path:
    """Plot Isolation Forest and z-score distributions with thresholds."""
    figure, axes = plt.subplots(1, 2, figsize=(14, 5.2))
    sns.histplot(
        predictions["isolation_forest_score"],
        bins=90,
        color=IFOREST_COLOR,
        ax=axes[0],
        edgecolor="white",
        linewidth=0.2,
    )
    axes[0].axvline(
        0.0,
        color="black",
        linestyle="--",
        linewidth=1.2,
        label="Flag threshold (decision < 0)",
    )
    axes[0].axvline(
        float(np.median(predictions["isolation_forest_score"])),
        color="#2563eb",
        linestyle=":",
        linewidth=1.0,
        label="Median",
    )
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Isolation Forest decision score")
    axes[0].set_ylabel("Minutes (log scale)")
    axes[0].set_title("Isolation Forest score distribution")
    axes[0].legend()

    z = predictions["gap_z_24h"].to_numpy(dtype=float)
    z_lower, z_upper = np.percentile(z, [0.1, 99.9])
    sns.histplot(
        z,
        bins=90,
        color=ZSCORE_COLOR,
        ax=axes[1],
        edgecolor="white",
        linewidth=0.2,
        element="bars",
    )
    for value, label in ((-3.0, "|z| = 3"), (3.0, None)):
        axes[1].axvline(
            value,
            color="black",
            linestyle="--",
            linewidth=1.0,
            label=label,
        )
    axes[1].set_xlim(max(z_lower, -8.0), min(z_upper, 8.0))
    axes[1].set_xlabel("Causal 24-hour rolling z-score of active power")
    axes[1].set_ylabel("Minutes")
    axes[1].set_title("Rolling z-score distribution")
    axes[1].legend()
    figure.suptitle("Anomaly score distributions (real scored observations)")
    figure.tight_layout()
    return _save_figure(figure, "anomaly_score_distribution.png")


def _plot_method_comparison(
    counts: pd.DataFrame,
    overlap: dict[str, Any],
) -> Path:
    """Compare detection rates by split and show flag agreement."""
    plot_rows = []
    for row in counts.itertuples(index=False):
        for split in SPLITS:
            plot_rows.append(
                {
                    "Method": "Isolation Forest" if "Isolation" in row.detection_method else "Rolling z-score",
                    "Split": split.title(),
                    "Percentage": getattr(row, f"{split}_anomaly_percentage"),
                }
            )
    plot_frame = pd.DataFrame(plot_rows)

    figure, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    sns.barplot(
        data=plot_frame,
        x="Split",
        y="Percentage",
        hue="Method",
        palette={"Isolation Forest": IFOREST_COLOR, "Rolling z-score": ZSCORE_COLOR},
        ax=axes[0],
    )
    for container in axes[0].containers:
        axes[0].bar_label(container, fmt="%.2f%%", fontsize=8, padding=2)
    axes[0].set_ylabel("Flagged observations (%)")
    axes[0].set_title("Detection rate by chronological split")

    matrix = np.array(
        [
            [overlap["neither"], overlap["only_zscore"]],
            [overlap["only_iforest"], overlap["both"]],
        ]
    )
    sns.heatmap(
        matrix,
        annot=True,
        fmt=",",
        cmap="YlOrRd",
        cbar=False,
        xticklabels=["z-score normal", "z-score flagged"],
        yticklabels=["IF normal", "IF flagged"],
        ax=axes[1],
    )
    axes[1].set_title(
        "Flag agreement (not accuracy)\n"
        f"Jaccard {overlap['jaccard_pct']:.2f}% | both {overlap['both']:,}"
    )
    figure.suptitle("Comparison of unsupervised detection methods")
    figure.tight_layout()
    return _save_figure(figure, "anomaly_method_comparison.png")


def _plot_profiles(predictions: pd.DataFrame) -> Path:
    """Show how detection rates vary by hour and weekday."""
    frame = predictions.copy()
    frame["hour"] = frame["timestamp"].dt.hour
    frame["weekday"] = frame["timestamp"].dt.day_name().str[:3]
    weekday_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    hourly = frame.groupby("hour", observed=True).agg(
        rows=("timestamp", "size"),
        iforest=("isolation_forest_anomaly", "sum"),
        zscore=("zscore_anomaly", "sum"),
    )
    hourly["iforest_pct"] = hourly["iforest"] / hourly["rows"] * 100.0
    hourly["zscore_pct"] = hourly["zscore"] / hourly["rows"] * 100.0

    weekdays = frame.groupby("weekday", observed=True).agg(
        rows=("timestamp", "size"),
        iforest=("isolation_forest_anomaly", "sum"),
        zscore=("zscore_anomaly", "sum"),
    ).reindex(weekday_order)
    weekdays["iforest_pct"] = weekdays["iforest"] / weekdays["rows"] * 100.0
    weekdays["zscore_pct"] = weekdays["zscore"] / weekdays["rows"] * 100.0

    figure, axes = plt.subplots(1, 2, figsize=(14, 5.2))
    axes[0].plot(
        hourly.index,
        hourly["zscore_pct"],
        marker="o",
        color=ZSCORE_COLOR,
        label="Rolling z-score",
    )
    axes[0].plot(
        hourly.index,
        hourly["iforest_pct"],
        marker="s",
        color=IFOREST_COLOR,
        label="Isolation Forest",
    )
    axes[0].set_xticks(range(0, 24, 2))
    axes[0].set_xlabel("Hour of day")
    axes[0].set_ylabel("Flagged observations (%)")
    axes[0].set_title("Anomaly percentage by hour")
    axes[0].legend()

    positions = np.arange(len(weekday_order))
    width = 0.38
    axes[1].bar(
        positions - width / 2,
        weekdays["zscore_pct"],
        width,
        color=ZSCORE_COLOR,
        label="Rolling z-score",
    )
    axes[1].bar(
        positions + width / 2,
        weekdays["iforest_pct"],
        width,
        color=IFOREST_COLOR,
        label="Isolation Forest",
    )
    axes[1].set_xticks(positions, weekday_order)
    axes[1].set_ylabel("Flagged observations (%)")
    axes[1].set_title("Anomaly percentage by weekday")
    axes[1].legend()
    figure.tight_layout()
    return _save_figure(figure, "anomaly_hourly_profile.png")


def _plot_normal_vs_anomalous(predictions: pd.DataFrame) -> Path:
    """Compare active power and voltage for normal and flagged observations."""
    rng = np.random.default_rng(42)
    normal = predictions.loc[
        ~predictions["isolation_forest_anomaly"] & ~predictions["zscore_anomaly"]
    ]
    sample_size = min(50_000, len(normal))
    positions = rng.choice(len(normal), size=sample_size, replace=False)
    normal_sample = normal.iloc[positions]
    only_iforest = predictions.loc[
        predictions["isolation_forest_anomaly"] & ~predictions["zscore_anomaly"]
    ]
    only_zscore = predictions.loc[
        ~predictions["isolation_forest_anomaly"] & predictions["zscore_anomaly"]
    ]
    both = predictions.loc[
        predictions["isolation_forest_anomaly"] & predictions["zscore_anomaly"]
    ]

    figure, axis = plt.subplots(figsize=(9.5, 6.2))
    axis.scatter(
        normal_sample["Global_active_power"],
        normal_sample["Voltage"],
        s=4,
        color=NORMAL_COLOR,
        alpha=0.18,
        label=f"Neither method (sample {sample_size:,})",
        edgecolors="none",
    )
    axis.scatter(
        only_zscore["Global_active_power"],
        only_zscore["Voltage"],
        s=6,
        color=ZSCORE_COLOR,
        alpha=0.35,
        label=f"z-score only ({len(only_zscore):,})",
        edgecolors="none",
    )
    axis.scatter(
        only_iforest["Global_active_power"],
        only_iforest["Voltage"],
        s=10,
        color=IFOREST_COLOR,
        alpha=0.55,
        label=f"Isolation Forest only ({len(only_iforest):,})",
        edgecolors="none",
    )
    axis.scatter(
        both["Global_active_power"],
        both["Voltage"],
        s=16,
        color="#6a1b9a",
        alpha=0.75,
        label=f"Both methods ({len(both):,})",
        edgecolors="none",
    )
    axis.set_xlabel("Global active power (kW)")
    axis.set_ylabel("Voltage (V)")
    axis.set_title(
        "Normal vs flagged observations\n"
        "Flags are statistical deviation candidates, not confirmed faults"
    )
    axis.legend(markerscale=2.0, fontsize=8)
    figure.tight_layout()
    return _save_figure(figure, "anomaly_normal_vs_anomalous.png")


def run_evaluation(verbose: bool = True) -> dict[str, Any]:
    """Evaluate anomaly flags, write the summary CSV, report and figures."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    for path in (
        ANOMALY_DATASET_PATH,
        PREDICTIONS_PATH,
        TRAINING_SUMMARY_PATH,
        MODEL_PATH,
        SCALER_PATH,
        METADATA_PATH,
        FEATURES_PATH,
    ):
        if not path.is_file():
            raise FileNotFoundError(
                f"Required anomaly artefact is missing: {path}. Run the earlier stages."
            )

    predictions = pd.read_parquet(PREDICTIONS_PATH)
    summary = _load_json(TRAINING_SUMMARY_PATH)
    metadata = _load_json(METADATA_PATH)
    feature_document = _load_json(FEATURES_PATH)
    if len(predictions) != int(summary["rows"]):
        raise RuntimeError("Anomaly prediction row count does not match the training summary.")
    if not predictions["timestamp"].is_monotonic_increasing:
        raise RuntimeError("Anomaly predictions are not chronologically sorted.")
    if predictions["timestamp"].duplicated().any():
        raise RuntimeError("Anomaly predictions contain duplicate timestamps.")

    feature_source = pd.read_parquet(
        ANOMALY_DATASET_PATH,
        columns=["timestamp", *ANOMALY_FEATURES],
        filters=[("split", "==", "test")],
    )
    checks = validate_anomaly_model_artifact(
        MODEL_PATH,
        SCALER_PATH,
        METADATA_PATH,
        FEATURES_PATH,
        predictions,
        ANOMALY_FEATURES,
        metadata["zscore_baseline"]["threshold"],
        feature_frame=feature_source,
    )
    del feature_source
    if any(check.status == FAIL for check in checks):
        raise RuntimeError(
            "Saved anomaly model validation failed:\n"
            + "\n".join(check_lines(checks, include_passed=False))
        )

    counts = _count_table(predictions)
    counts.to_csv(SUMMARY_CSV, index=False, float_format="%.6f")
    overlap = _overlap_table(predictions)

    recomputed_summary = {}
    for method, column in (
        ("iforest", "isolation_forest_anomaly"),
        ("zscore", "zscore_anomaly"),
    ):
        total = int(predictions[column].sum())
        expected_key = f"{method}_anomalies"
        if int(summary["overall"][expected_key]) != total:
            raise RuntimeError(
                f"Stored {method} anomaly count does not match the predictions."
            )
        recomputed_summary[method] = total
        for row in summary["split_counts"]:
            split_count = int(
                predictions.loc[predictions["split"] == row["split"], column].sum()
            )
            if split_count != int(row[f"{method}_anomalies"]):
                raise RuntimeError(
                    f"Stored {method} count for split {row['split']} is inconsistent."
                )

    frame = predictions.copy()
    frame["month"] = frame["timestamp"].dt.to_period("M").astype(str)
    monthly = frame.groupby("month", observed=True).agg(
        rows=("timestamp", "size"),
        iforest=("isolation_forest_anomaly", "sum"),
        zscore=("zscore_anomaly", "sum"),
    )
    monthly["iforest_pct"] = monthly["iforest"] / monthly["rows"] * 100.0
    monthly["zscore_pct"] = monthly["zscore"] / monthly["rows"] * 100.0
    top_iforest_month = monthly.sort_values(
        ["iforest_pct", "iforest"], ascending=False
    ).iloc[0]
    top_zscore_month = monthly.sort_values(
        ["zscore_pct", "zscore"], ascending=False
    ).iloc[0]

    frame["hour"] = frame["timestamp"].dt.hour
    hourly = frame.groupby("hour", observed=True).agg(
        rows=("timestamp", "size"),
        iforest=("isolation_forest_anomaly", "sum"),
        zscore=("zscore_anomaly", "sum"),
    )
    hourly["iforest_pct"] = hourly["iforest"] / hourly["rows"] * 100.0
    hourly["zscore_pct"] = hourly["zscore"] / hourly["rows"] * 100.0
    top_iforest_hour = hourly.sort_values(
        ["iforest_pct", "iforest"], ascending=False
    ).iloc[0]
    top_zscore_hour = hourly.sort_values(
        ["zscore_pct", "zscore"], ascending=False
    ).iloc[0]

    iforest_top = predictions.nsmallest(5, "isolation_forest_score")
    zscore_top = (
        predictions.assign(abs_z=predictions["gap_z_24h"].abs())
        .nlargest(5, "abs_z")
    )

    score_correlations = predictions[
        ["isolation_forest_score", "gap_z_24h"]
    ].corr(method="pearson")
    correlation = float(score_correlations.iloc[0, 1])

    figure_paths = [
        _plot_timeline(predictions),
        _plot_distribution_over_time(predictions, summary),
        _plot_score_distribution(predictions),
        _plot_method_comparison(counts, overlap),
        _plot_profiles(predictions),
        _plot_normal_vs_anomalous(predictions),
    ]

    lines: list[str] = []

    def add(line: str = "") -> None:
        lines.append(line)

    add("=" * 78)
    add("ECOPULSE AI - PHASE 4 ANOMALY DETECTION REPORT")
    add("=" * 78)
    add(f"Generated (UTC): {datetime.now(UTC).isoformat()}")
    add("Dataset: Individual Household Electric Power Consumption")
    add(
        "Scope: unsupervised anomaly detection only; no labelled accuracy is "
        "claimed."
    )
    add("")
    add("1. DATASET USED")
    add("-" * 78)
    add(f"Source:                    {metadata['dataset']}")
    add(
        f"Cleaned minute observations: {metadata['source']['cleaned_minutes']:,}"
    )
    add(
        f"Excluded before scoring:    "
        f"{metadata['source']['imputed_rows_excluded']:,} imputed rows + "
        f"{metadata['source']['warmup_or_gap_rows_excluded']:,} "
        f"warm-up/gap rows"
    )
    add(f"Usable minute observations: {summary['rows']:,}")
    add(
        f"Training rows:             {metadata['training_period']['rows']:,} "
        f"({metadata['training_period']['start']} -> {metadata['training_period']['end']})"
    )
    add(
        f"Validation rows:           {metadata['validation_period']['rows']:,} "
        f"({metadata['validation_period']['start']} -> {metadata['validation_period']['end']})"
    )
    add(
        f"Test rows:                 {metadata['test_period']['rows']:,} "
        f"({metadata['test_period']['start']} -> {metadata['test_period']['end']})"
    )
    add(
        "Exclusions:                interpolated minutes and rows without a full "
        "prior 24-hour baseline"
    )
    add("")
    add("2. FEATURES")
    add("-" * 78)
    for group, columns in feature_document["feature_groups"].items():
        add(f"{group.title():<12} " + ", ".join(columns))
    add(f"Causality: {feature_document['causality']}")
    add("")
    add("3. DETECTION METHODS")
    add("-" * 78)
    add("A. Rolling z-score baseline")
    add(
        "   |Global_active_power(t) - mean(previous 24h)| / std(previous 24h) "
        ">= 3.0"
    )
    add(
        "   The mean and standard deviation are shifted by one minute, use at least "
        "720 prior observations, and require no model fitting."
    )
    add("")
    add("B. Isolation Forest")
    add(
        f"   {metadata['isolation_forest']['n_estimators']} trees, "
        f"max_samples={metadata['isolation_forest']['max_samples']}, "
        f"contamination={metadata['contamination']:.2%}, "
        f"random_state={metadata['isolation_forest']['random_state']}"
    )
    add(
        "   StandardScaler and the forest are fitted on the training split only. "
        "The offset is derived from training scores."
    )
    add(
        f"   Training decision quantile at 0.5%: "
        f"{metadata['isolation_forest']['training_decision_quantile_0_005']:.6f} "
        f"(0 by construction)"
    )
    add(
        f"   Decision threshold:                 "
        f"{metadata['isolation_forest']['decision_threshold']:.6f}"
    )
    add(
        f"   Raw-score offset (offset_):         "
        f"{metadata['isolation_forest']['iforest_offset']:.6f}"
    )
    add(f"   Contamination rationale: {metadata['contamination_rationale']}")
    add("")
    add("4. DETECTION COUNTS")
    add("-" * 78)
    add(
        f"{'Method':<38}{'Total':>10}{'Flagged':>10}{'Percent':>10}"
    )
    add("-" * 78)
    for row in counts.itertuples(index=False):
        add(
            f"{row.detection_method:<38}{row.total_observations:>10,}"
            f"{row.detected_anomalies:>10,}{row.anomaly_percentage:>9.3f}%"
        )
    add("")
    add(
        f"{'Method':<38}{'Train %':>10}{'Val %':>10}{'Test %':>10}"
    )
    add("-" * 78)
    for row in counts.itertuples(index=False):
        add(
            f"{row.detection_method:<38}"
            f"{row.train_anomaly_percentage:>9.3f}%"
            f"{row.validation_anomaly_percentage:>9.3f}%"
            f"{row.test_anomaly_percentage:>9.3f}%"
        )
    add(
        "Note: Isolation Forest train flags are in-sample and are not comparable "
        "to validation/test detection rates."
    )
    add("")
    add("5. METHOD AGREEMENT")
    add("-" * 78)
    add(f"Flagged by both methods:       {overlap['both']:,}")
    add(f"Flagged by Isolation Forest only: {overlap['only_iforest']:,}")
    add(f"Flagged by rolling z-score only:  {overlap['only_zscore']:,}")
    add(f"Flagged by neither method:     {overlap['neither']:,}")
    add(f"Jaccard overlap:               {overlap['jaccard_pct']:.2f}%")
    add(
        f"Share of Isolation Forest flags also flagged by z-score: "
        f"{overlap['overlap_of_iforest_pct']:.2f}%"
    )
    add(
        f"Share of z-score flags also flagged by Isolation Forest: "
        f"{overlap['overlap_of_zscore_pct']:.2f}%"
    )
    add(f"Pearson correlation (IF score vs z-score): {correlation:.4f}")
    add("")
    add("6. TEMPORAL AND DAILY PATTERNS")
    add("-" * 78)
    add(
        f"Highest Isolation Forest month: {top_iforest_month.name} | "
        f"{int(top_iforest_month['iforest']):,} flags | "
        f"{top_iforest_month['iforest_pct']:.3f}%"
    )
    add(
        f"Highest z-score month:          {top_zscore_month.name} | "
        f"{int(top_zscore_month['zscore']):,} flags | "
        f"{top_zscore_month['zscore_pct']:.3f}%"
    )
    add(
        f"Highest Isolation Forest hour:  {int(top_iforest_hour.name):02d}:00 | "
        f"{top_iforest_hour['iforest_pct']:.3f}% of minutes"
    )
    add(
        f"Highest z-score hour:           {int(top_zscore_hour.name):02d}:00 | "
        f"{top_zscore_hour['zscore_pct']:.3f}% of minutes"
    )
    add("")
    add("7. EXAMPLE HIGH-SCORE OBSERVATIONS (investigation candidates)")
    add("-" * 78)
    add("Isolation Forest lowest decision scores:")
    add(
        f"{'Timestamp':<20}{'Split':<12}{'GAP kW':>9}{'Voltage V':>11}"
        f"{'z-score':>9}{'IF score':>11}"
    )
    for row in iforest_top.itertuples(index=False):
        add(
            f"{str(row.timestamp)[:19]:<20}{row.split:<12}"
            f"{row.Global_active_power:>9.3f}{row.Voltage:>11.2f}"
            f"{row.gap_z_24h:>9.3f}{row.isolation_forest_score:>11.4f}"
        )
    add("")
    add("Largest absolute rolling z-scores:")
    add(
        f"{'Timestamp':<20}{'Split':<12}{'GAP kW':>9}{'Voltage V':>11}"
        f"{'z-score':>9}{'IF score':>11}"
    )
    for row in zscore_top.itertuples(index=False):
        add(
            f"{str(row.timestamp)[:19]:<20}{row.split:<12}"
            f"{row.Global_active_power:>9.3f}{row.Voltage:>11.2f}"
            f"{row.gap_z_24h:>9.3f}{row.isolation_forest_score:>11.4f}"
        )
    add("")
    add("These are the most extreme scored minutes, not confirmed equipment faults.")
    add("")
    add("8. KEY OBSERVATIONS")
    add("-" * 78)
    add(
        f"- The rolling z-score flagged {summary['overall']['zscore_anomalies']:,} "
        f"minutes ({summary['overall']['zscore_percentage']:.3f}%), while the "
        f"Isolation Forest flagged {summary['overall']['iforest_anomalies']:,} "
        f"({summary['overall']['iforest_percentage']:.3f}%)."
    )
    add(
        f"- The methods agree on {overlap['both']:,} minutes "
        f"(Jaccard {overlap['jaccard_pct']:.2f}%), which is expected because they "
        f"model different notions of deviation."
    )
    add(
        f"- The z-score is univariate on active power; the Isolation Forest also "
        f"uses voltage, reactive power, intensity, sub-metering and calendar context."
    )
    add(
        f"- Detection percentages differ across splits; this reflects changing "
        f"household behaviour over four years as well as the train-only threshold."
    )
    add("")
    add("9. LIMITATIONS")
    add("-" * 78)
    add("- No reliable ground-truth anomaly labels exist. Accuracy, precision,")
    add("  recall and F1 are therefore not reported and would be fabricated.")
    add("- Detected observations are deviation candidates, not confirmed faults.")
    add("  A high reading can be normal behaviour; a fault can produce a normal")
    add("  reading.")
    add("- The Isolation Forest contamination setting is a prior assumption, not an")
    add("  estimated fault prevalence.")
    add("- The rolling z-score assumes approximate local stability and is sensitive")
    add("  to autocorrelation and heavy tails; the fixed 3.0 threshold is a")
    add("  convention, not a calibrated probability.")
    add("- Interpolated minutes were excluded, and long missing intervals are absent")
    add("  from the source, so gap-adjacent behaviour is under-represented.")
    add("- No weather, occupancy, appliance identity or tariff context is available.")
    add(
        "- Anomaly scores measure statistical deviation from learned patterns, not "
        "physical causation or fault severity."
    )
    add("")
    add("10. FIGURES AND ARTEFACTS")
    add("-" * 78)
    add(f"Summary CSV:    {SUMMARY_CSV.relative_to(PROJECT_ROOT)}")
    add(f"Model:          {MODEL_PATH.relative_to(PROJECT_ROOT)}")
    add(f"Scaler:         {SCALER_PATH.relative_to(PROJECT_ROOT)}")
    add(f"Metadata:       {METADATA_PATH.relative_to(PROJECT_ROOT)}")
    add(f"Feature list:   {FEATURES_PATH.relative_to(PROJECT_ROOT)}")
    for path in figure_paths:
        add(f"Figure:         {path.relative_to(PROJECT_ROOT)}")
    add("")
    add("11. VERIFICATION")
    add("-" * 78)
    add(
        "- Saved scaler and Isolation Forest reloaded and reproduced flags on a "
        "25,000-row test sample."
    )
    add("- Rolling z-score flags were recomputed from stored z-scores and matched.")
    add("- Counts in the training summary were reconciled with the prediction table.")
    for line in check_lines(checks, include_passed=True):
        add(line)
    add("")
    add("Final anomaly evaluation status: PASSED")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if verbose:
        print("=" * 78)
        print(f"{PROJECT_NAME.upper()} - PHASE 4 ANOMALY DETECTION EVALUATION")
        print("=" * 78)
        for row in counts.itertuples(index=False):
            print(
                f"{row.detection_method:<40} {row.detected_anomalies:>8,} "
                f"({row.anomaly_percentage:.3f}%)"
            )
        print(
            f"Agreement: both {overlap['both']:,} | Jaccard "
            f"{overlap['jaccard_pct']:.2f}% | correlation {correlation:.4f}"
        )
        for line in check_lines(checks):
            print("  " + line)
        print(f"Report: {REPORT_PATH.relative_to(PROJECT_ROOT)}")
        print(f"Figures: {len(figure_paths)} written to {FIGURE_DIR.relative_to(PROJECT_ROOT)}")

    return {
        "counts": counts.to_dict(orient="records"),
        "overlap": overlap,
        "correlation": correlation,
        "figures": [str(path.relative_to(PROJECT_ROOT)) for path in figure_paths],
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
            }
            for check in checks
        ],
        "summary_csv": str(SUMMARY_CSV.relative_to(PROJECT_ROOT)),
        "report": str(REPORT_PATH.relative_to(PROJECT_ROOT)),
    }


def main() -> int:
    """Evaluate anomaly detection from the command line."""
    try:
        result = run_evaluation(verbose=True)
    except Exception as error:  # pragma: no cover - surfaced with a clear message
        print(f"\nERROR: {error}")
        return 1
    print("\nPhase 4 anomaly evaluation status: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
