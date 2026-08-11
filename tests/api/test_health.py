"""System endpoint tests."""

from fastapi.testclient import TestClient


def test_health_reports_foundational_dependencies(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["runtime_mode"] == "UNINITIALIZED"
    assert body["version"] == "0.2.0"


def test_version_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json()["api_version"] == "v1"
