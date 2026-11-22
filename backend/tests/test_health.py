"""Health, readiness and documentation checks against the test database."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_root_exposes_api_metadata(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["docs"] == "/docs"
    assert payload["redoc"] == "/redoc"
    assert payload["health"] == "/api/v1/health"


def test_liveness_does_not_depend_on_the_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "EcoPulse AI API"
    assert payload["version"] == "0.2.0"


@pytest.mark.requires_models
def test_health_reports_database_and_models(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["environment"] == "test"
    assert payload["checks"]["api"]["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["forecast_model"]["status"] == "ok"
    assert payload["checks"]["anomaly_model"]["status"] == "ok"
    assert "Random Forest" in payload["checks"]["forecast_model"]["detail"]
    assert "Isolation Forest" in payload["checks"]["anomaly_model"]["detail"]


@pytest.mark.requires_models
def test_readiness_is_ok_with_all_dependencies(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_and_rendered_documentation(client: TestClient) -> None:
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/api/v1/energy" in paths
    assert "/api/v1/forecasts/predict" in paths
    assert "/api/v1/anomalies/detect" in paths
    assert "/api/v1/analytics/overview" in paths

    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()

    redoc = client.get("/redoc")
    assert redoc.status_code == 200
    assert "redoc" in redoc.text.lower()
