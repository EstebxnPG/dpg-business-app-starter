from fastapi.testclient import TestClient

from app import main
from app.main import app


def test_health_endpoint_is_available() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_rejects_unavailable_database(monkeypatch) -> None:
    monkeypatch.setattr(main, "database_ready", lambda: False)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_readiness_accepts_available_database(monkeypatch) -> None:
    monkeypatch.setattr(main, "database_ready", lambda: True)

    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
