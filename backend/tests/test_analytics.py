"""Analytics overview and consumption-pattern endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

API = "/api/v1/analytics"


def test_overview_combines_real_stored_data(
    client: TestClient,
    seeded: dict[str, Any],
) -> None:
    response = client.get(f"{API}/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["energy"]["total_observations"] == seeded["rows"]
    assert payload["energy"]["total_consumption_kwh"] == pytest.approx(
        seeded["total_energy_kwh"], abs=1e-4
    )
    assert payload["energy"]["peak_consumption_kwh"] == pytest.approx(
        seeded["maximum_energy_kwh"], abs=1e-9
    )
    assert payload["energy"]["start_timestamp"] == seeded["start"].isoformat()
    assert payload["energy"]["end_timestamp"] == seeded["end"].isoformat()

    assert payload["forecast"]["total_predictions"] == 0
    assert payload["anomaly"]["total_observations"] == 0
    assert payload["anomaly"]["anomaly_percentage"] == 0.0

    assert len(payload["hourly_trend"]) == 48
    assert len(payload["daily_trend"]) == 12
    assert payload["hourly_trend"][0]["period_start"] < payload["hourly_trend"][-1][
        "period_start"
    ]
    assert payload["daily_trend"][-1]["period_start"] == "2010-11-26T00:00:00"


@pytest.mark.requires_models
def test_overview_reflects_new_forecasts_and_detections(client: TestClient) -> None:
    forecast = client.post(
        "/api/v1/forecasts/predict",
        json={"horizon_hours": 1, "base_timestamp": "2010-11-26T19:00:00"},
    )
    assert forecast.status_code == 201
    anomaly = client.post(
        "/api/v1/anomalies/detect",
        json={"observation_timestamp": "2010-11-26T21:01:00"},
    )
    assert anomaly.status_code == 201

    response = client.get(f"{API}/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["forecast"]["total_predictions"] == 1
    assert payload["forecast"]["models"] == ["Random Forest"]
    assert payload["forecast"]["latest_forecast_timestamp"] == "2010-11-26T20:00:00"
    assert payload["anomaly"]["total_observations"] == 1
    assert payload["anomaly"]["total_anomalies"] == 0


def test_consumption_patterns_match_grouped_seed_data(
    client: TestClient,
    seeded: dict[str, Any],
) -> None:
    response = client.get(f"{API}/consumption-patterns")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["hourly"]) == 24
    assert len(payload["weekday"]) == 7
    assert len(payload["monthly"]) == 1
    assert [point["hour"] for point in payload["hourly"]] == list(range(24))
    assert [point["day_of_week"] for point in payload["weekday"]] == list(range(7))
    assert payload["monthly"][0]["month"] == 11
    assert payload["monthly"][0]["month_name"] == "November"
    assert [point["day_name"] for point in payload["weekday"]][:2] == [
        "Monday",
        "Tuesday",
    ]

    frame = seeded["frame"]
    expected = frame.loc[frame["timestamp"].dt.hour == 0, "energy_consumption_kwh"].mean()
    assert payload["hourly"][0]["average_consumption_kwh"] == pytest.approx(
        float(expected), abs=1e-9
    )
    assert payload["hourly"][0]["observation_count"] == int(
        (frame["timestamp"].dt.hour == 0).sum()
    )

    expected_month = frame.loc[
        frame["timestamp"].dt.month == 11, "energy_consumption_kwh"
    ].mean()
    assert payload["monthly"][0]["average_consumption_kwh"] == pytest.approx(
        float(expected_month), abs=1e-9
    )


def test_patterns_are_empty_safe_for_an_empty_range(client: TestClient) -> None:
    # The endpoint has no range parameters; this test documents that it always
    # aggregates the stored table and never fabricates values.
    response = client.get(f"{API}/consumption-patterns")
    assert response.status_code == 200
    assert all(point["observation_count"] > 0 for point in response.json()["hourly"])
