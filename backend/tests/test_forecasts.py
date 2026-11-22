"""Forecast inference, persistence and history endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

API = "/api/v1/forecasts"
PHASE4_FORECAST_TARGET_20 = 1.897491782047

pytestmark = pytest.mark.requires_models


def test_predict_uses_the_saved_phase4_model(client: TestClient) -> None:
    response = client.post(
        f"{API}/predict",
        json={"horizon_hours": 1, "base_timestamp": "2010-11-26T19:00:00"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["base_timestamp"] == "2010-11-26T19:00:00"
    assert payload["horizon_hours"] == 1
    assert payload["model_name"] == "Random Forest"
    assert payload["model_version"] == "1.0.0"
    assert payload["units"] == "kWh"
    assert len(payload["items"]) == 1

    point = payload["items"][0]
    assert point["forecast_timestamp"] == "2010-11-26T20:00:00"
    assert point["predicted_energy_kwh"] == pytest.approx(
        PHASE4_FORECAST_TARGET_20, abs=1e-5
    )
    assert point["predicted_energy_kwh"] > 0
    assert point["forecast_horizon"] == 1
    assert point["units"] == "kWh"


def test_prediction_is_persisted_and_exposed_in_history(
    client: TestClient,
) -> None:
    created = client.post(
        f"{API}/predict",
        json={"horizon_hours": 1, "base_timestamp": "2010-11-26T19:00:00"},
    )
    assert created.status_code == 201
    expected = created.json()["items"][0]["predicted_energy_kwh"]

    latest = client.get(f"{API}/latest")
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload["forecast_timestamp"] == "2010-11-26T20:00:00"
    assert latest_payload["predicted_energy_kwh"] == pytest.approx(expected, abs=1e-9)
    assert latest_payload["model_name"] == "Random Forest"

    history = client.get(f"{API}/history")
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["total"] == 1
    assert history_payload["items"][0]["id"] == latest_payload["id"]

    filtered = client.get(
        f"{API}/history",
        params={"forecast_horizon": 1, "model_name": "Random Forest"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1


def test_recursive_multi_step_forecast_is_ordered_and_positive(
    client: TestClient,
) -> None:
    response = client.post(
        f"{API}/predict",
        json={"horizon_hours": 6, "base_timestamp": "2010-11-26T19:00:00"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert len(payload["items"]) == 6
    timestamps = [point["forecast_timestamp"] for point in payload["items"]]
    assert timestamps == [
        "2010-11-26T20:00:00",
        "2010-11-26T21:00:00",
        "2010-11-26T22:00:00",
        "2010-11-26T23:00:00",
        "2010-11-27T00:00:00",
        "2010-11-27T01:00:00",
    ]
    assert all(point["predicted_energy_kwh"] >= 0 for point in payload["items"])
    assert all(point["forecast_horizon"] == 6 for point in payload["items"])

    history = client.get(f"{API}/history")
    assert history.status_code == 200
    assert history.json()["total"] == 6


def test_latest_base_timestamp_uses_the_last_complete_hour(
    client: TestClient,
) -> None:
    response = client.post(f"{API}/predict", json={"horizon_hours": 1})

    assert response.status_code == 201
    payload = response.json()
    assert payload["base_timestamp"] == "2010-11-26T20:00:00"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["forecast_timestamp"] == "2010-11-26T21:00:00"


def test_48_hour_horizon_is_supported(client: TestClient) -> None:
    response = client.post(
        f"{API}/predict",
        json={"horizon_hours": 48, "base_timestamp": "2010-11-26T19:00:00"},
    )

    assert response.status_code == 201
    items = response.json()["items"]
    assert len(items) == 48
    first = items[0]["forecast_timestamp"]
    last = items[-1]["forecast_timestamp"]
    assert first == "2010-11-26T20:00:00"
    assert last == "2010-11-28T19:00:00"
    assert all(point["predicted_energy_kwh"] >= 0 for point in items)


def test_incomplete_base_hour_is_rejected(client: TestClient) -> None:
    response = client.post(
        f"{API}/predict",
        json={"horizon_hours": 1, "base_timestamp": "2010-11-26T21:00:00"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["details"]["observation_count"] == 3
    assert payload["error"]["details"]["expected"] == 60


def test_unknown_base_hour_is_rejected(client: TestClient) -> None:
    response = client.post(
        f"{API}/predict",
        json={"horizon_hours": 1, "base_timestamp": "2010-11-27T01:00:00"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["details"]["observation_count"] == 0


def test_latest_returns_not_found_without_history(client: TestClient) -> None:
    response = client.get(f"{API}/latest")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "not_found"
    assert "No forecast" in payload["error"]["message"]


def test_invalid_horizon_is_rejected(client: TestClient) -> None:
    response = client.post(
        f"{API}/predict",
        json={"horizon_hours": 3, "base_timestamp": "2010-11-26T19:00:00"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert "horizon_hours" in payload["error"]["details"][0]["location"]


def test_base_timestamp_must_be_hour_aligned(client: TestClient) -> None:
    response = client.post(
        f"{API}/predict",
        json={"horizon_hours": 1, "base_timestamp": "2010-11-26T19:30:00"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert "clock-hour" in payload["error"]["details"][0]["message"]
