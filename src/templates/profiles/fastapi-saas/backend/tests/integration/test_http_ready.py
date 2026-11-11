"""`/ready` gercek veritabaniyla (ARCH-0002)."""

from fastapi.testclient import TestClient

from PKG_NAME.interface.http.app import create_app


def test_ready_is_green_against_the_test_database(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with TestClient(create_app()) as client:
        response = client.get("/ready", headers={"X-Request-Id": "ready-1"})
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"database": "ok", "schema": "ok"}
    assert response.headers["x-request-id"] == "ready-1"
