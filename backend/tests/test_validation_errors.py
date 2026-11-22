"""Validation, error envelopes and dependency-failure handling."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.session import get_db
from app.main import app
from app.ml.model_loader import ModelRegistry, get_model_registry


def test_invalid_time_range_returns_a_safe_error(client: TestClient) -> None:
    response = client.get(
        "/api/v1/energy",
        params={
            "start": "2010-11-26T00:00:00",
            "end": "2010-11-15T00:00:00",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert "must not be after" in payload["error"]["message"]


def test_query_limits_are_validated(client: TestClient) -> None:
    response = client.get("/api/v1/energy", params={"limit": 0})

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert "limit" in payload["error"]["details"][0]["location"]


def test_unknown_route_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "not_found"
    assert "detail" not in payload


def test_forecast_history_range_is_validated(client: TestClient) -> None:
    response = client.get(
        "/api/v1/forecasts/history",
        params={
            "start": "2010-11-26T00:00:00",
            "end": "2010-11-15T00:00:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


class BrokenSession:
    def execute(self, *args: object, **kwargs: object) -> object:
        raise SQLAlchemyError("simulated database outage")

    def scalar(self, *args: object, **kwargs: object) -> object:
        raise SQLAlchemyError("simulated database outage")


def test_database_failure_returns_503_without_internals(client: TestClient) -> None:
    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        response = client.get("/api/v1/energy/summary")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "database_unavailable"
    assert "simulated" not in payload["error"]["message"].lower()
    assert "traceback" not in response.text.lower()


def test_missing_model_returns_503(
    client: TestClient,
    tmp_path: Path,
) -> None:
    registry = ModelRegistry(Settings(ml_models_dir=str(tmp_path / "absent")))
    registry.load()
    app.dependency_overrides[get_model_registry] = lambda: registry
    try:
        response = client.post(
            "/api/v1/forecasts/predict",
            json={"horizon_hours": 1, "base_timestamp": "2010-11-26T19:00:00"},
        )
    finally:
        app.dependency_overrides.pop(get_model_registry, None)

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "model_unavailable"
    assert payload["error"]["details"]["reason"]
    assert "traceback" not in response.text.lower()


def test_request_id_header_is_preserved(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "phase5-test-request"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "phase5-test-request"

    generated = client.get("/api/v1/health/live")
    assert len(generated.headers["X-Request-ID"]) == 32


def test_validation_errors_do_not_expose_stack_traces(client: TestClient) -> None:
    response = client.post(
        "/api/v1/forecasts/predict",
        json={"horizon_hours": -1},
    )

    assert response.status_code == 422
    assert "traceback" not in response.text.lower()
    assert response.json()["error"]["code"] == "validation_error"
