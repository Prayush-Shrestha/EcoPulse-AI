"""Energy listing, summary and aggregation endpoints."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

API = "/api/v1/energy"


def _frame(seeded: dict[str, Any]) -> pd.DataFrame:
    return seeded["frame"]


def test_list_readings_paginates_and_sorts(
    client: TestClient,
    seeded: dict[str, Any],
) -> None:
    frame = _frame(seeded)

    ascending = client.get(API, params={"limit": 5, "offset": 2, "order": "asc"})
    assert ascending.status_code == 200
    payload = ascending.json()
    assert payload["total"] == seeded["rows"]
    assert payload["limit"] == 5
    assert payload["offset"] == 2
    timestamps = [item["timestamp"] for item in payload["items"]]
    expected = [
        stamp.isoformat()
        for stamp in frame["timestamp"].sort_values().iloc[2:7]
    ]
    assert timestamps == expected
    assert payload["items"][0]["is_imputed"] in (True, False)

    descending = client.get(API, params={"limit": 3, "order": "desc"})
    assert descending.status_code == 200
    assert [item["timestamp"] for item in descending.json()["items"]] == [
        stamp.isoformat() for stamp in frame["timestamp"].sort_values(ascending=False).iloc[:3]
    ]


def test_list_readings_filters_by_time(
    client: TestClient,
    seeded: dict[str, Any],
) -> None:
    frame = _frame(seeded)
    start = pd.Timestamp("2010-11-26T00:00:00")
    end = pd.Timestamp("2010-11-26T23:59:59")
    expected = frame.loc[(frame["timestamp"] >= start) & (frame["timestamp"] <= end)]

    response = client.get(
        API,
        params={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": 5000,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == len(expected)
    assert len(payload["items"]) == len(expected)
    assert all(
        start.isoformat() <= item["timestamp"] <= "2010-11-26T23:59:59"
        for item in payload["items"]
    )


def test_summary_matches_seeded_observations(
    client: TestClient,
    seeded: dict[str, Any],
) -> None:
    response = client.get(f"{API}/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_observations"] == seeded["rows"]
    assert payload["total_consumption_kwh"] == pytest.approx(
        seeded["total_energy_kwh"], abs=1e-4
    )
    assert payload["average_consumption_kwh"] == pytest.approx(
        seeded["total_energy_kwh"] / seeded["rows"], abs=1e-9
    )
    assert payload["maximum_consumption_kwh"] == pytest.approx(
        seeded["maximum_energy_kwh"], abs=1e-9
    )
    assert payload["minimum_consumption_kwh"] == pytest.approx(
        seeded["minimum_energy_kwh"], abs=1e-9
    )
    assert payload["start_timestamp"] == seeded["start"].isoformat()
    assert payload["end_timestamp"] == seeded["end"].isoformat()
    assert payload["units"] == "kWh"


def test_hourly_aggregation_marks_partial_boundary_hours(
    client: TestClient,
    seeded: dict[str, Any],
) -> None:
    response = client.get(
        f"{API}/hourly",
        params={
            "start": "2010-11-26T00:00:00",
            "end": "2010-11-26T21:02:00",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["granularity"] == "hourly"
    assert len(payload["items"]) == 22
    assert payload["items"][0]["period_start"] == "2010-11-26T00:00:00"
    assert payload["items"][0]["is_complete"] is True
    assert payload["items"][-1]["period_start"] == "2010-11-26T21:00:00"
    assert payload["items"][-1]["observation_count"] == 3
    assert payload["items"][-1]["expected_observations"] == 60
    assert payload["items"][-1]["is_complete"] is False

    expected_total = _frame(seeded).loc[
        (_frame(seeded)["timestamp"] >= pd.Timestamp("2010-11-26T00:00:00"))
        & (_frame(seeded)["timestamp"] <= pd.Timestamp("2010-11-26T21:02:00")),
        "energy_consumption_kwh",
    ].sum()
    assert sum(item["consumption_kwh"] for item in payload["items"]) == pytest.approx(
        float(expected_total), abs=1e-6
    )


def test_daily_and_monthly_aggregation(
    client: TestClient,
    seeded: dict[str, Any],
) -> None:
    daily = client.get(f"{API}/daily", params={"limit": 100})
    assert daily.status_code == 200
    daily_payload = daily.json()
    assert daily_payload["granularity"] == "daily"
    assert daily_payload["total"] == 12
    assert daily_payload["items"][0]["period_start"] == "2010-11-15T00:00:00"
    assert daily_payload["items"][-1]["observation_count"] == 1263

    monthly = client.get(f"{API}/monthly", params={"limit": 100})
    assert monthly.status_code == 200
    monthly_payload = monthly.json()
    assert monthly_payload["granularity"] == "monthly"
    assert monthly_payload["total"] == 1
    assert monthly_payload["items"][0]["period_start"] == "2010-11-01T00:00:00"
    assert monthly_payload["items"][0]["observation_count"] == seeded["rows"]
    assert monthly_payload["items"][0]["consumption_kwh"] == pytest.approx(
        seeded["total_energy_kwh"], abs=1e-4
    )


def test_invalid_date_filter_is_rejected(client: TestClient) -> None:
    response = client.get(
        API,
        params={
            "start": "2010-11-26T00:00:00+00:00",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert "naive local civil timestamp" in payload["error"]["details"][0]["message"]
