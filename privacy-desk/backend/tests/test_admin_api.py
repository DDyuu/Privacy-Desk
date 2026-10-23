CUSTOM_TYPE = {
    "code": "EMP_NO",
    "name": "工号",
    "category": "custom",
    "level": "low",
    "builtin": False,
    "enabled": True,
    "detectors": [{"kind": "regex", "pattern": "EMP-\\d{4}"}],
    "defaultAction": "mask",
    "actionOptions": {"keepPrefix": 0, "keepSuffix": 2},
}


def test_builtin_types_and_custom_type(unlocked_client):
    client = unlocked_client
    builtin = client.get("/api/v1/types").json()
    assert any(item["code"] == "ID_CARD_CN" for item in builtin)

    saved = client.put("/api/v1/types/EMP_NO", json=CUSTOM_TYPE)
    assert saved.status_code == 200
    assert any(item["code"] == "EMP_NO" for item in client.get("/api/v1/types").json())

    tested = client.post(
        "/api/v1/types/test",
        json={"type": CUSTOM_TYPE, "samples": ["工号 EMP-1234", "工号 EMP-xx"]},
    )
    assert tested.status_code == 200
    assert len(tested.json()["results"][0]["spans"]) == 1
    assert tested.json()["results"][1]["spans"] == []


def test_builtin_type_cannot_be_overwritten(unlocked_client):
    payload = {
        "code": "PHONE_CN", "name": "手机号", "category": "contact", "level": "low",
        "builtin": False, "enabled": False,
        "detectors": [{"kind": "regex", "pattern": "x"}],
        "defaultAction": "mask", "actionOptions": {},
    }
    assert unlocked_client.put("/api/v1/types/PHONE_CN", json=payload).status_code == 403


def test_invalid_regex_rejected(unlocked_client):
    payload = {
        "code": "BAD_RE", "name": "坏正则", "category": "custom", "level": "low",
        "builtin": False, "enabled": True,
        "detectors": [{"kind": "regex", "pattern": "("}],
        "defaultAction": "mask", "actionOptions": {},
    }
    assert unlocked_client.put("/api/v1/types/BAD_RE", json=payload).status_code == 400


def test_custom_type_can_be_deleted(unlocked_client):
    payload = {
        "code": "DEL_ME", "name": "临时", "category": "custom", "level": "low",
        "builtin": False, "enabled": True,
        "detectors": [{"kind": "regex", "pattern": "TMP-\\d+"}],
        "defaultAction": "mask", "actionOptions": {},
    }
    assert unlocked_client.put("/api/v1/types/DEL_ME", json=payload).status_code == 200
    assert unlocked_client.delete("/api/v1/types/DEL_ME").status_code == 200
    codes = {item["code"] for item in unlocked_client.get("/api/v1/types").json()}
    assert "DEL_ME" not in codes


def test_llm_settings_hide_api_key(unlocked_client):
    client = unlocked_client
    initial = client.get("/api/v1/settings/llm").json()
    assert "api_key" not in initial
    assert initial["has_key"] is False

    saved = client.put(
        "/api/v1/settings/llm",
        json={
            "mode": "online",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-secret",
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "qwen2.5:7b",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["has_key"] is True
    assert "sk-secret" not in saved.text

    fetched = client.get("/api/v1/settings/llm")
    assert "sk-secret" not in fetched.text


def test_llm_test_returns_false_in_rules_mode(unlocked_client):
    response = unlocked_client.post("/api/v1/settings/llm/test")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["mode"] == "rules"


def test_batch_processes_all_files(unlocked_client):
    client = unlocked_client
    files = [
        ("files", ("a.txt", "电话13800138000".encode("utf-8"), "text/plain")),
        ("files", ("b.txt", "身份证11010519491231002X".encode("utf-8"), "text/plain")),
    ]
    created = client.post("/api/v1/batches", files=files)
    assert created.status_code == 200
    batch_id = created.json()["id"]
    status = client.get(f"/api/v1/batches/{batch_id}").json()
    assert status["status"] == "done"
    assert status["total"] == 2
    assert status["done"] == 2
    assert all(item["status"] == "done" for item in status["items"])
