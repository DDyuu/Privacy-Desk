from app.llm.env_keys import detect_env_keys, mask_key, normalize_names


def test_mask_key_keeps_edges_only():
    masked = mask_key("sk-1234567890abcdef")
    assert masked == "sk-1****cdef"
    assert "1234567890ab" not in masked
    assert mask_key("short") == "*****"


def test_normalize_names_filters_invalid_and_dedupes():
    assert normalize_names([" MY_KEY ", "MY_KEY", "1BAD", "", "A-B"]) == ["MY_KEY"]


def test_detect_env_keys_follows_order_and_masks(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-123456")
    monkeypatch.setenv("CUSTOM_LLM_KEY", "sk-custom-abcdef")
    items = detect_env_keys(["CUSTOM_LLM_KEY"])
    assert [item["name"] for item in items] == ["DEEPSEEK_API_KEY", "CUSTOM_LLM_KEY"]
    assert items[0]["provider"] == "DeepSeek"
    assert "sk-deepseek-123456" not in items[0]["masked"]


def test_settings_fallbacks_to_env_key(unlocked_client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-secret-9876")
    response = unlocked_client.get("/api/v1/settings/llm")
    body = response.json()
    assert body["has_key"] is True
    assert body["mode"] == "online"
    assert body["key_source"] == "env:DEEPSEEK_API_KEY"
    assert body["env_keys"][0]["active"] is True
    assert body["env_keys"][0]["masked"].startswith("sk-e")
    assert "sk-env-secret-9876" not in response.text


def test_stored_key_wins_over_env(unlocked_client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-secret")
    unlocked_client.put(
        "/api/v1/settings/llm",
        json={
            "mode": "online",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-stored-secret",
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "qwen2.5:7b",
        },
    )
    body = unlocked_client.get("/api/v1/settings/llm").json()
    assert body["key_source"] == "stored"
    assert all(not item["active"] for item in body["env_keys"])


def test_saving_does_not_persist_env_key(unlocked_client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-only")
    unlocked_client.put(
        "/api/v1/settings/llm",
        json={
            "mode": "online",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "",
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "qwen2.5:7b",
        },
    )
    assert unlocked_client.get("/api/v1/settings/llm").json()["key_source"] == (
        "env:DEEPSEEK_API_KEY"
    )

    monkeypatch.delenv("DEEPSEEK_API_KEY")
    after = unlocked_client.get("/api/v1/settings/llm").json()
    assert after["has_key"] is False
    assert after["key_source"] == "none"


def test_detect_endpoint_previews_unsaved_names(unlocked_client, monkeypatch):
    monkeypatch.setenv("MY_LLM_KEY", "sk-preview-secret")
    response = unlocked_client.get("/api/v1/settings/llm/env-keys?names=MY_LLM_KEY")
    body = response.json()
    assert body["key_source"] == "env:MY_LLM_KEY"
    assert body["has_key"] is True
    assert [item["name"] for item in body["env_keys"]] == ["MY_LLM_KEY"]
    assert body["env_keys"][0]["active"] is True
    assert "sk-preview-secret" not in response.text

    empty = unlocked_client.get("/api/v1/settings/llm/env-keys?names=").json()
    assert empty["env_keys"] == []
    assert empty["key_source"] == "none"


def test_custom_env_names_are_saved_and_detected(unlocked_client, monkeypatch):
    monkeypatch.setenv("MY_LLM_KEY", "sk-custom-secret")
    saved = unlocked_client.put(
        "/api/v1/settings/llm",
        json={
            "mode": "online",
            "base_url": "https://example.com/v1",
            "model": "custom-model",
            "api_key": "",
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "qwen2.5:7b",
            "env_key_names": ["MY_LLM_KEY", "MY_LLM_KEY", "1BAD"],
        },
    )
    body = saved.json()
    assert body["env_key_names"] == ["MY_LLM_KEY"]
    assert body["key_source"] == "env:MY_LLM_KEY"
    assert [item["name"] for item in body["env_keys"]] == ["MY_LLM_KEY"]
    assert "sk-custom-secret" not in saved.text
