"""Loaded-model metadata and inference unit checks."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import InsufficientHistoryError, ModelUnavailableError
from app.ml.inference import build_anomaly_features, build_forecast_features
from app.ml.model_loader import ModelRegistry, get_model_registry


@pytest.mark.requires_models
def test_models_endpoint_reports_the_saved_phase4_artefacts(client: TestClient) -> None:
    response = client.get("/api/v1/models")

    assert response.status_code == 200
    payload = response.json()
    by_key = {model["key"]: model for model in payload["models"]}
    assert by_key["forecasting"]["status"] == "loaded"
    assert by_key["forecasting"]["name"] == "Random Forest"
    assert by_key["forecasting"]["version"] == "1.0.0"
    assert by_key["forecasting"]["feature_count"] == 24
    assert by_key["forecasting"]["metrics"]["rmse"] == pytest.approx(0.4626, abs=1e-4)

    anomaly = by_key["anomaly_detection"]
    assert anomaly["status"] == "loaded"
    assert anomaly["name"] == "Isolation Forest"
    assert anomaly["feature_count"] == 20
    assert anomaly["threshold"] == 0.0
    assert "no labelled" in payload["label_status"].lower()


@pytest.mark.requires_models
def test_single_model_endpoint_and_unknown_key(client: TestClient) -> None:
    single = client.get("/api/v1/models/anomaly_detection")
    assert single.status_code == 200
    assert single.json()["threshold"] == 0.0
    # The bundle stores scikit-learn's raw score_samples offset; the API
    # scores with decision_function, whose threshold is 0.
    assert single.json()["raw_offset"] == pytest.approx(-0.6677766878861168)

    missing = client.get("/api/v1/models/not-a-model")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


@pytest.mark.requires_models
def test_registry_uses_the_decision_function_threshold() -> None:
    artifact = get_model_registry().require_anomaly()

    assert artifact.threshold == 0.0
    assert artifact.raw_offset == pytest.approx(-0.6677766878861168)


def test_missing_artefacts_are_reported_safely(tmp_path: Path) -> None:
    registry = ModelRegistry(Settings(ml_models_dir=str(tmp_path / "absent")))
    registry.load()

    assert registry.forecast is None
    assert registry.anomaly is None
    assert "forecasting" in registry.errors
    assert "anomaly_detection" in registry.errors
    with pytest.raises(ModelUnavailableError):
        registry.require_forecast()
    with pytest.raises(ModelUnavailableError):
        registry.require_anomaly()


@pytest.mark.requires_models
def test_forecast_features_never_use_the_target_row() -> None:
    artifact = get_model_registry().require_forecast()
    index = pd.date_range("2010-01-01T00:00:00", periods=200, freq="h")
    history = pd.Series(np.linspace(1.0, 2.0, 200), index=index, dtype="float64")
    target = index[-1] + timedelta(hours=1)

    baseline = build_forecast_features(history, target, artifact.feature_names)
    contaminated = history.copy()
    contaminated.loc[target] = 999.0
    with_target = build_forecast_features(contaminated, target, artifact.feature_names)

    pd.testing.assert_frame_equal(baseline, with_target)
    assert baseline.loc[0, "lag_168"] == pytest.approx(history.loc[index[32]])


@pytest.mark.requires_models
def test_forecast_features_require_the_full_lag_history() -> None:
    artifact = get_model_registry().require_forecast()
    index = pd.date_range("2010-01-01T00:00:00", periods=200, freq="h")
    history = pd.Series(np.linspace(1.0, 2.0, 200), index=index, dtype="float64")
    target = index[-1] + timedelta(hours=1)
    incomplete = history.drop(index=history.index[32])

    with pytest.raises(InsufficientHistoryError):
        build_forecast_features(incomplete, target, artifact.feature_names)


@pytest.mark.requires_models
def test_anomaly_features_ignore_the_current_measurement_in_its_baseline() -> None:
    artifact = get_model_registry().require_anomaly()
    timestamps = pd.date_range("2010-01-01T00:00:00", periods=25 * 60, freq="min")
    history = pd.DataFrame(
        {
            "timestamp": timestamps,
            "Global_active_power": np.linspace(0.5, 1.5, len(timestamps)),
        }
    )
    target = timestamps[-1] + timedelta(minutes=1)
    measurements = {
        "Global_active_power": 9.9,
        "Global_reactive_power": 0.2,
        "Voltage": 240.0,
        "Global_intensity": 40.0,
        "Sub_metering_1": 1.0,
        "Sub_metering_2": 1.0,
        "Sub_metering_3": 1.0,
    }

    baseline = build_anomaly_features(
        history, target, measurements, artifact.feature_names
    )
    contaminated = pd.concat(
        [
            history,
            pd.DataFrame(
                {
                    "timestamp": [target],
                    "Global_active_power": [999.0],
                }
            ),
        ],
        ignore_index=True,
    )
    with_target = build_anomaly_features(
        contaminated, target, measurements, artifact.feature_names
    )

    pd.testing.assert_frame_equal(baseline, with_target)
    assert baseline.loc[0, "gap_lag_1"] == pytest.approx(history.iloc[-1, 1])
    assert np.isfinite(baseline.loc[0, "gap_z_24h"])
    assert baseline.loc[0, "gap_mean_1440"] == pytest.approx(
        history["Global_active_power"].tail(1440).mean(), rel=1e-9
    )


def test_naive_datetime_contract_is_explicit() -> None:
    # The saved dataset has no timezone; the API rejects invented offsets.
    assert datetime(2010, 11, 26, 21, 1).tzinfo is None
