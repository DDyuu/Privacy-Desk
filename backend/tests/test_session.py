from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_status_reports_uninitialized(client):
    body = client.get("/api/v1/session/status").json()
    assert body["initialized"] is False
    assert body["unlocked"] is False


def test_setup_then_lock_then_unlock(unlocked_client):
    client = unlocked_client
    status = client.get("/api/v1/session/status").json()
    assert status["initialized"] is True
    assert status["unlocked"] is True

    client.post("/api/v1/session/lock")
    assert client.get("/api/v1/session/status").json()["unlocked"] is False

    wrong = client.post("/api/v1/session/unlock", json={"password": "wrong-pass"})
    assert wrong.status_code == 401

    right = client.post("/api/v1/session/unlock", json={"password": "password123"})
    assert right.status_code == 200
    assert right.json()["unlocked"] is True


def test_setup_twice_returns_conflict(unlocked_client):
    response = unlocked_client.post(
        "/api/v1/session/setup", json={"password": "another-pass"}
    )
    assert response.status_code == 409


def test_short_password_rejected(client):
    response = client.post("/api/v1/session/setup", json={"password": "short"})
    assert response.status_code == 422


def test_app_token_guard(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, app_token="secret-token"))
    client = TestClient(app)
    assert client.get("/api/v1/health").status_code == 401
    assert (
        client.get("/api/v1/health", headers={"X-App-Token": "secret-token"}).status_code
        == 200
    )
