import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_enforce_integrity_without_manifest_fails(tmp_path):
    with pytest.raises(RuntimeError, match="完整性清单"):
        create_app(Settings(data_dir=tmp_path / "data", enforce_integrity=True))


def test_require_token_without_token_fails(tmp_path):
    with pytest.raises(RuntimeError, match="APP_TOKEN"):
        create_app(Settings(data_dir=tmp_path / "data", require_token=True))


def test_token_guard_allows_cors_preflight(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data", app_token="secret")))
    assert client.get("/api/v1/health").status_code == 401

    preflight = client.options(
        "/api/v1/session/status",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-app-token",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") in {
        "*",
        "http://localhost:5173",
    }
    assert (
        client.get("/api/v1/health", headers={"X-App-Token": "secret"}).status_code == 200
    )
