def test_mask_requires_detect_first(unlocked_client):
    upload = unlocked_client.post(
        "/api/v1/documents",
        files={"file": ("a.txt", "电话13800138000".encode(), "text/plain")},
    )
    doc_id = upload.json()["id"]
    masked = unlocked_client.post(
        f"/api/v1/documents/{doc_id}/mask", json={"actions": {}, "verify": True}
    )
    assert masked.status_code == 400
    assert "识别" in masked.json()["detail"]


def test_export_rejects_unknown_fmt(unlocked_client):
    upload = unlocked_client.post(
        "/api/v1/documents",
        files={"file": ("a.txt", "电话13800138000".encode(), "text/plain")},
    )
    doc_id = upload.json()["id"]
    unlocked_client.post(f"/api/v1/documents/{doc_id}/detect", json={"use_llm": False})
    unlocked_client.post(f"/api/v1/documents/{doc_id}/mask", json={"actions": {}, "verify": True})
    response = unlocked_client.get(
        f"/api/v1/documents/{doc_id}/export", params={"kind": "masked", "fmt": "exe"}
    )
    assert response.status_code == 400


def test_invalid_mask_options_return_400(unlocked_client):
    upload = unlocked_client.post(
        "/api/v1/documents",
        files={"file": ("a.txt", "电话13800138000".encode(), "text/plain")},
    )
    doc_id = upload.json()["id"]
    unlocked_client.post(f"/api/v1/documents/{doc_id}/detect", json={"use_llm": False})
    response = unlocked_client.post(
        f"/api/v1/documents/{doc_id}/mask",
        json={"actions": {"PHONE_CN": {"action": "mask", "options": "bad"}}, "verify": True},
    )
    assert response.status_code == 400


def test_corrupted_docx_upload_returns_400(unlocked_client):
    response = unlocked_client.post(
        "/api/v1/documents",
        files={"file": ("broken.docx", b"not-a-zip", "application/octet-stream")},
    )
    assert response.status_code == 400
