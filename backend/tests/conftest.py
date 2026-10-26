import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_llm_env(monkeypatch):
    """避免开发机上的环境变量干扰配置相关断言。"""
    for name in ("PRIVACY_DESK_LLM_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, llm_api_key=None))
    return TestClient(app)


@pytest.fixture
def unlocked_client(client):
    response = client.post("/api/v1/session/setup", json={"password": "password123"})
    assert response.status_code == 200
    return client
