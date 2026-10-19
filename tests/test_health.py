"""Health endpoint contract: the console and compose healthchecks read this."""

from fastapi.testclient import TestClient


def test_health_returns_ok_status() -> None:
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "firstshift-backend"
