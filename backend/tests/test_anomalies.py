"""Anomaly detection, persistence, filtering and summary endpoints."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

API = "/api/v1/anomalies"
PHASE4_ANOMALY_SCORE_2101 = 0.222983405
PHASE4_ANOMALY_SCORE_1920 = -0.018904202

pytestmark = pytest.mark.requires_models


def _reading(frame: pd.DataFrame, timestamp: str) -> pd.Series:
    rows = frame.loc[frame["timestamp"] == pd.Timestamp(timestamp)]
    assert len(rows) == 1, timestamp
    return rows.iloc[0]


def test_detect_scores_stored_observation_with_phase4_model(
    client: TestClient,
    seeded: dict[str, Any],
) -> None:
    response = client.post(
        f"{API}/detect",
        json={"observation_timestamp": "2010-11-26T21:01:00"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["observation_timestamp"] == "2010-11-26T21:01:00"
    assert payload["anomaly_score"] == pytest.approx(
        PHASE4_ANOMALY_SCORE_2101, abs=1e-5
    )
    assert payload["detection_method"] == "isolation_forest"
    assert payload["threshold"] == 0.0
    assert payload["is_anomaly"] is False
    assert payload["severity"] == "none"
    assert payload["model_name"] == "Isolation Forest"
    assert payload["model_version"] == "1.0.0"
    assert "not a confirmed" in payload["label_status"]
    assert payload["energy_consumption_kwh"] > 0

    row = _reading(seeded["frame"], "2010-11-26T21:01:00")
    assert payload["energy_consumption_kwh"] == pytest.approx(
        float(row["energy_consumption_kwh"]), abs=1e-9
    )


def test_detect_flags_a_known_phase4_deviation(
    client: TestClient,
) -> None:
    response = client.post(
        f"{API}/detect",
        json={"observation_timestamp": "2010-11-20T19:05:00"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["is_anomaly"] is True
    assert payload["severity"] == "low"
    assert payload["anomaly_score"] == pytest.approx(
        PHASE4_ANOMALY_SCORE_1920, abs=1e-5
    )


def test_explicit_measurements_do_not_require_a_stored_reading(
    client: TestClient,
    seeded: dict[str, Any],
) -> None:
    row = _reading(seeded["frame"], "2010-11-26T21:01:00")
    payload = {
        "observation_timestamp": "2010-11-26T21:01:00",
        "measurements": {
            "global_active_power": float(row["Global_active_power"]),
            "global_reactive_power": float(row["Global_reactive_power"]),
            "voltage": float(row["Voltage"]),
            "global_intensity": float(row["Global_intensity"]),
            "sub_metering_1": float(row["Sub_metering_1"]),
            "sub_metering_2": float(row["Sub_metering_2"]),
            "sub_metering_3": float(row["Sub_metering_3"]),
        },
    }

    response = client.post(f"{API}/detect", json=payload)

    assert response.status_code == 201
    result = response.json()
    assert result["anomaly_score"] == pytest.approx(
        PHASE4_ANOMALY_SCORE_2101, abs=1e-5
    )
    # energy_consumption_kwh is persisted as Numeric(18, 9), so compare at
    # the column's nine-decimal precision rather than float-exact.
    assert result["energy_consumption_kwh"] == pytest.approx(
        float(row["Global_active_power"]) / 60.0, abs=1e-9
    )


def test_history_and_summary_reflect_detections(client: TestClient) -> None:
    assert client.post(
        f"{API}/detect",
        json={"observation_timestamp": "2010-11-26T21:01:00"},
    ).status_code == 201
    assert client.post(
        f"{API}/detect",
        json={"observation_timestamp": "2010-11-20T19:05:00"},
    ).status_code == 201

    history = client.get(API)
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["total"] == 2
    assert len(history_payload["items"]) == 2

    anomalies_only = client.get(API, params={"is_anomaly": True})
    assert anomalies_only.status_code == 200
    assert anomalies_only.json()["total"] == 1
    assert anomalies_only.json()["items"][0]["severity"] == "low"

    summary = client.get(f"{API}/summary")
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert len(summary_payload["methods"]) == 1
    method = summary_payload["methods"][0]
    assert method["detection_method"] == "isolation_forest"
    assert method["total_observations"] == 2
    assert method["total_anomalies"] == 1
    assert method["anomaly_percentage"] == pytest.approx(50.0)
    assert method["start_timestamp"] == "2010-11-20T19:05:00"
    assert method["end_timestamp"] == "2010-11-26T21:01:00"
    assert "no labelled" in summary_payload["label_status"].lower()


def test_missing_observation_returns_not_found(client: TestClient) -> None:
    response = client.post(
        f"{API}/detect",
        json={"observation_timestamp": "2010-11-27T00:00:00"},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "not_found"
    assert "No energy reading" in payload["error"]["message"]


def test_insufficient_history_is_reported_safely(client: TestClient) -> None:
    response = client.post(
        f"{API}/detect",
        json={
            "observation_timestamp": "2010-11-15T00:10:00",
            "measurements": {
                "global_active_power": 1.0,
                "global_reactive_power": 0.1,
                "voltage": 240.0,
                "global_intensity": 4.0,
                "sub_metering_1": 0.0,
                "sub_metering_2": 0.0,
                "sub_metering_3": 0.0,
            },
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "insufficient_history"
    assert "24-hour" in payload["error"]["message"]


def test_observation_timestamp_must_be_minute_aligned(client: TestClient) -> None:
    response = client.post(
        f"{API}/detect",
        json={"observation_timestamp": "2010-11-26T21:01:30"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert "whole minute" in payload["error"]["details"][0]["message"]


def test_timezone_aware_observation_is_rejected(client: TestClient) -> None:
    response = client.post(
        f"{API}/detect",
        json={"observation_timestamp": "2010-11-26T21:01:00Z"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert "naive local civil timestamp" in payload["error"]["details"][0]["message"]
