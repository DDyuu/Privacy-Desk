from app.core.security.vault import Vault
from app.core.store.db import Database
from app.core.store.repository import Repository


def make_repo(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init()
    vault = Vault()
    vault.set_master(b"m" * 32)
    return Repository(db, vault)


def test_document_roundtrip(tmp_path):
    repo = make_repo(tmp_path)
    doc_id = repo.create_document("测试.txt", "txt", "身份证 11010519491231002X", "sha")
    doc = repo.get_document(doc_id)
    assert doc["name"] == "测试.txt"
    assert doc["ext"] == "txt"
    assert repo.get_text(doc_id, "original") == "身份证 11010519491231002X"
    assert repo.list_documents()[0]["id"] == doc_id


def test_blob_roundtrip(tmp_path):
    repo = make_repo(tmp_path)
    doc_id = repo.create_document("a.docx", "docx", "正文", "sha")
    repo.save_blob(doc_id, "source", b"\x00binary\xff")
    assert repo.get_blob(doc_id, "source") == b"\x00binary\xff"


def test_detections_and_report_roundtrip(tmp_path):
    repo = make_repo(tmp_path)
    doc_id = repo.create_document("a.txt", "txt", "电话13800138000", "sha")
    version_id = repo.latest_version_id(doc_id, "original")

    class FakeSpan:
        start = 2
        end = 13
        type_code = "PHONE_CN"
        text = "13800138000"
        confidence = 0.99
        source = "rule"
        level = "high"

        def to_dict(self):
            return {
                "start": self.start,
                "end": self.end,
                "type_code": self.type_code,
                "text": self.text,
                "confidence": self.confidence,
                "source": self.source,
                "level": self.level,
            }

    repo.save_detections(doc_id, version_id, [FakeSpan()])
    items = repo.get_detections(doc_id)
    assert items[0]["text"] == "13800138000"
    assert items[0]["type_code"] == "PHONE_CN"

    report_id = repo.save_report(doc_id, "job1", "json", b'{"ok":true}')
    assert repo.get_report(report_id) == b'{"ok":true}'


def test_setting_and_type_roundtrip(tmp_path):
    repo = make_repo(tmp_path)
    repo.set_setting("llm", {"mode": "rules"})
    assert repo.get_setting("llm") == {"mode": "rules"}
    repo.save_type("CUSTOM_X", {"code": "CUSTOM_X", "name": "自定义"})
    assert repo.list_types()[0]["code"] == "CUSTOM_X"


def test_locked_repository_cannot_read(tmp_path):
    repo = make_repo(tmp_path)
    doc_id = repo.create_document("a.txt", "txt", "正文", "sha")
    repo._vault.lock()
    try:
        repo.get_text(doc_id, "original")
    except Exception as exc:
        assert "解锁" in str(exc)
    else:
        raise AssertionError("未解锁时读取应失败")
