import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_full_document_flow(unlocked_client):
    client = unlocked_client
    content = "联系人张三，电话13800138000，身份证11010519491231002X。".encode("utf-8")
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("sample.txt", content, "text/plain")},
    )
    assert upload.status_code == 200
    doc_id = upload.json()["id"]

    listing = client.get("/api/v1/documents")
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == doc_id

    detected = client.post(
        f"/api/v1/documents/{doc_id}/detect", json={"use_llm": False}
    )
    assert detected.status_code == 200
    codes = {item["type_code"] for item in detected.json()["spans"]}
    assert {"PHONE_CN", "ID_CARD_CN"} <= codes
    assert detected.json()["mode"] == "rules"

    masked = client.post(
        f"/api/v1/documents/{doc_id}/mask", json={"actions": {}, "verify": True}
    )
    assert masked.status_code == 200
    body = masked.json()
    assert "13800138000" not in body["masked_text"]
    assert "11010519491231002X" not in body["masked_text"]
    assert body["verify"]["passed"] is True
    assert body["stats"]["detected"] >= 2

    compare = client.get(f"/api/v1/documents/{doc_id}/compare")
    assert "13800138000" in compare.json()["original"]
    assert "13800138000" not in compare.json()["masked"]

    no_password = client.get(
        f"/api/v1/documents/{doc_id}/export", params={"kind": "report", "fmt": "json"}
    )
    assert no_password.status_code == 401

    wrong_password = client.get(
        f"/api/v1/documents/{doc_id}/export",
        params={"kind": "report", "fmt": "json", "password": "wrong-pass"},
    )
    assert wrong_password.status_code == 403

    report = client.get(
        f"/api/v1/documents/{doc_id}/export",
        params={"kind": "report", "fmt": "json", "password": "password123"},
    )
    assert report.status_code == 200
    assert report.json()["summary"]["detected"] >= 2

    exported = client.get(
        f"/api/v1/documents/{doc_id}/export", params={"kind": "masked", "fmt": "txt"}
    )
    assert exported.status_code == 200
    assert "13800138000" not in exported.text


def test_reveal_encrypted_tokens_requires_password(unlocked_client):
    client = unlocked_client
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("secret.txt", "电话13800138000".encode("utf-8"), "text/plain")},
    )
    doc_id = upload.json()["id"]
    client.post(f"/api/v1/documents/{doc_id}/detect", json={"use_llm": False})
    masked = client.post(
        f"/api/v1/documents/{doc_id}/mask",
        json={"actions": {"PHONE_CN": {"action": "encrypt"}}, "verify": True},
    )
    assert masked.status_code == 200
    assert "ENC:" in masked.json()["masked_text"]

    assert client.post(f"/api/v1/documents/{doc_id}/reveal", json={}).status_code == 401
    wrong = client.post(
        f"/api/v1/documents/{doc_id}/reveal", json={"password": "wrong-pass"}
    )
    assert wrong.status_code == 403

    ok = client.post(
        f"/api/v1/documents/{doc_id}/reveal", json={"password": "password123"}
    )
    assert ok.status_code == 200
    items = ok.json()["items"]
    assert [item["text"] for item in items] == ["13800138000"]
    assert items[0]["type_code"] == "PHONE_CN"
    assert "13800138000" not in items[0]["token"]


def test_mask_can_ignore_selected_span(unlocked_client):
    client = unlocked_client
    text = "电话13800138000，备用13900139000"
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("phones.txt", text.encode("utf-8"), "text/plain")},
    )
    doc_id = upload.json()["id"]
    client.post(f"/api/v1/documents/{doc_id}/detect", json={"use_llm": False})
    detections = client.get(f"/api/v1/documents/{doc_id}").json()["detections"]
    phones = [item for item in detections if item["type_code"] == "PHONE_CN"]
    assert len(phones) == 2

    kept = phones[0]
    masked = client.post(
        f"/api/v1/documents/{doc_id}/mask",
        json={
            "actions": {},
            "verify": True,
            "ignored": [f"{kept['start']}-{kept['end']}-{kept['type_code']}"],
        },
    )
    assert masked.status_code == 200
    body = masked.json()
    assert kept["text"] in body["masked_text"]
    assert phones[1]["text"] not in body["masked_text"]
    assert body["stats"]["ignored"] == 1
    assert body["stats"]["applied"] == 1
    assert body["verify"]["passed"] is True

    again = client.post(f"/api/v1/documents/{doc_id}/verify")
    assert again.json()["passed"] is True


def test_clear_documents_removes_history(unlocked_client):
    client = unlocked_client
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("a.txt", "电话13800138000".encode("utf-8"), "text/plain")},
    )
    doc_id = upload.json()["id"]
    client.post(f"/api/v1/documents/{doc_id}/detect", json={"use_llm": False})

    cleared = client.delete("/api/v1/documents")
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 1
    assert client.get("/api/v1/documents").json() == []
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404

    ctx = client.app.state.ctx
    assert ctx.repo.get_detections(doc_id) == []
    with pytest.raises(KeyError):
        ctx.repo.get_text(doc_id, "original")


def test_document_limit_rejects_upload(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, llm_api_key=None, max_docs=1))
    client = TestClient(app)
    setup = client.post("/api/v1/session/setup", json={"password": "password123"})
    assert setup.status_code == 200

    first = client.post(
        "/api/v1/documents", files={"file": ("a.txt", b"hello", "text/plain")}
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/documents", files={"file": ("b.txt", b"world", "text/plain")}
    )
    assert second.status_code == 409
    assert "上限" in second.json()["detail"]


def test_edit_content_and_reject_unsupported(unlocked_client):
    client = unlocked_client
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("a.txt", "电话13800138000".encode("utf-8"), "text/plain")},
    )
    doc_id = upload.json()["id"]
    edited = client.put(
        f"/api/v1/documents/{doc_id}/content",
        json={"text": "新的正文 13800138000"},
    )
    assert edited.status_code == 200
    assert "新的正文" in client.get(f"/api/v1/documents/{doc_id}").json()["text"]

    bad = client.post(
        "/api/v1/documents",
        files={"file": ("a.exe", b"MZ", "application/octet-stream")},
    )
    assert bad.status_code == 400


def test_docx_export_uses_applied_mapping(unlocked_client, tmp_path):
    from docx import Document
    from io import BytesIO

    doc = Document()
    doc.add_paragraph("姓名张三")
    doc.add_paragraph("电话13800138000")
    buffer = BytesIO()
    doc.save(buffer)
    upload = unlocked_client.post(
        "/api/v1/documents",
        files={
            "file": (
                "sample.docx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload.status_code == 200
    doc_id = upload.json()["id"]
    unlocked_client.post(f"/api/v1/documents/{doc_id}/detect", json={"use_llm": False})
    unlocked_client.post(
        f"/api/v1/documents/{doc_id}/mask",
        json={"actions": {"PHONE_CN": {"action": "replace"}}, "verify": True},
    )
    exported = unlocked_client.get(
        f"/api/v1/documents/{doc_id}/export", params={"kind": "masked", "fmt": "docx"}
    )
    assert exported.status_code == 200
    reloaded = Document(BytesIO(exported.content))
    assert "13800138000" not in reloaded.paragraphs[1].text
    assert "电话" in reloaded.paragraphs[1].text
