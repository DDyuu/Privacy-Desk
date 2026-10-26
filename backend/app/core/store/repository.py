from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.security import crypto
from app.core.security.vault import Vault
from app.core.store.db import Database


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    """所有敏感内容经 vault.data_key() 加密后落库。"""

    def __init__(self, db: Database, vault: Vault) -> None:
        self._db = db
        self._vault = vault

    def _enc_bytes(self, data: bytes, aad: str) -> bytes:
        return crypto.encrypt(self._vault.data_key(), data, aad.encode("utf-8"))

    def _dec_bytes(self, blob: bytes, aad: str) -> bytes:
        return crypto.decrypt(self._vault.data_key(), blob, aad.encode("utf-8"))

    def _enc_text(self, text: str, aad: str) -> bytes:
        return self._enc_bytes(text.encode("utf-8"), aad)

    def _dec_text(self, blob: bytes, aad: str) -> str:
        return self._dec_bytes(blob, aad).decode("utf-8")

    def _enc_json(self, value: Any, aad: str) -> bytes:
        return self._enc_text(json.dumps(value, ensure_ascii=False), aad)

    def _dec_json(self, blob: bytes, aad: str) -> Any:
        return json.loads(self._dec_text(blob, aad))

    def create_document(self, name: str, ext: str, text: str, sha256: str) -> str:
        doc_id = uuid.uuid4().hex
        stamp = now_iso()
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO documents(id,name,ext,size,sha256,status,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    doc_id,
                    self._enc_text(name, f"doc:{doc_id}:name"),
                    ext,
                    len(text.encode("utf-8")),
                    sha256,
                    "uploaded",
                    stamp,
                    stamp,
                ),
            )
        self.save_version(doc_id, "original", text)
        return doc_id

    def save_version(self, doc_id: str, kind: str, text: str) -> str:
        version_id = uuid.uuid4().hex
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO doc_versions(id,doc_id,kind,content,created_at) VALUES(?,?,?,?,?)",
                (
                    version_id,
                    doc_id,
                    kind,
                    self._enc_text(text, f"ver:{version_id}"),
                    now_iso(),
                ),
            )
        return version_id

    def save_blob(self, doc_id: str, kind: str, data: bytes) -> str:
        blob_id = uuid.uuid4().hex
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO doc_versions(id,doc_id,kind,content,created_at) VALUES(?,?,?,?,?)",
                (blob_id, doc_id, kind, self._enc_bytes(data, f"blob:{blob_id}"), now_iso()),
            )
        return blob_id

    def latest_version_id(self, doc_id: str, kind: str) -> str:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id FROM doc_versions WHERE doc_id=? AND kind=?"
                " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (doc_id, kind),
            ).fetchone()
        if row is None:
            raise KeyError(f"文档 {doc_id} 没有 {kind} 版本")
        return row["id"]

    def get_text(self, doc_id: str, kind: str) -> str:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id,content FROM doc_versions WHERE doc_id=? AND kind=?"
                " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (doc_id, kind),
            ).fetchone()
        if row is None:
            raise KeyError(f"文档 {doc_id} 没有 {kind} 版本")
        return self._dec_text(row["content"], f"ver:{row['id']}")

    def get_blob(self, doc_id: str, kind: str) -> bytes:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id,content FROM doc_versions WHERE doc_id=? AND kind=?"
                " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (doc_id, kind),
            ).fetchone()
        if row is None:
            raise KeyError(f"文档 {doc_id} 没有 {kind} 数据")
        return self._dec_bytes(row["content"], f"blob:{row['id']}")

    def get_document(self, doc_id: str) -> dict:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if row is None:
            raise KeyError(doc_id)
        return {
            "id": row["id"],
            "name": self._dec_text(row["name"], f"doc:{doc_id}:name"),
            "ext": row["ext"],
            "size": row["size"],
            "sha256": row["sha256"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_documents(self) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY created_at DESC"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": self._dec_text(row["name"], f"doc:{row['id']}:name"),
                "ext": row["ext"],
                "size": row["size"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def update_status(self, doc_id: str, status: str) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE documents SET status=?, updated_at=? WHERE id=?",
                (status, now_iso(), doc_id),
            )

    def save_detections(self, doc_id: str, version_id: str, spans: list) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM detections WHERE doc_id=?", (doc_id,))
            for span in spans:
                det_id = uuid.uuid4().hex
                conn.execute(
                    'INSERT INTO detections(id,doc_id,version_id,type_code,start,"end",text,'
                    "confidence,source,level) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        det_id,
                        doc_id,
                        version_id,
                        span.type_code,
                        span.start,
                        span.end,
                        self._enc_text(span.text, f"det:{det_id}"),
                        span.confidence,
                        span.source,
                        span.level,
                    ),
                )

    def clear_detections(self, doc_id: str) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM detections WHERE doc_id=?", (doc_id,))

    def delete_type(self, code: str) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM custom_types WHERE code=?", (code,))

    def get_detections(self, doc_id: str) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute(
                'SELECT * FROM detections WHERE doc_id=? ORDER BY start, "end"',
                (doc_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "type_code": row["type_code"],
                "start": row["start"],
                "end": row["end"],
                "text": self._dec_text(row["text"], f"det:{row['id']}"),
                "confidence": row["confidence"],
                "source": row["source"],
                "level": row["level"],
            }
            for row in rows
        ]

    def save_mask_job(self, doc_id: str, config: dict, stats: dict) -> str:
        job_id = uuid.uuid4().hex
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO mask_jobs(id,doc_id,config,status,stats,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (
                    job_id,
                    doc_id,
                    self._enc_json(config, f"job:{job_id}:config"),
                    "done",
                    self._enc_json(stats, f"job:{job_id}:stats"),
                    now_iso(),
                ),
            )
        return job_id

    def save_report(self, doc_id: str, job_id: str, fmt: str, payload: bytes) -> str:
        report_id = uuid.uuid4().hex
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO reports(id,doc_id,job_id,format,content,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (
                    report_id,
                    doc_id,
                    job_id,
                    fmt,
                    self._enc_bytes(payload, f"report:{report_id}"),
                    now_iso(),
                ),
            )
        return report_id

    def latest_report(self, doc_id: str, fmt: str) -> bytes:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id,content FROM reports WHERE doc_id=? AND format=?"
                " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (doc_id, fmt),
            ).fetchone()
        if row is None:
            raise KeyError(f"文档 {doc_id} 没有 {fmt} 报告")
        return self._dec_bytes(row["content"], f"report:{row['id']}")

    def get_report(self, report_id: str) -> bytes:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id,content FROM reports WHERE id=?", (report_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"报告不存在：{report_id}")
        return self._dec_bytes(row["content"], f"report:{row['id']}")

    def set_setting(self, key: str, value: Any) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO app_settings(key,value) VALUES(?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, self._enc_json(value, f"setting:{key}")),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._db.connect() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        return self._dec_json(row["value"], f"setting:{key}")

    def save_type(self, code: str, payload: dict) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO custom_types(code,config,updated_at) VALUES(?,?,?)"
                " ON CONFLICT(code) DO UPDATE SET config=excluded.config,"
                " updated_at=excluded.updated_at",
                (code, self._enc_json(payload, f"type:{code}"), now_iso()),
            )

    def list_types(self) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT code,config FROM custom_types ORDER BY code").fetchall()
        return [self._dec_json(row["config"], f"type:{row['code']}") for row in rows]

    def create_batch(self, total: int) -> str:
        batch_id = uuid.uuid4().hex
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO batch_jobs(id,status,total,done,created_at) VALUES(?,?,?,?,?)",
                (batch_id, "running", total, 0, now_iso()),
            )
        return batch_id

    def add_batch_item(self, batch_id: str, status: str = "pending", message: str = "") -> str:
        item_id = uuid.uuid4().hex
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO batch_items(id,batch_id,doc_id,status,message) VALUES(?,?,?,?,?)",
                (item_id, batch_id, None, status, message),
            )
        return item_id

    def update_batch_item(
        self, item_id: str, status: str, message: str = "", doc_id: str | None = None
    ) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE batch_items SET status=?, message=?, doc_id=COALESCE(?, doc_id) WHERE id=?",
                (status, message, doc_id, item_id),
            )

    def finish_batch(self, batch_id: str) -> None:
        with self._db.connect() as conn:
            conn.execute("UPDATE batch_jobs SET status='done' WHERE id=?", (batch_id,))

    def get_batch(self, batch_id: str) -> dict:
        with self._db.connect() as conn:
            job = conn.execute("SELECT * FROM batch_jobs WHERE id=?", (batch_id,)).fetchone()
            items = conn.execute(
                "SELECT * FROM batch_items WHERE batch_id=? ORDER BY rowid", (batch_id,)
            ).fetchall()
        if job is None:
            raise KeyError(batch_id)
        return {
            "id": job["id"],
            "status": job["status"],
            "total": job["total"],
            "done": sum(1 for item in items if item["status"] in {"done", "failed"}),
            "items": [
                {
                    "id": item["id"],
                    "doc_id": item["doc_id"],
                    "status": item["status"],
                    "message": item["message"],
                }
                for item in items
            ],
        }

    def audit(self, action: str, detail: dict) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO audit_logs(id,action,detail,created_at) VALUES(?,?,?,?)",
                (uuid.uuid4().hex, action, json.dumps(detail, ensure_ascii=False), now_iso()),
            )
