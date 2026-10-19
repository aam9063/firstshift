"""Prometheus scrape endpoint contract: the metrics stack reads this."""


def test_metrics_exposes_prometheus_format() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "python_info" in response.text
