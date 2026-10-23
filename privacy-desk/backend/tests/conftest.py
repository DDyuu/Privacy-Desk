import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, llm_api_key=None))
    return TestClient(app)


@pytest.fixture
def unlocked_client(client):
    response = client.post("/api/v1/session/setup", json={"password": "password123"})
    assert response.status_code == 200
    return client
