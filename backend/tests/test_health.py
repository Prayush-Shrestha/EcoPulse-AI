from datetime import datetime

from fastapi.testclient import TestClient


def test_root_exposes_local_api_metadata(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["docs"] == "/docs"
    assert payload["health"] == "/api/v1/health"


def test_liveness_does_not_depend_on_the_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "EcoPulse AI API"
    assert payload["version"] == "0.1.0"


def test_aggregate_health_reports_ok_when_database_responds(
    healthy_client: TestClient,
) -> None:
    response = healthy_client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["api"]["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["database"]["latency_ms"] >= 0
    assert payload["checks"]["database"]["detail"] is None

    timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    assert timestamp.tzinfo is not None


def test_aggregate_health_degrades_without_failing_the_request(
    unavailable_client: TestClient,
) -> None:
    response = unavailable_client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["api"]["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "unavailable"
    assert payload["checks"]["database"]["detail"] == "Database check failed."


def test_readiness_returns_ok_for_a_healthy_database(
    healthy_client: TestClient,
) -> None:
    response = healthy_client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_returns_503_for_an_unavailable_database(
    unavailable_client: TestClient,
) -> None:
    response = unavailable_client.get("/api/v1/health/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["database"]["status"] == "unavailable"


def test_cors_allows_the_local_frontend(healthy_client: TestClient) -> None:
    response = healthy_client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
