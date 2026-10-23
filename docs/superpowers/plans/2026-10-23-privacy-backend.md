# 隐私脱敏系统后端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现可独立运行和测试的 FastAPI 后端：加密存储、多格式解析、规则+LLM 识别、四种脱敏、效果校验、报告与批量处理。

**Architecture:** 单进程 FastAPI 应用，SQLite 字段级 AES-256-GCM 加密，规则引擎与 LLM 引擎并行产出 Span 后融合；所有文档先转统一模型再识别，脱敏按 span 逆序替换并复扫校验。

**Tech Stack:** Python 3.12、FastAPI、SQLite、argon2-cffi、cryptography、python-docx、pdfplumber、reportlab、httpx、pytest。

**执行约定：** 工程根目录为 `privacy-desk/`，命令均在 `privacy-desk/backend` 下执行；使用 `py -3.12` 创建虚拟环境。仓库未初始化 git，按用户偏好不自动提交，每个任务以"目标测试全绿"为完成标准。

---

## 文件结构

```
privacy-desk/backend/
├─ pyproject.toml
├─ app/
│  ├─ config.py                 运行配置
│  ├─ main.py                   应用工厂、令牌中间件、路由挂载
│  ├─ context.py                依赖容器
│  ├─ api/
│  │  ├─ session.py             主密码与解锁
│  │  ├─ documents.py           上传/识别/脱敏/对比/导出
│  │  ├─ types.py               类型管理
│  │  ├─ settings.py            LLM 配置
│  │  └─ batches.py             批量任务
│  ├─ core/
│  │  ├─ pipeline.py            上传→识别→脱敏的编排
│  │  ├─ security/
│  │  │  ├─ crypto.py           AES-GCM 原语
│  │  │  ├─ keys.py             Argon2id / HKDF / canary
│  │  │  ├─ vault.py            会话密钥
│  │  │  ├─ resources.py        加密资源加载
│  │  │  └─ integrity.py        manifest + HMAC 校验
│  │  ├─ store/
│  │  │  ├─ db.py               SQLite 连接与建表
│  │  │  └─ repository.py       加密仓储
│  │  ├─ detect/
│  │  │  ├─ checksum.py         身份证/Luhn 校验
│  │  │  ├─ types.py            类型定义与注册表
│  │  │  ├─ rule_engine.py      正则/关键词识别
│  │  │  ├─ chunking.py         分块
│  │  │  ├─ pre_redact.py       云端前等长遮蔽
│  │  │  ├─ llm_engine.py       LLM 语义识别
│  │  │  └─ fusion.py           span 融合
│  │  ├─ mask/
│  │  │  ├─ operators.py        四种脱敏算子
│  │  │  ├─ engine.py           脱敏编排与一致性映射
│  │  │  └─ verifier.py         脱敏后复扫
│  │  └─ report/
│  │     └─ builder.py          JSON/PDF 报告
│  └─ llm/
│     ├─ client.py              OpenAI 兼容 / Ollama 客户端
│     └─ service.py             LLM 配置与降级
├─ resources/
│  ├─ types.default.json
│  └─ prompts/llm_extract.txt
└─ tests/
```

---

## Task 1: 工程骨架与健康检查

**Files:**
- Create: `privacy-desk/backend/pyproject.toml`
- Create: `privacy-desk/backend/app/__init__.py`
- Create: `privacy-desk/backend/app/config.py`
- Create: `privacy-desk/backend/app/main.py`
- Create: `privacy-desk/backend/tests/test_health.py`
- Create: `privacy-desk/.gitignore`

- [ ] **Step 1: 写失败测试**

`tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_returns_ok(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_health.py -v`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'app'` 或 `create_app` 不存在。

- [ ] **Step 3: 写最小实现**

`pyproject.toml`:

```toml
[project]
name = "privacy-desk-backend"
version = "0.1.0"
description = "基于大模型的文本隐私信息智能脱敏系统后端"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.8.0",
    "argon2-cffi>=23.1.0",
    "cryptography>=43.0.0",
    "python-docx>=1.1.2",
    "pdfplumber>=0.11.4",
    "reportlab>=4.2.2",
    "httpx>=0.27.2",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.3.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-q"
```

`app/config.py`:

```python
import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    """运行期配置；测试可传入临时目录。"""

    data_dir: Path = field(
        default_factory=lambda: Path(_env("PRIVACY_DESK_DATA", str(Path.home() / ".privacy-desk")))
    )
    resources_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "resources"
    )
    app_token: str | None = field(default_factory=lambda: os.environ.get("APP_TOKEN"))
    max_upload_mb: int = 20
    chunk_size: int = 2000
    chunk_overlap: int = 100
    llm_base_url: str = field(
        default_factory=lambda: _env("PRIVACY_DESK_LLM_BASE", "https://api.deepseek.com/v1")
    )
    llm_model: str = field(
        default_factory=lambda: _env("PRIVACY_DESK_LLM_MODEL", "deepseek-chat")
    )
    llm_api_key: str | None = field(default_factory=lambda: os.environ.get("PRIVACY_DESK_LLM_KEY"))
    ollama_url: str = field(
        default_factory=lambda: _env("PRIVACY_DESK_OLLAMA", "http://127.0.0.1:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: _env("PRIVACY_DESK_OLLAMA_MODEL", "qwen2.5:7b")
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "privacy.db"
```

`app/main.py`:

```python
from fastapi import FastAPI

from app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Privacy Desk", version="0.1.0")
    app.state.settings = settings or Settings()

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok"}

    return app
```

`app/__init__.py` 与 `tests/__init__.py` 为空文件。`privacy-desk/.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
node_modules/
dist/
build/
*.log
```

- [ ] **Step 4: 创建环境并安装依赖**

Run: `py -3.12 -m venv .venv`
Run: `.venv\Scripts\python.exe -m pip install -e ".[dev]"`
Expected: 安装成功，`Successfully installed fastapi-... pytest-...`。

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_health.py -v`
Expected: `1 passed`。

---

## Task 2: 加密原语与密钥派生

**Files:**
- Create: `privacy-desk/backend/app/core/__init__.py`
- Create: `privacy-desk/backend/app/core/security/__init__.py`
- Create: `privacy-desk/backend/app/core/security/crypto.py`
- Create: `privacy-desk/backend/app/core/security/keys.py`
- Create: `privacy-desk/backend/tests/test_crypto.py`
- Create: `privacy-desk/backend/tests/test_keys.py`

- [ ] **Step 1: 写失败测试**

`tests/test_crypto.py`:

```python
import pytest

from app.core.security import crypto


def test_encrypt_decrypt_roundtrip():
    key = b"k" * 32
    blob = crypto.encrypt(key, b"hello", b"aad")
    assert blob != b"hello"
    assert crypto.decrypt(key, blob, b"aad") == b"hello"


def test_decrypt_with_wrong_aad_fails():
    key = b"k" * 32
    blob = crypto.encrypt(key, b"hello", b"aad-1")
    with pytest.raises(Exception):
        crypto.decrypt(key, blob, b"aad-2")


def test_tampered_ciphertext_fails():
    key = b"k" * 32
    blob = crypto.encrypt(key, b"hello", b"aad")
    tampered = blob[:-1] + bytes([blob[-1] ^ 0xFF])
    with pytest.raises(Exception):
        crypto.decrypt(key, tampered, b"aad")


def test_base64url_roundtrip():
    data = bytes(range(32))
    assert crypto.b64url_decode(crypto.b64url_encode(data)) == data
```

`tests/test_keys.py`:

```python
from app.core.security import keys


def test_derive_is_deterministic_and_different_for_wrong_password():
    salt = keys.new_salt()
    right = keys.derive_master_key("password123", salt)
    again = keys.derive_master_key("password123", salt)
    wrong = keys.derive_master_key("password456", salt)
    assert right == again
    assert right != wrong
    assert len(right) == 32


def test_data_key_differs_from_master_key():
    salt = keys.new_salt()
    master = keys.derive_master_key("password123", salt)
    assert keys.derive_data_key(master) != master
    assert len(keys.derive_data_key(master)) == 32


def test_canary_verifies_only_with_correct_key():
    salt = keys.new_salt()
    master = keys.derive_master_key("password123", salt)
    sealed = keys.seal_canary(master)
    assert keys.verify_canary(master, sealed) is True
    other = keys.derive_master_key("password456", salt)
    assert keys.verify_canary(other, sealed) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_crypto.py tests/test_keys.py -v`
Expected: FAIL，`No module named 'app.core.security'`。

- [ ] **Step 3: 写实现**

`app/core/security/crypto.py`:

```python
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_LEN = 12


def encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM 加密，返回 nonce(12B) + 密文 + tag。"""
    nonce = os.urandom(NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if len(blob) <= NONCE_LEN:
        raise ValueError("密文长度非法")
    return AESGCM(key).decrypt(blob[:NONCE_LEN], blob[NONCE_LEN:], aad)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)
```

`app/core/security/keys.py`:

```python
import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.security import crypto

SALT_LEN = 16
CANARY = b"PRIVACY-DESK-CANARY-V1"


def new_salt() -> bytes:
    return os.urandom(SALT_LEN)


def derive_master_key(password: str, salt: bytes) -> bytes:
    """Argon2id 派生主密钥；参数固定，保证跨启动可复现。"""
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        type=Type.ID,
    )


def derive_data_key(master_key: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"data/v1",
    ).derive(master_key)


def seal_canary(master_key: bytes) -> bytes:
    return crypto.encrypt(master_key, CANARY, b"meta:canary")


def verify_canary(master_key: bytes, sealed: bytes) -> bool:
    try:
        return crypto.decrypt(master_key, sealed, b"meta:canary") == CANARY
    except Exception:
        return False
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_crypto.py tests/test_keys.py -v`
Expected: `7 passed`。

---

## Task 3: 会话密钥保险库

**Files:**
- Create: `privacy-desk/backend/app/core/security/vault.py`
- Create: `privacy-desk/backend/tests/test_vault.py`

- [ ] **Step 1: 写失败测试**

`tests/test_vault.py`:

```python
import pytest

from app.core.security.vault import LockedError, Vault


def test_vault_requires_unlock():
    vault = Vault()
    assert vault.unlocked is False
    with pytest.raises(LockedError):
        vault.data_key()


def test_lock_clears_key():
    vault = Vault()
    vault.set_master(b"m" * 32)
    assert len(vault.data_key()) == 32
    vault.lock()
    assert vault.unlocked is False
    with pytest.raises(LockedError):
        vault.master_key()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_vault.py -v`
Expected: FAIL，`No module named 'app.core.security.vault'`。

- [ ] **Step 3: 写实现**

`app/core/security/vault.py`:

```python
from app.core.security import keys


class LockedError(RuntimeError):
    """未解锁时访问密钥。"""


class Vault:
    """主密钥仅保存在内存，锁定时丢弃引用。"""

    def __init__(self) -> None:
        self._master: bytes | None = None

    @property
    def unlocked(self) -> bool:
        return self._master is not None

    def set_master(self, master_key: bytes) -> None:
        self._master = master_key

    def lock(self) -> None:
        self._master = None

    def master_key(self) -> bytes:
        if self._master is None:
            raise LockedError("请先输入主密码解锁")
        return self._master

    def data_key(self) -> bytes:
        return keys.derive_data_key(self.master_key())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_vault.py -v`
Expected: `2 passed`。

---

## Task 4: SQLite 建表与加密仓储

**Files:**
- Create: `privacy-desk/backend/app/core/store/__init__.py`
- Create: `privacy-desk/backend/app/core/store/db.py`
- Create: `privacy-desk/backend/app/core/store/repository.py`
- Create: `privacy-desk/backend/tests/test_repository.py`

- [ ] **Step 1: 写失败测试**

`tests/test_repository.py`:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_repository.py -v`
Expected: FAIL，`No module named 'app.core.store'`。

- [ ] **Step 3: 写实现**

`app/core/store/db.py`:

```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_meta(
    key TEXT PRIMARY KEY,
    value BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS documents(
    id TEXT PRIMARY KEY,
    name BLOB NOT NULL,
    ext TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS doc_versions(
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    content BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_versions_doc ON doc_versions(doc_id, kind);
CREATE TABLE IF NOT EXISTS detections(
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_id TEXT NOT NULL,
    type_code TEXT NOT NULL,
    start INTEGER NOT NULL,
    "end" INTEGER NOT NULL,
    text BLOB NOT NULL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    level TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_detections_doc ON detections(doc_id);
CREATE TABLE IF NOT EXISTS mask_jobs(
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    config BLOB NOT NULL,
    status TEXT NOT NULL,
    stats BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports(
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    job_id TEXT NOT NULL,
    format TEXT NOT NULL,
    content BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_doc ON reports(doc_id, format);
CREATE TABLE IF NOT EXISTS custom_types(
    code TEXT PRIMARY KEY,
    config BLOB NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings(
    key TEXT PRIMARY KEY,
    value BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS batch_jobs(
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    total INTEGER NOT NULL,
    done INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batch_items(
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batch_jobs(id) ON DELETE CASCADE,
    doc_id TEXT,
    status TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs(
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
```

`app/core/store/repository.py`:

```python
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
                (report_id, doc_id, job_id, fmt, self._enc_bytes(payload, f"report:{report_id}"), now_iso()),
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

    def update_batch_item(self, item_id: str, status: str, message: str = "", doc_id: str | None = None) -> None:
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_repository.py -v`
Expected: `5 passed`。

---

## Task 5: 隐私类型体系与校验算法

**Files:**
- Create: `privacy-desk/backend/app/core/detect/__init__.py`
- Create: `privacy-desk/backend/app/core/detect/checksum.py`
- Create: `privacy-desk/backend/app/core/detect/types.py`
- Create: `privacy-desk/backend/resources/types.default.json`
- Create: `privacy-desk/backend/tests/test_types.py`

- [ ] **Step 1: 写失败测试**

`tests/test_types.py`:

```python
from pathlib import Path

from app.core.detect.checksum import gb11643_valid, luhn_valid
from app.core.detect.types import load_builtin_types


def test_gb11643_checksum():
    assert gb11643_valid("11010519491231002X") is True
    assert gb11643_valid("110105194912310021") is False
    assert gb11643_valid("12345") is False


def test_luhn_checksum():
    assert luhn_valid("4111111111111111") is True
    assert luhn_valid("4111111111111112") is False


def test_builtin_types_loaded():
    types = load_builtin_types(Path(__file__).resolve().parents[1] / "resources")
    codes = {t.code for t in types}
    assert {"ID_CARD_CN", "PHONE_CN", "BANK_CARD", "NAME_CN", "ADDRESS_CN", "SECRET_INFO"} <= codes
    assert len(types) == 10
    id_card = next(t for t in types if t.code == "ID_CARD_CN")
    assert id_card.level == "high"
    assert id_card.default_action == "mask"
    assert any(d.kind == "checksum" and d.algo == "gb11643" for d in id_card.detectors)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_types.py -v`
Expected: FAIL，`No module named 'app.core.detect'`。

- [ ] **Step 3: 写实现**

`app/core/detect/checksum.py`:

```python
GB11643_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
GB11643_CHECK = "10X98765432"


def gb11643_valid(value: str) -> bool:
    """18 位居民身份证号校验位验证。"""
    if len(value) != 18 or not value[:17].isdigit():
        return False
    total = sum(int(ch) * weight for ch, weight in zip(value[:17], GB11643_WEIGHTS))
    return GB11643_CHECK[total % 11] == value[17].upper()


def luhn_valid(value: str) -> bool:
    """银行卡 Luhn 校验。"""
    digits = [int(ch) for ch in value if ch.isdigit()]
    if len(digits) < 12:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def validate_checksum(algo: str, value: str) -> bool:
    if algo == "gb11643":
        return gb11643_valid(value)
    if algo == "luhn":
        return luhn_valid(value)
    raise ValueError(f"未知校验算法：{algo}")
```

`app/core/detect/types.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Detector(BaseModel):
    kind: Literal["regex", "checksum", "keyword", "dict", "llm"]
    pattern: str | None = None
    flags: list[str] = Field(default_factory=list)
    algo: str | None = None
    words: list[str] = Field(default_factory=list)
    hint: str | None = None


class TypeDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    name: str
    category: str
    level: Literal["high", "medium", "low"] = "medium"
    builtin: bool = False
    enabled: bool = True
    detectors: list[Detector]
    default_action: Literal["mask", "replace", "fuzz", "encrypt"] = Field("mask", alias="defaultAction")
    action_options: dict[str, Any] = Field(default_factory=dict, alias="actionOptions")


class TypeRegistry:
    """内置类型与用户自定义类型的合并视图。"""

    def __init__(self, types: list[TypeDefinition]) -> None:
        self._types: dict[str, TypeDefinition] = {item.code: item for item in types}

    def list(self) -> list[TypeDefinition]:
        return [item for item in self._types.values() if item.enabled]

    def all(self) -> list[TypeDefinition]:
        return list(self._types.values())

    def get(self, code: str) -> TypeDefinition:
        if code not in self._types:
            raise KeyError(f"未知隐私类型：{code}")
        return self._types[code]

    def upsert(self, definition: TypeDefinition) -> None:
        self._types[definition.code] = definition

    def load_from_repo(self, repo) -> None:
        """解锁后把自定义类型合并进注册表；未解锁时静默跳过。"""
        try:
            payloads = repo.list_types()
        except Exception:
            return
        for payload in payloads:
            self.upsert(TypeDefinition.model_validate(payload))


def load_builtin_types(resources_dir: Path) -> list[TypeDefinition]:
    payload = json.loads((resources_dir / "types.default.json").read_text(encoding="utf-8"))
    return [TypeDefinition.model_validate(item) for item in payload]
```

`resources/types.default.json`:

```json
[
  {
    "code": "ID_CARD_CN", "name": "身份证号", "category": "personal_id", "level": "high",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "regex", "pattern": "(?<![0-9A-Za-z])\\d{17}[0-9Xx](?![0-9A-Za-z])"},
      {"kind": "checksum", "algo": "gb11643"},
      {"kind": "llm", "hint": "中国大陆居民身份证号（18 位）"}
    ],
    "defaultAction": "mask", "actionOptions": {"keepPrefix": 0, "keepSuffix": 4}
  },
  {
    "code": "PHONE_CN", "name": "手机号", "category": "contact", "level": "high",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "regex", "pattern": "(?<![0-9])1[3-9]\\d{9}(?![0-9])"},
      {"kind": "llm", "hint": "中国大陆 11 位手机号"}
    ],
    "defaultAction": "mask", "actionOptions": {"keepPrefix": 0, "keepSuffix": 4}
  },
  {
    "code": "BANK_CARD", "name": "银行卡号", "category": "financial", "level": "high",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "regex", "pattern": "(?<![0-9])\\d{16,19}(?![0-9])"},
      {"kind": "checksum", "algo": "luhn"},
      {"kind": "llm", "hint": "银行卡号"}
    ],
    "defaultAction": "mask", "actionOptions": {"keepPrefix": 0, "keepSuffix": 4}
  },
  {
    "code": "EMAIL", "name": "邮箱地址", "category": "contact", "level": "medium",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "regex", "pattern": "[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}"},
      {"kind": "llm", "hint": "电子邮件地址"}
    ],
    "defaultAction": "mask", "actionOptions": {"keepPrefix": 2, "keepSuffix": 0}
  },
  {
    "code": "IPV4", "name": "IP 地址", "category": "network", "level": "medium",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "regex", "pattern": "(?<![0-9])(?:(?:25[0-5]|2[0-4]\\d|1?\\d?\\d)\\.){3}(?:25[0-5]|2[0-4]\\d|1?\\d?\\d)(?![0-9])"},
      {"kind": "llm", "hint": "IPv4 地址"}
    ],
    "defaultAction": "mask", "actionOptions": {"keepPrefix": 0, "keepSuffix": 0}
  },
  {
    "code": "PLATE_CN", "name": "车牌号", "category": "personal_id", "level": "medium",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "regex", "pattern": "[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{5,6}"},
      {"kind": "llm", "hint": "中国大陆机动车号牌"}
    ],
    "defaultAction": "mask", "actionOptions": {"keepPrefix": 0, "keepSuffix": 2}
  },
  {
    "code": "PASSPORT_CN", "name": "护照号", "category": "personal_id", "level": "high",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "regex", "pattern": "(?<![0-9A-Za-z])[EG]\\d{8}(?![0-9A-Za-z])"},
      {"kind": "llm", "hint": "中国护照号"}
    ],
    "defaultAction": "mask", "actionOptions": {"keepPrefix": 0, "keepSuffix": 4}
  },
  {
    "code": "NAME_CN", "name": "姓名", "category": "personal", "level": "medium",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "llm", "hint": "中文人名，姓+名共 2 到 4 个字，需结合上下文判断"}
    ],
    "defaultAction": "replace", "actionOptions": {}
  },
  {
    "code": "ADDRESS_CN", "name": "详细地址", "category": "personal", "level": "medium",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "regex", "pattern": "[\\u4e00-\\u9fa5]{2,8}(?:省|市)[\\u4e00-\\u9fa5]{0,8}(?:区|县|市)[\\u4e00-\\u9fa5A-Za-z0-9]{0,20}(?:路|街|道|巷)[\\u4e00-\\u9fa5A-Za-z0-9]{0,10}(?:号)?"},
      {"kind": "llm", "hint": "详细住址，包含省市区与街道门牌"}
    ],
    "defaultAction": "fuzz", "actionOptions": {}
  },
  {
    "code": "SECRET_INFO", "name": "涉密信息", "category": "secret", "level": "high",
    "builtin": true, "enabled": true,
    "detectors": [
      {"kind": "keyword", "words": ["绝密", "机密", "秘密", "涉密", "内部资料", "仅限内部"]},
      {"kind": "llm", "hint": "标密内容、内部资料、涉密表述"}
    ],
    "defaultAction": "encrypt", "actionOptions": {}
  }
]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_types.py -v`
Expected: `3 passed`。

---

## Task 6: 规则识别引擎

**Files:**
- Create: `privacy-desk/backend/app/core/detect/rule_engine.py`
- Create: `privacy-desk/backend/tests/test_rule_engine.py`

- [ ] **Step 1: 写失败测试**

`tests/test_rule_engine.py`:

```python
from pathlib import Path

from app.core.detect.rule_engine import RuleEngine, Span
from app.core.detect.types import load_builtin_types

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def engine():
    return RuleEngine(load_builtin_types(RESOURCES))


def test_detects_phone_and_valid_id():
    text = "联系人电话13800138000，身份证11010519491231002X。"
    spans = engine().detect(text)
    found = {(s.type_code, s.text) for s in spans}
    assert ("PHONE_CN", "13800138000") in found
    assert ("ID_CARD_CN", "11010519491231002X") in found


def test_rejects_invalid_id_checksum():
    spans = engine().detect("身份证110105194912310021")
    assert all(s.type_code != "ID_CARD_CN" for s in spans)


def test_detects_keyword_secret():
    spans = engine().detect("以下内容属于内部资料，请勿外传")
    assert any(s.type_code == "SECRET_INFO" for s in spans)


def test_span_offsets_point_to_original_text():
    text = "电话：13800138000"
    span = next(s for s in engine().detect(text) if s.type_code == "PHONE_CN")
    assert text[span.start:span.end] == span.text


def test_overlapping_candidates_keep_longest():
    spans = engine().detect("银行卡4111111111111111")
    cards = [s for s in spans if s.type_code == "BANK_CARD"]
    assert len(cards) == 1
    assert cards[0].text == "4111111111111111"


def test_span_to_dict():
    span = Span(0, 3, "X", "abc", 0.9, "rule", "low")
    assert span.to_dict()["type_code"] == "X"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rule_engine.py -v`
Expected: FAIL，`No module named 'app.core.detect.rule_engine'`。

- [ ] **Step 3: 写实现**

`app/core/detect/rule_engine.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.detect.checksum import validate_checksum
from app.core.detect.types import TypeDefinition


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    type_code: str
    text: str
    confidence: float
    source: str
    level: str = "medium"

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "type_code": self.type_code,
            "text": self.text,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "level": self.level,
        }


def _find_all(text: str, needle: str):
    start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            return
        yield index
        start = index + 1


class RuleEngine:
    """正则、关键词、校验位与词典的确定性识别。"""

    def __init__(self, types: list[TypeDefinition]) -> None:
        self._types = [item for item in types if item.enabled]

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for definition in self._types:
            checksum = next(
                (d.algo for d in definition.detectors if d.kind == "checksum" and d.algo), None
            )
            candidates: list[tuple[int, int, float]] = []
            for detector in definition.detectors:
                if detector.kind == "regex" and detector.pattern:
                    flags = re.IGNORECASE if "i" in detector.flags else 0
                    for match in re.finditer(detector.pattern, text, flags):
                        candidates.append((match.start(), match.end(), 0.9))
                elif detector.kind in ("keyword", "dict"):
                    for word in detector.words:
                        if not word:
                            continue
                        for position in _find_all(text, word):
                            candidates.append((position, position + len(word), 0.8))
            kept: list[tuple[int, int, float]] = []
            for start, end, confidence in sorted(
                candidates, key=lambda item: (item[0], -(item[1] - item[0]))
            ):
                if kept and start < kept[-1][1]:
                    continue
                if checksum and not validate_checksum(checksum, text[start:end]):
                    continue
                kept.append((start, end, confidence))
            for start, end, confidence in kept:
                spans.append(
                    Span(
                        start=start,
                        end=end,
                        type_code=definition.code,
                        text=text[start:end],
                        confidence=0.99 if checksum else confidence,
                        source="rule",
                        level=definition.level,
                    )
                )
        return spans
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rule_engine.py -v`
Expected: `6 passed`。

---

## Task 7: 统一文档模型与纯文本解析

**Files:**
- Create: `privacy-desk/backend/app/core/ingest/__init__.py`
- Create: `privacy-desk/backend/app/core/ingest/model.py`
- Create: `privacy-desk/backend/app/core/ingest/text_loader.py`
- Create: `privacy-desk/backend/app/core/ingest/writer.py`
- Create: `privacy-desk/backend/app/core/ingest/registry.py`
- Create: `privacy-desk/backend/tests/test_text_ingest.py`

- [ ] **Step 1: 写失败测试**

`tests/test_text_ingest.py`:

```python
from pathlib import Path

from app.core.ingest.model import Block, build_model
from app.core.ingest.registry import export_document, load_document
from app.core.ingest.text_loader import decode_text


def test_build_model_offsets():
    model = build_model([Block("paragraph", "abc"), Block("paragraph", "defg")], "txt")
    assert model.text == "abc\ndefg"
    assert model.text[model.blocks[0].start:model.blocks[0].end] == "abc"
    assert model.text[model.blocks[1].start:model.blocks[1].end] == "defg"


def test_decode_gbk_fallback():
    assert decode_text("中文内容".encode("gbk")) == "中文内容"


def test_load_and_export_text(tmp_path):
    source = tmp_path / "a.txt"
    source.write_text("第一行\n电话13800138000", encoding="utf-8")
    model = load_document(source, "txt")
    assert "13800138000" in model.text
    masked = model.text.replace("13800138000", "138****8000")
    target = tmp_path / "out.txt"
    export_document(model, masked, target, "txt")
    assert "138****8000" in target.read_text(encoding="utf-8")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_text_ingest.py -v`
Expected: FAIL，`No module named 'app.core.ingest'`。

- [ ] **Step 3: 写实现**

`app/core/ingest/model.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Block:
    kind: str
    text: str
    start: int = 0
    end: int = 0
    ref: Any = None


@dataclass
class DocumentModel:
    text: str
    blocks: list[Block]
    fmt: str
    meta: dict = field(default_factory=dict)


def build_model(blocks: list[Block], fmt: str, meta: dict | None = None) -> DocumentModel:
    """用换行连接块文本，并记录每块在全文中的偏移。"""
    parts: list[str] = []
    cursor = 0
    for block in blocks:
        block.start = cursor
        block.end = cursor + len(block.text)
        parts.append(block.text)
        cursor = block.end + 1
    return DocumentModel(text="\n".join(parts), blocks=blocks, fmt=fmt, meta=meta or {})
```

`app/core/ingest/text_loader.py`:

```python
from pathlib import Path

from app.core.ingest.model import Block, DocumentModel, build_model


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_text(path: Path) -> DocumentModel:
    text = decode_text(Path(path).read_bytes())
    blocks = [Block(kind="paragraph", text=line) for line in text.split("\n")]
    fmt = Path(path).suffix.lstrip(".").lower() or "txt"
    return build_model(blocks, fmt)
```

`app/core/ingest/writer.py`:

```python
from pathlib import Path

from app.core.ingest.model import DocumentModel


def write_text(model: DocumentModel, masked_text: str, out_path: Path) -> None:
    Path(out_path).write_text(masked_text, encoding="utf-8")
```

`app/core/ingest/registry.py`:

```python
from pathlib import Path

from app.core.ingest.model import DocumentModel
from app.core.ingest.text_loader import load_text
from app.core.ingest.writer import write_text

TEXT_EXTS = {"txt", "md", "log", "py", "java", "js", "ts", "json", "csv", "eml"}


def load_document(path: Path, ext: str) -> DocumentModel:
    ext = ext.lower()
    if ext in TEXT_EXTS:
        return load_text(Path(path))
    raise ValueError(f"暂不支持的格式：{ext}")


def export_document(model: DocumentModel, masked_text: str, out_path: Path, ext: str) -> None:
    ext = ext.lower()
    if ext in TEXT_EXTS:
        write_text(model, masked_text, out_path)
        return
    raise ValueError(f"暂不支持的导出格式：{ext}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_text_ingest.py -v`
Expected: `3 passed`。

---

## Task 8: docx 解析与写回

**Files:**
- Create: `privacy-desk/backend/app/core/ingest/docx_loader.py`
- Modify: `privacy-desk/backend/app/core/ingest/writer.py`
- Modify: `privacy-desk/backend/app/core/ingest/registry.py`
- Create: `privacy-desk/backend/tests/test_docx_ingest.py`

- [ ] **Step 1: 写失败测试**

`tests/test_docx_ingest.py`:

```python
from docx import Document

from app.core.ingest.docx_loader import load_docx
from app.core.ingest.registry import export_document, load_document


def test_docx_roundtrip_preserves_table(tmp_path):
    source = tmp_path / "a.docx"
    doc = Document()
    doc.add_paragraph("联系人电话 13800138000")
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "身份证 11010519491231002X"
    doc.save(source)

    model = load_docx(source)
    assert "13800138000" in model.text
    assert "11010519491231002X" in model.text

    masked = model.text.replace("13800138000", "138****8000").replace(
        "11010519491231002X", "**************002X"
    )
    target = tmp_path / "out.docx"
    export_document(model, masked, target, "docx")

    reloaded = Document(target)
    assert reloaded.paragraphs[0].text == "联系人电话 138****8000"
    assert reloaded.tables[0].cell(0, 0).text == "身份证 **************002X"


def test_load_document_dispatches_docx(tmp_path):
    source = tmp_path / "b.docx"
    doc = Document()
    doc.add_paragraph("hello")
    doc.save(source)
    assert load_document(source, "docx").fmt == "docx"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_docx_ingest.py -v`
Expected: FAIL，`No module named 'app.core.ingest.docx_loader'`。

- [ ] **Step 3: 写实现**

`app/core/ingest/docx_loader.py`:

```python
from pathlib import Path

from docx import Document

from app.core.ingest.model import Block, DocumentModel, build_model


def load_docx(path: Path) -> DocumentModel:
    document = Document(str(path))
    blocks: list[Block] = []
    for paragraph in document.paragraphs:
        blocks.append(Block(kind="paragraph", text=paragraph.text, ref=paragraph))
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    blocks.append(
                        Block(kind="table_cell", text=paragraph.text, ref=(cell, paragraph))
                    )
    for section in document.sections:
        for paragraph in section.header.paragraphs:
            blocks.append(Block(kind="header", text=paragraph.text, ref=paragraph))
        for paragraph in section.footer.paragraphs:
            blocks.append(Block(kind="footer", text=paragraph.text, ref=paragraph))
    model = build_model(blocks, "docx")
    model.meta["docx"] = document
    return model
```

在 `app/core/ingest/writer.py` 追加：

```python
from docx.text.paragraph import Paragraph


def _set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    """保留段落样式，合并 run 后写入新文本。"""
    if not paragraph.runs:
        paragraph.add_run(text)
        return
    first = paragraph.runs[0]
    for run in list(paragraph.runs[1:]):
        run._element.getparent().remove(run._element)
    first.text = text


def write_docx(model: DocumentModel, masked_text: str, out_path: Path) -> None:
    document = model.meta["docx"]
    for block in model.blocks:
        new_text = masked_text[block.start:block.end]
        if block.kind == "table_cell":
            _, paragraph = block.ref
            _set_paragraph_text(paragraph, new_text)
        else:
            _set_paragraph_text(block.ref, new_text)
    document.save(str(out_path))
```

在 `app/core/ingest/registry.py` 更新为：

```python
from pathlib import Path

from app.core.ingest.docx_loader import load_docx
from app.core.ingest.model import DocumentModel
from app.core.ingest.text_loader import load_text
from app.core.ingest.writer import write_docx, write_text

TEXT_EXTS = {"txt", "md", "log", "py", "java", "js", "ts", "json", "csv", "eml"}


def load_document(path: Path, ext: str) -> DocumentModel:
    ext = ext.lower()
    if ext == "docx":
        return load_docx(Path(path))
    if ext in TEXT_EXTS:
        return load_text(Path(path))
    raise ValueError(f"暂不支持的格式：{ext}")


def export_document(model: DocumentModel, masked_text: str, out_path: Path, ext: str) -> None:
    ext = ext.lower()
    if ext == "docx":
        write_docx(model, masked_text, Path(out_path))
        return
    if ext in TEXT_EXTS:
        write_text(model, masked_text, Path(out_path))
        return
    raise ValueError(f"暂不支持的导出格式：{ext}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_docx_ingest.py -v`
Expected: `2 passed`。

---

## Task 9: pdf 解析与重建导出

**Files:**
- Create: `privacy-desk/backend/app/core/ingest/pdf_loader.py`
- Modify: `privacy-desk/backend/app/core/ingest/writer.py`
- Modify: `privacy-desk/backend/app/core/ingest/registry.py`
- Create: `privacy-desk/backend/tests/test_pdf_ingest.py`

- [ ] **Step 1: 写失败测试**

`tests/test_pdf_ingest.py`:

```python
from pathlib import Path

import pdfplumber
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.ingest.pdf_loader import load_pdf
from app.core.ingest.registry import export_document


def make_pdf(path: Path, text: str) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.drawString(72, 720, text)
    pdf.save()


def test_pdf_extract_and_rebuild(tmp_path):
    source = tmp_path / "a.pdf"
    make_pdf(source, "Phone 13800138000")
    model = load_pdf(source)
    assert "13800138000" in model.text

    masked = model.text.replace("13800138000", "138****8000")
    target = tmp_path / "out.pdf"
    export_document(model, masked, target, "pdf")
    assert target.read_bytes().startswith(b"%PDF")

    with pdfplumber.open(target) as pdf:
        assert "138****8000" in "\n".join(page.extract_text() or "" for page in pdf.pages)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pdf_ingest.py -v`
Expected: FAIL，`No module named 'app.core.ingest.pdf_loader'`。

- [ ] **Step 3: 写实现**

`app/core/ingest/pdf_loader.py`:

```python
from pathlib import Path

import pdfplumber

from app.core.ingest.model import Block, DocumentModel, build_model


def load_pdf(path: Path) -> DocumentModel:
    blocks: list[Block] = []
    page_texts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            page_texts.append(text)
            for line in text.split("\n"):
                blocks.append(Block(kind="paragraph", text=line))
    model = build_model(blocks, "pdf")
    model.meta["pages"] = page_texts
    return model
```

在 `app/core/ingest/writer.py` 追加：

```python
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph as PdfParagraph, SimpleDocTemplate

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
_PDF_STYLE = ParagraphStyle("cn", fontName="STSong-Light", fontSize=11, leading=18)


def write_pdf(masked_text: str, out_path: Path) -> None:
    story = []
    for line in masked_text.split("\n"):
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(PdfParagraph(safe or "&nbsp;", _PDF_STYLE))
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4)
    document.build(story)
    Path(out_path).write_bytes(buffer.getvalue())
```

在 `app/core/ingest/registry.py` 更新 load/export：

```python
from app.core.ingest.pdf_loader import load_pdf
from app.core.ingest.writer import write_docx, write_pdf, write_text

def load_document(path: Path, ext: str) -> DocumentModel:
    ext = ext.lower()
    if ext == "docx":
        return load_docx(Path(path))
    if ext == "pdf":
        return load_pdf(Path(path))
    if ext in TEXT_EXTS:
        return load_text(Path(path))
    raise ValueError(f"暂不支持的格式：{ext}")


def export_document(model: DocumentModel, masked_text: str, out_path: Path, ext: str) -> None:
    ext = ext.lower()
    if ext == "docx":
        write_docx(model, masked_text, Path(out_path))
        return
    if ext == "pdf":
        write_pdf(masked_text, Path(out_path))
        return
    if ext in TEXT_EXTS:
        write_text(model, masked_text, Path(out_path))
        return
    raise ValueError(f"暂不支持的导出格式：{ext}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pdf_ingest.py -v`
Expected: `1 passed`。

## Task 10: 分块、本地预遮蔽与 LLM 客户端

**Files:**
- Create: `privacy-desk/backend/app/core/detect/chunking.py`
- Create: `privacy-desk/backend/app/core/detect/pre_redact.py`
- Create: `privacy-desk/backend/app/llm/__init__.py`
- Create: `privacy-desk/backend/app/llm/client.py`
- Create: `privacy-desk/backend/resources/prompts/llm_extract.txt`
- Create: `privacy-desk/backend/tests/test_chunking.py`
- Create: `privacy-desk/backend/tests/test_llm_client.py`

- [ ] **Step 1: 写失败测试**

`tests/test_chunking.py`:

```python
from app.core.detect.chunking import chunk_text
from app.core.detect.pre_redact import pre_redact
from app.core.detect.rule_engine import Span


def test_short_text_single_chunk():
    assert chunk_text("hello", size=100, overlap=10) == [(0, 5)]


def test_chunks_cover_full_text():
    text = "word " * 500
    chunks = chunk_text(text, size=200, overlap=50)
    assert chunks[0][0] == 0
    assert chunks[-1][1] == len(text)
    for (_, end), (next_start, _) in zip(chunks, chunks[1:]):
        assert next_start <= end


def test_chunks_prefer_whitespace_boundary():
    text = "abcdefghij " * 50
    for start, end in chunk_text(text, size=100, overlap=10)[:-1]:
        assert text[end - 1] == " "


def test_pre_redact_keeps_length_and_masks_span():
    text = "张三电话13800138000"
    span = Span(4, 15, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    redacted = pre_redact(text, [span])
    assert len(redacted) == len(text)
    assert "13800138000" not in redacted
    assert redacted[:4] == "张三电话"
    assert redacted[4:15] == "█" * 11
```

`tests/test_llm_client.py`:

```python
import json

import httpx

from app.llm.client import NullLLM, OllamaLLM, OpenAICompatLLM, parse_json_array


def test_parse_json_array_with_code_fence():
    content = '```json\n[{"type":"NAME_CN","text":"张三","confidence":0.9}]\n```'
    items = parse_json_array(content)
    assert items[0]["text"] == "张三"


def test_parse_json_array_returns_empty_on_garbage():
    assert parse_json_array("抱歉，我无法识别") == []


def test_openai_client_sends_zero_temperature_and_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["temperature"] == 0
        assert payload["model"] == "test-model"
        assert request.headers["Authorization"] == "Bearer sk-test"
        content = '[{"type":"NAME_CN","text":"张三","confidence":0.9,"reason":"人名"}]'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatLLM("https://api.test/v1", "sk-test", "test-model", client=client)
    items = llm.extract("张三来了", [{"code": "NAME_CN", "name": "姓名", "hint": "中文人名"}])
    assert llm.available() is True
    assert items[0]["text"] == "张三"


def test_ollama_client_uses_json_format():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["format"] == "json"
        return httpx.Response(
            200,
            json={"message": {"content": '[{"type":"NAME_CN","text":"李四","confidence":0.8}]'}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OllamaLLM("http://127.0.0.1:11434", "qwen2.5:7b", client=client)
    items = llm.extract("李四", [{"code": "NAME_CN", "name": "姓名"}])
    assert items[0]["text"] == "李四"


def test_null_llm_is_unavailable():
    assert NullLLM().available() is False
    assert NullLLM().extract("abc", []) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_chunking.py tests/test_llm_client.py -v`
Expected: FAIL，`No module named 'app.core.detect.chunking'`。

- [ ] **Step 3: 写实现**

`app/core/detect/chunking.py`:

```python
def chunk_text(text: str, size: int = 2000, overlap: int = 100) -> list[tuple[int, int]]:
    """按字符数切块，优先在空白处断开，块间保留重叠。"""
    if not text:
        return [(0, 0)]
    if len(text) <= size:
        return [(0, len(text))]
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            newline = text.rfind("\n", start, end)
            space = text.rfind(" ", start, end)
            cut = max(newline, space)
            if cut > start + size // 2:
                end = cut + 1
        chunks.append((start, end))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
```

`app/core/detect/pre_redact.py`:

```python
from app.core.detect.rule_engine import Span


def pre_redact(text: str, spans: list[Span]) -> str:
    """对高敏片段做等长遮蔽，保证云端返回的片段仍能定位回原文。"""
    if not spans:
        return text
    chars = list(text)
    for span in spans:
        for index in range(span.start, min(span.end, len(chars))):
            chars[index] = "█"
    return "".join(chars)
```

`app/llm/client.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import httpx

DEFAULT_PROMPT = (
    "你是隐私信息识别引擎。只在给定文本中找出属于候选类型的隐私信息。"
    '输出严格 JSON 数组，元素为 {"type":"类型代码","text":"原文片段","confidence":0到1的小数,"reason":"简短理由"}。'
    "不要输出解释、代码块标记或多余文本；找不到时输出 []。"
)


class LLMError(RuntimeError):
    """大模型调用失败。"""


def load_prompt() -> str:
    path = Path(__file__).resolve().parents[2] / "resources" / "prompts" / "llm_extract.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return DEFAULT_PROMPT


def parse_json_array(content: str) -> list[dict]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


class BaseLLM:
    name = "base"

    def available(self) -> bool:
        return False

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        raise NotImplementedError


class NullLLM(BaseLLM):
    name = "rules"

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        return []


class OpenAICompatLLM(BaseLLM):
    name = "online"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)

    def available(self) -> bool:
        return bool(self._api_key)

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        hint_lines = "\n".join(
            f"- {item['code']}（{item['name']}）：{item.get('hint', '')}" for item in hints
        )
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": load_prompt()},
                {
                    "role": "user",
                    "content": f"候选类型：\n{hint_lines}\n\n待识别文本：\n{text}",
                },
            ],
        }
        try:
            response = self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMError(f"在线模型调用失败：{exc}") from exc
        return parse_json_array(content)


class OllamaLLM(BaseLLM):
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)

    def available(self) -> bool:
        return True

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        hint_lines = "\n".join(
            f"- {item['code']}（{item['name']}）：{item.get('hint', '')}" for item in hints
        )
        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": load_prompt()},
                {
                    "role": "user",
                    "content": f"候选类型：\n{hint_lines}\n\n待识别文本：\n{text}",
                },
            ],
        }
        try:
            response = self._client.post(self._url, json=payload)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except Exception as exc:
            raise LLMError(f"本地模型调用失败：{exc}") from exc
        return parse_json_array(content)
```

`resources/prompts/llm_extract.txt`:

```
你是隐私信息识别引擎，负责在中文文本中定位隐私信息。
只输出 JSON 数组，不要输出任何解释、代码块标记或前后缀文字。
数组元素格式：{"type": "类型代码", "text": "原文片段", "confidence": 0.0 到 1.0, "reason": "简短理由"}
规则：
1. text 必须逐字复制原文片段，不要改写、不要拼接、不要包含上下文。
2. 只识别候选类型中列出的类型，type 必须使用给定的类型代码。
3. 没有发现时输出 []。
4. 不要识别已被 █ 遮蔽的片段。
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_chunking.py tests/test_llm_client.py -v`
Expected: `9 passed`。

---

## Task 11: LLM 语义识别与结果融合

**Files:**
- Create: `privacy-desk/backend/app/core/detect/llm_engine.py`
- Create: `privacy-desk/backend/app/core/detect/fusion.py`
- Create: `privacy-desk/backend/tests/test_llm_engine.py`
- Create: `privacy-desk/backend/tests/test_fusion.py`

- [ ] **Step 1: 写失败测试**

`tests/test_llm_engine.py`:

```python
from pathlib import Path

from app.core.detect.llm_engine import LLMEngine
from app.core.detect.rule_engine import Span
from app.core.detect.types import load_builtin_types
from app.llm.client import BaseLLM

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


class RecordingLLM(BaseLLM):
    name = "online"

    def __init__(self):
        self.inputs: list[str] = []

    def available(self) -> bool:
        return True

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        self.inputs.append(text)
        return [{"type": "NAME_CN", "text": "张三", "confidence": 0.9, "reason": "人名"}]


def test_llm_engine_pre_redacts_phone_before_sending():
    text = "张三电话13800138000"
    high_span = Span(4, 15, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    client = RecordingLLM()
    engine = LLMEngine(client, load_builtin_types(RESOURCES), chunk_size=2000)
    spans = engine.detect(text, [high_span])
    assert "13800138000" not in client.inputs[0]
    assert "█" in client.inputs[0]
    name = next(item for item in spans if item.type_code == "NAME_CN")
    assert text[name.start:name.end] == "张三"
    assert name.source == "llm"


def test_llm_engine_returns_empty_when_unavailable():
    engine = LLMEngine(BaseLLM(), load_builtin_types(RESOURCES))
    assert engine.detect("张三", []) == []


def test_llm_engine_ignores_unknown_type_and_masked_fragment():
    class BadLLM(BaseLLM):
        def available(self):
            return True

        def extract(self, text, hints):
            return [
                {"type": "UNKNOWN", "text": "张三", "confidence": 0.9},
                {"type": "NAME_CN", "text": "██", "confidence": 0.9},
            ]

    engine = LLMEngine(BadLLM(), load_builtin_types(RESOURCES))
    assert engine.detect("张三", []) == []
```

`tests/test_fusion.py`:

```python
from pathlib import Path

from app.core.detect.fusion import fuse
from app.core.detect.rule_engine import Span
from app.core.detect.types import load_builtin_types

RESOURCES = Path(__file__).resolve().parents[1] / "resources"
TYPES = load_builtin_types(RESOURCES)


def test_rule_wins_for_phone_when_overlapping():
    rule = Span(0, 11, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    llm = Span(0, 11, "PHONE_CN", "13800138000", 0.80, "llm", "high")
    result = fuse([rule], [llm], TYPES)
    assert len(result) == 1
    assert result[0].source == "rule"


def test_non_overlapping_spans_both_kept():
    rule = Span(4, 15, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    llm = Span(0, 2, "NAME_CN", "张三", 0.85, "llm", "medium")
    result = fuse([rule], [llm], TYPES)
    assert [item.type_code for item in result] == ["NAME_CN", "PHONE_CN"]


def test_longer_span_wins_inside_same_type():
    short = Span(0, 2, "NAME_CN", "张三", 0.8, "llm", "medium")
    long = Span(0, 4, "NAME_CN", "张三丰丰", 0.8, "llm", "medium")
    result = fuse([], [short, long], TYPES)
    assert result[0].text == "张三丰丰"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_engine.py tests/test_fusion.py -v`
Expected: FAIL，`No module named 'app.core.detect.llm_engine'`。

- [ ] **Step 3: 写实现**

`app/core/detect/llm_engine.py`:

```python
from __future__ import annotations

from app.core.detect.chunking import chunk_text
from app.core.detect.pre_redact import pre_redact
from app.core.detect.rule_engine import Span, _find_all
from app.core.detect.types import TypeDefinition
from app.llm.client import BaseLLM


class LLMEngine:
    """把分块文本交给大模型，返回可直接定位的 span。"""

    def __init__(
        self,
        client: BaseLLM,
        types: list[TypeDefinition],
        chunk_size: int = 2000,
        chunk_overlap: int = 100,
    ) -> None:
        self._client = client
        self._types = types
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def detect(self, text: str, high_spans: list[Span]) -> list[Span]:
        if not self._client.available():
            return []
        hints = [
            {
                "code": definition.code,
                "name": definition.name,
                "hint": next(
                    (d.hint for d in definition.detectors if d.kind == "llm" and d.hint), ""
                ),
            }
            for definition in self._types
            if any(d.kind == "llm" for d in definition.detectors)
        ]
        allowed = {item["code"] for item in hints}
        levels = {definition.code: definition.level for definition in self._types}
        found: dict[tuple[int, int, str], Span] = {}
        for start, end in chunk_text(text, self._chunk_size, self._chunk_overlap):
            chunk = text[start:end]
            local_high = [
                Span(
                    span.start - start,
                    span.end - start,
                    span.type_code,
                    span.text,
                    span.confidence,
                    span.source,
                    span.level,
                )
                for span in high_spans
                if start <= span.start and span.end <= end
            ]
            redacted = pre_redact(chunk, local_high)
            for item in self._client.extract(redacted, hints):
                code = str(item.get("type") or "")
                fragment = str(item.get("text") or "")
                if code not in allowed or not fragment or "█" in fragment or len(fragment) > 200:
                    continue
                try:
                    confidence = float(item.get("confidence", 0.7))
                except (TypeError, ValueError):
                    confidence = 0.7
                for position in _find_all(chunk, fragment):
                    key = (start + position, start + position + len(fragment), code)
                    candidate = Span(
                        key[0],
                        key[1],
                        code,
                        fragment,
                        confidence,
                        "llm",
                        levels.get(code, "medium"),
                    )
                    if key not in found or candidate.confidence > found[key].confidence:
                        found[key] = candidate
        return sorted(found.values(), key=lambda item: (item.start, item.end))
```

`app/core/detect/fusion.py`:

```python
from dataclasses import replace

from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeDefinition

RULE_PRIORITY_TYPES = {
    "ID_CARD_CN",
    "BANK_CARD",
    "PHONE_CN",
    "EMAIL",
    "IPV4",
    "PLATE_CN",
    "PASSPORT_CN",
}


def fuse(rule_spans: list[Span], llm_spans: list[Span], types: list[TypeDefinition]) -> list[Span]:
    """按优先级贪心选取互不重叠的 span。"""
    levels = {definition.code: definition.level for definition in types}

    def score(span: Span) -> tuple[int, float, int]:
        return (
            1 if span.type_code in RULE_PRIORITY_TYPES and span.source == "rule" else 0,
            span.confidence,
            span.end - span.start,
        )

    accepted: list[Span] = []
    for candidate in sorted(rule_spans + llm_spans, key=score, reverse=True):
        if any(
            candidate.start < kept.end and kept.start < candidate.end for kept in accepted
        ):
            continue
        accepted.append(replace(candidate, level=levels.get(candidate.type_code, candidate.level)))
    return sorted(accepted, key=lambda item: (item.start, item.end, item.type_code))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_engine.py tests/test_fusion.py -v`
Expected: `6 passed`。

---

## Task 12: 脱敏算子与脱敏引擎

**Files:**
- Create: `privacy-desk/backend/app/core/mask/__init__.py`
- Create: `privacy-desk/backend/app/core/mask/operators.py`
- Create: `privacy-desk/backend/app/core/mask/engine.py`
- Create: `privacy-desk/backend/tests/test_mask.py`

- [ ] **Step 1: 写失败测试**

`tests/test_mask.py`:

```python
from pathlib import Path

from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeRegistry, load_builtin_types
from app.core.mask.engine import MaskEngine
from app.core.mask.operators import encrypt_value, fuzz_value, mask_value, replace_value
from app.core.security import crypto

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def registry():
    return TypeRegistry(load_builtin_types(RESOURCES))


def test_mask_value_keeps_edges():
    assert mask_value("13800138000", 0, 4) == "*******8000"
    assert mask_value("abc", 0, 0) == "***"


def test_replace_value():
    assert replace_value("张三", "[姓名_1]") == "[姓名_1]"


def test_fuzz_address_and_name():
    assert fuzz_value("北京市朝阳区建国路88号", "ADDRESS_CN") == "北京市某处"
    assert fuzz_value("张三", "NAME_CN") == "张*"


def test_encrypt_value_roundtrip():
    key = b"k" * 32
    aad = b"doc:SECRET_INFO:0"
    token = encrypt_value("机密内容", key, aad)
    assert token.startswith("ENC:")
    plain = crypto.decrypt(key, crypto.b64url_decode(token[4:]), aad)
    assert plain.decode("utf-8") == "机密内容"


def test_engine_uses_consistent_placeholder_for_same_name():
    spans = [
        Span(0, 2, "NAME_CN", "张三", 0.9, "llm", "medium"),
        Span(5, 7, "NAME_CN", "张三", 0.9, "llm", "medium"),
    ]
    engine = MaskEngine(b"k" * 32, registry(), {"NAME_CN": {"action": "replace"}})
    result = engine.apply("张三说，张三走了", spans)
    assert result.masked_text == "[姓名_1]说，[姓名_1]走了"
    assert result.mapping_size == 1


def test_engine_applies_default_mask_to_phone():
    span = Span(4, 15, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    engine = MaskEngine(b"k" * 32, registry())
    result = engine.apply("电话：13800138000", [span])
    assert result.masked_text == "电话：*******8000"
    assert result.applied[0]["action"] == "mask"


def test_engine_rejects_overlapping_spans():
    spans = [
        Span(0, 5, "PHONE_CN", "13800", 0.9, "rule", "high"),
        Span(3, 11, "NAME_CN", "某某某", 0.9, "llm", "medium"),
    ]
    engine = MaskEngine(b"k" * 32, registry())
    try:
        engine.apply("13800138000", spans)
    except ValueError as exc:
        assert "重叠" in str(exc)
    else:
        raise AssertionError("重叠 span 应报错")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mask.py -v`
Expected: FAIL，`No module named 'app.core.mask'`。

- [ ] **Step 3: 写实现**

`app/core/mask/operators.py`:

```python
import re

from app.core.security import crypto


def mask_value(value: str, keep_prefix: int = 0, keep_suffix: int = 0) -> str:
    if len(value) <= keep_prefix + keep_suffix:
        return "*" * len(value)
    head = value[:keep_prefix]
    tail = value[len(value) - keep_suffix:] if keep_suffix else ""
    return head + "*" * (len(value) - keep_prefix - keep_suffix) + tail


def replace_value(value: str, token: str) -> str:
    return token


def fuzz_value(value: str, type_code: str) -> str:
    if type_code == "ADDRESS_CN":
        match = re.match(r"^(.{2,6}?(?:省|市|自治区))", value)
        prefix = match.group(1) if match else value[:2]
        return f"{prefix}某处"
    if type_code == "NAME_CN":
        return value[:1] + "*" * max(len(value) - 1, 1)
    return "[已模糊]"


def encrypt_value(value: str, key: bytes, aad: bytes) -> str:
    token = crypto.encrypt(key, value.encode("utf-8"), aad)
    return "ENC:" + crypto.b64url_encode(token)
```

`app/core/mask/engine.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeRegistry
from app.core.mask.operators import encrypt_value, fuzz_value, mask_value


@dataclass
class MaskResult:
    masked_text: str
    applied: list[dict]
    mapping_size: int


def default_actions(registry: TypeRegistry) -> dict[str, dict]:
    return {
        definition.code: {
            "action": definition.default_action,
            "options": dict(definition.action_options),
        }
        for definition in registry.all()
    }


class MaskEngine:
    def __init__(
        self,
        data_key: bytes,
        registry: TypeRegistry,
        actions: dict[str, dict] | None = None,
    ) -> None:
        self._key = data_key
        self._registry = registry
        self._actions = {**default_actions(registry), **(actions or {})}

    def apply(self, text: str, spans: list[Span], aad_prefix: str = "doc") -> MaskResult:
        ordered = sorted(spans, key=lambda item: item.start)
        for previous, current in zip(ordered, ordered[1:]):
            if current.start < previous.end:
                raise ValueError("识别结果存在重叠，无法脱敏")
        counters: dict[str, int] = {}
        mapping: dict[tuple[str, str], str] = {}
        replacements: list[tuple[Span, str, str]] = []
        for span in ordered:
            spec = self._actions.get(span.type_code, {"action": "mask", "options": {}})
            action = spec.get("action", "mask")
            options = spec.get("options") or {}
            if action == "replace":
                key = (span.type_code, span.text)
                if key not in mapping:
                    count = counters.get(span.type_code, 0) + 1
                    counters[span.type_code] = count
                    label = self._registry.get(span.type_code).name
                    mapping[key] = f"[{label}_{count}]"
                replacement = mapping[key]
            elif action == "fuzz":
                replacement = fuzz_value(span.text, span.type_code)
            elif action == "encrypt":
                aad = f"{aad_prefix}:{span.type_code}:{span.start}".encode("utf-8")
                replacement = encrypt_value(span.text, self._key, aad)
            else:
                replacement = mask_value(
                    span.text,
                    keep_prefix=int(options.get("keepPrefix", 0)),
                    keep_suffix=int(options.get("keepSuffix", 0)),
                )
            replacements.append((span, action, replacement))
        masked = text
        for span, _, replacement in sorted(replacements, key=lambda item: -item[0].start):
            masked = masked[: span.start] + replacement + masked[span.end:]
        applied = [
            {
                "start": span.start,
                "end": span.end,
                "type_code": span.type_code,
                "action": action,
                "replacement": replacement,
            }
            for span, action, replacement in replacements
        ]
        return MaskResult(masked_text=masked, applied=applied, mapping_size=len(mapping))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mask.py -v`
Expected: `7 passed`。

---

## Task 13: 脱敏效果校验器

**Files:**
- Create: `privacy-desk/backend/app/core/mask/verifier.py`
- Create: `privacy-desk/backend/tests/test_verifier.py`

- [ ] **Step 1: 写失败测试**

`tests/test_verifier.py`:

```python
from pathlib import Path

from app.core.detect.rule_engine import RuleEngine
from app.core.detect.types import TypeRegistry, load_builtin_types
from app.core.mask.verifier import Verifier

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def verifier():
    types = load_builtin_types(RESOURCES)
    registry = TypeRegistry(types)
    return Verifier(registry, RuleEngine(types))


def test_passes_when_phone_is_masked():
    result = verifier().verify("电话13800138000", "电话*******8000")
    assert result.passed is True
    assert result.residuals == []
    assert result.metrics["residual_count"] == 0


def test_fails_when_high_risk_residual_remains():
    result = verifier().verify("电话13800138000", "电话13800138000")
    assert result.passed is False
    assert any("高敏" in issue for issue in result.issues)


def test_warns_on_extreme_length_change():
    result = verifier().verify("a" * 100, "a" * 10)
    assert any("长度" in issue for issue in result.issues)


def test_to_dict_contains_metrics():
    payload = verifier().verify("电话13800138000", "电话*******8000").to_dict()
    assert payload["passed"] is True
    assert "placeholder_density" in payload["metrics"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_verifier.py -v`
Expected: FAIL，`No module named 'app.core.mask.verifier'`。

- [ ] **Step 3: 写实现**

`app/core/mask/verifier.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.core.detect.rule_engine import RuleEngine, Span
from app.core.detect.types import TypeRegistry


@dataclass
class VerifyResult:
    passed: bool
    residuals: list[Span]
    metrics: dict
    issues: list[str]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "residuals": [span.to_dict() for span in self.residuals],
            "metrics": self.metrics,
            "issues": self.issues,
        }


class Verifier:
    def __init__(self, registry: TypeRegistry, rule_engine: RuleEngine) -> None:
        self._registry = registry
        self._rule_engine = rule_engine

    def verify(self, original_text: str, masked_text: str) -> VerifyResult:
        residuals = self._rule_engine.detect(masked_text)
        high = [span for span in residuals if span.level == "high"]
        ratio = len(masked_text) / max(len(original_text), 1)
        marker_count = sum(
            masked_text.count(char) for char in ("█", "*", "[", "ENC:")
        )
        density = marker_count / max(len(masked_text), 1)
        issues: list[str] = []
        if high:
            issues.append(f"仍有 {len(high)} 处高敏信息未清除")
        if ratio < 0.6:
            issues.append("文本长度变化超过 40%")
        if density > 0.15:
            issues.append("占位符密度超过 15%")
        metrics = {
            "ratio": round(ratio, 3),
            "placeholder_density": round(density, 3),
            "residual_count": len(residuals),
            "high_risk_residual_count": len(high),
        }
        return VerifyResult(
            passed=not issues, residuals=residuals, metrics=metrics, issues=issues
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_verifier.py -v`
Expected: `4 passed`。

---

## Task 14: 脱敏报告生成

**Files:**
- Create: `privacy-desk/backend/app/core/report/__init__.py`
- Create: `privacy-desk/backend/app/core/report/builder.py`
- Create: `privacy-desk/backend/tests/test_report.py`

- [ ] **Step 1: 写失败测试**

`tests/test_report.py`:

```python
from app.core.detect.rule_engine import Span
from app.core.mask.verifier import VerifyResult
from app.core.report.builder import build_json_report, build_pdf_report


def sample():
    span = Span(4, 15, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    verify = VerifyResult(
        passed=True,
        residuals=[],
        metrics={"ratio": 1.0, "placeholder_density": 0.1, "residual_count": 0},
        issues=[],
    )
    applied = [
        {
            "start": 4,
            "end": 15,
            "type_code": "PHONE_CN",
            "action": "mask",
            "replacement": "*******8000",
        }
    ]
    return build_json_report(
        "样例.txt", "rules", [span], applied, verify, {"detected": 1, "applied": 1}
    )


def test_json_report_contains_summary_and_detections():
    report = sample()
    assert report["document"] == "样例.txt"
    assert report["summary"]["detected"] == 1
    assert report["summary"]["by_type"]["PHONE_CN"] == 1
    assert report["summary"]["passed"] is True
    assert report["detections"][0]["type_code"] == "PHONE_CN"


def test_pdf_report_is_valid_pdf():
    payload = build_pdf_report(sample())
    assert payload.startswith(b"%PDF")
    assert len(payload) > 800
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_report.py -v`
Expected: FAIL，`No module named 'app.core.report'`。

- [ ] **Step 3: 写实现**

`app/core/report/builder.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.detect.rule_engine import Span
from app.core.mask.verifier import VerifyResult

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
_STYLE = ParagraphStyle("cn", fontName="STSong-Light", fontSize=10.5, leading=17)


def build_json_report(
    document: str,
    mode: str,
    detections: list[Span],
    applied: list[dict],
    verify: VerifyResult | None,
    stats: dict,
) -> dict:
    by_type: dict[str, int] = {}
    for span in detections:
        by_type[span.type_code] = by_type.get(span.type_code, 0) + 1
    return {
        "document": document,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "detected": len(detections),
            "by_type": by_type,
            "applied": len(applied),
            "residual": len(verify.residuals) if verify else None,
            "passed": verify.passed if verify else None,
        },
        "stats": stats,
        "metrics": verify.metrics if verify else {},
        "issues": verify.issues if verify else [],
        "detections": [span.to_dict() for span in detections],
        "applied": applied,
        "residuals": [span.to_dict() for span in verify.residuals] if verify else [],
    }


def build_pdf_report(report: dict) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title="脱敏报告")
    story = [Paragraph("文本隐私信息脱敏报告", ParagraphStyle(
        "title", parent=_STYLE, fontSize=18, leading=24, spaceAfter=12
    ))]
    summary = report["summary"]
    story.append(Paragraph(f"文件：{report['document']}", _STYLE))
    story.append(Paragraph(f"识别模式：{report['mode']}", _STYLE))
    story.append(Paragraph(f"生成时间：{report['generated_at']}", _STYLE))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"识别隐私信息 {summary['detected']} 处，脱敏 {summary['applied']} 处", _STYLE))
    story.append(Paragraph(
        f"校验结果：{'通过' if summary['passed'] else '未通过'}", _STYLE
    ))
    story.append(Spacer(1, 10))

    rows = [["隐私类型", "数量"]]
    for code, count in sorted(summary["by_type"].items()):
        rows.append([code, str(count)])
    table = Table(rows, colWidths=[280, 80])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8C4D6")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    if report["issues"]:
        story.append(Paragraph("校验问题", ParagraphStyle("h", parent=_STYLE, fontSize=12)))
        for issue in report["issues"]:
            story.append(Paragraph(f"· {issue}", _STYLE))
        story.append(Spacer(1, 8))

    story.append(Paragraph("脱敏明细", ParagraphStyle("h2", parent=_STYLE, fontSize=12)))
    detail_rows = [["起始", "结束", "类型", "方式", "替换结果"]]
    for item in report["applied"]:
        detail_rows.append([
            str(item["start"]),
            str(item["end"]),
            item["type_code"],
            item["action"],
            item["replacement"][:40],
        ])
    detail = Table(detail_rows, colWidths=[50, 50, 120, 60, 160])
    detail.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8C4D6")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(detail)
    document.build(story)
    return buffer.getvalue()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_report.py -v`
Expected: `2 passed`。

## Task 15: 应用上下文、LLM 服务与会话 API

**Files:**
- Create: `privacy-desk/backend/app/llm/service.py`
- Create: `privacy-desk/backend/app/context.py`
- Create: `privacy-desk/backend/app/api/__init__.py`
- Create: `privacy-desk/backend/app/api/deps.py`
- Create: `privacy-desk/backend/app/api/session.py`
- Modify: `privacy-desk/backend/app/main.py`
- Create: `privacy-desk/backend/tests/conftest.py`
- Create: `privacy-desk/backend/tests/test_session.py`

- [ ] **Step 1: 写失败测试**

`tests/conftest.py`:

```python
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
```

`tests/test_session.py`:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_session.py -v`
Expected: FAIL，`/api/v1/session/status` 返回 404。

- [ ] **Step 3: 写实现**

`app/llm/service.py`:

```python
from __future__ import annotations

from app.config import Settings
from app.core.detect.llm_engine import LLMEngine
from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeDefinition
from app.core.store.repository import Repository
from app.llm.client import LLMError, NullLLM, OllamaLLM, OpenAICompatLLM


class LLMService:
    def __init__(self, repo: Repository, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings

    def default_config(self) -> dict:
        return {
            "mode": "online" if self._settings.llm_api_key else "rules",
            "base_url": self._settings.llm_base_url,
            "model": self._settings.llm_model,
            "api_key": self._settings.llm_api_key or "",
            "ollama_url": self._settings.ollama_url,
            "ollama_model": self._settings.ollama_model,
        }

    def config(self) -> dict:
        try:
            stored = self._repo.get_setting("llm")
        except Exception:
            stored = None
        return {**self.default_config(), **(stored or {})}

    def set_config(self, config: dict) -> None:
        self._repo.set_setting("llm", config)

    def mode(self) -> str:
        config = self.config()
        if config.get("mode") == "online" and config.get("api_key"):
            return "online"
        if config.get("mode") == "ollama":
            return "ollama"
        return "rules"

    def build_client(self):
        config = self.config()
        if config.get("mode") == "online" and config.get("api_key"):
            return OpenAICompatLLM(
                config["base_url"], config["api_key"], config["model"]
            )
        if config.get("mode") == "ollama":
            return OllamaLLM(config["ollama_url"], config["ollama_model"])
        return NullLLM()

    def detect(
        self, text: str, high_spans: list[Span], types: list[TypeDefinition]
    ) -> tuple[list[Span], str]:
        mode = self.mode()
        if mode == "rules":
            return [], "rules"
        engine = LLMEngine(
            self.build_client(),
            types,
            chunk_size=self._settings.chunk_size,
            chunk_overlap=self._settings.chunk_overlap,
        )
        try:
            return engine.detect(text, high_spans), mode
        except LLMError:
            return [], "rules"
```

`app/context.py`:

```python
from dataclasses import dataclass

from app.config import Settings
from app.core.detect.types import TypeRegistry, load_builtin_types
from app.core.security.vault import Vault
from app.core.store.db import Database
from app.core.store.repository import Repository
from app.llm.service import LLMService


@dataclass
class AppContext:
    settings: Settings
    db: Database
    vault: Vault
    repo: Repository
    types: TypeRegistry
    llm_service: LLMService


def build_context(settings: Settings) -> AppContext:
    db = Database(settings.db_path)
    db.init()
    vault = Vault()
    repo = Repository(db, vault)
    registry = TypeRegistry(load_builtin_types(settings.resources_dir))
    return AppContext(
        settings=settings,
        db=db,
        vault=vault,
        repo=repo,
        types=registry,
        llm_service=LLMService(repo, settings),
    )
```

`app/api/deps.py`:

```python
from fastapi import HTTPException, Request

from app.context import AppContext


def get_context(request: Request) -> AppContext:
    return request.app.state.ctx


def require_unlocked(ctx: AppContext) -> None:
    if not ctx.vault.unlocked:
        raise HTTPException(401, "请先输入主密码解锁")
```

`app/api/session.py`:

```python
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_context
from app.context import AppContext
from app.core.security import keys

router = APIRouter(prefix="/session", tags=["session"])
_FAILURES: dict[int, int] = {}


class PasswordIn(BaseModel):
    password: str = Field(min_length=8)


def _meta_get(ctx: AppContext, key: str):
    with ctx.db.connect() as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return None if row is None else row["value"]


def _meta_set(ctx: AppContext, key: str, value: bytes) -> None:
    with ctx.db.connect() as conn:
        conn.execute(
            "INSERT INTO app_meta(key,value) VALUES(?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def _status(ctx: AppContext) -> dict:
    return {
        "initialized": _meta_get(ctx, "salt") is not None,
        "unlocked": ctx.vault.unlocked,
        "llm_mode": ctx.llm_service.mode(),
    }


@router.get("/status")
def status(ctx: AppContext = Depends(get_context)) -> dict:
    return _status(ctx)


@router.post("/setup")
def setup(payload: PasswordIn, ctx: AppContext = Depends(get_context)) -> dict:
    if _meta_get(ctx, "salt") is not None:
        raise HTTPException(409, "系统已初始化，请直接解锁")
    salt = keys.new_salt()
    master = keys.derive_master_key(payload.password, salt)
    _meta_set(ctx, "salt", salt)
    _meta_set(ctx, "canary", keys.seal_canary(master))
    ctx.vault.set_master(master)
    ctx.types.load_from_repo(ctx.repo)
    ctx.repo.audit("session.setup", {})
    return _status(ctx)


@router.post("/unlock")
def unlock(
    payload: PasswordIn, request: Request, ctx: AppContext = Depends(get_context)
) -> dict:
    salt = _meta_get(ctx, "salt")
    canary = _meta_get(ctx, "canary")
    if salt is None or canary is None:
        raise HTTPException(400, "系统尚未初始化")
    master = keys.derive_master_key(payload.password, salt)
    if not keys.verify_canary(master, canary):
        app_key = id(request.app)
        count = _FAILURES.get(app_key, 0) + 1
        _FAILURES[app_key] = count
        if count >= 3:
            time.sleep(min(0.5 * (2 ** (count - 3)), 4))
        raise HTTPException(401, "主密码错误")
    _FAILURES.pop(id(request.app), None)
    ctx.vault.set_master(master)
    ctx.types.load_from_repo(ctx.repo)
    ctx.repo.audit("session.unlock", {})
    return _status(ctx)


@router.post("/lock")
def lock(ctx: AppContext = Depends(get_context)) -> dict:
    ctx.vault.lock()
    return _status(ctx)
```

`app/api/__init__.py` 为空文件。

修改 `app/main.py`：

```python
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api import session
from app.config import Settings
from app.context import build_context


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    ctx = build_context(settings)
    app = FastAPI(title="Privacy Desk", version="0.1.0")
    app.state.ctx = ctx
    app.state.settings = settings

    @app.middleware("http")
    async def token_guard(request, call_next):
        if settings.app_token and request.url.path.startswith("/api/"):
            if request.headers.get("X-App-Token") != settings.app_token:
                return JSONResponse({"detail": "启动令牌无效"}, status_code=401)
        return await call_next(request)

    app.include_router(session.router, prefix="/api/v1")

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok", "llm_mode": ctx.llm_service.mode()}

    return app
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_session.py -v`
Expected: `5 passed`。

---

## Task 16: 处理流水线与文档 API

**Files:**
- Create: `privacy-desk/backend/app/core/pipeline.py`
- Create: `privacy-desk/backend/app/api/documents.py`
- Modify: `privacy-desk/backend/app/main.py`
- Create: `privacy-desk/backend/tests/test_documents_api.py`

- [ ] **Step 1: 写失败测试**

`tests/test_documents_api.py`:

```python
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

    report = client.get(
        f"/api/v1/documents/{doc_id}/export", params={"kind": "report", "fmt": "json"}
    )
    assert report.status_code == 200
    assert report.json()["summary"]["detected"] >= 2

    exported = client.get(
        f"/api/v1/documents/{doc_id}/export", params={"kind": "masked", "fmt": "txt"}
    )
    assert exported.status_code == 200
    assert "13800138000" not in exported.text


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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_documents_api.py -v`
Expected: FAIL，`/api/v1/documents` 返回 403 或 404。

- [ ] **Step 3: 写实现**

`app/core/pipeline.py`:

```python
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.detect.fusion import fuse
from app.core.detect.rule_engine import RuleEngine, Span
from app.core.ingest.registry import load_document
from app.core.mask.engine import MaskEngine
from app.core.mask.verifier import Verifier
from app.core.report.builder import build_json_report, build_pdf_report

if TYPE_CHECKING:
    from app.context import AppContext

ALLOWED_EXTS = {
    "txt", "md", "log", "py", "java", "js", "ts", "json", "csv", "eml", "docx", "pdf", "doc",
}


def convert_doc_to_docx(source: Path, workdir: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ValueError("未检测到 LibreOffice，无法处理 .doc 文件")
    subprocess.run(
        [soffice, "--headless", "--convert-to", "docx", "--outdir", str(workdir), str(source)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    target = workdir / (source.stem + ".docx")
    if not target.exists():
        raise ValueError("LibreOffice 转换失败")
    return target


def create_document_from_bytes(ctx: "AppContext", filename: str, raw: bytes) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"不支持的文件类型：{ext or '未知'}")
    if len(raw) > ctx.settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"文件超过 {ctx.settings.max_upload_mb}MB 限制")
    safe_name = Path(filename).name
    with tempfile.TemporaryDirectory() as temp_dir:
        workdir = Path(temp_dir)
        path = workdir / safe_name
        path.write_bytes(raw)
        if ext == "doc":
            path = convert_doc_to_docx(path, workdir)
            ext = "docx"
        model = load_document(path, ext)
        text = model.text
        source_bytes = path.read_bytes()
    doc_id = ctx.repo.create_document(
        safe_name, ext, text, hashlib.sha256(raw).hexdigest()
    )
    ctx.repo.save_blob(doc_id, "source", source_bytes)
    ctx.repo.audit("document.create", {"doc_id": doc_id, "ext": ext, "size": len(raw)})
    return doc_id


def _spans_from_rows(rows: list[dict]) -> list[Span]:
    return [
        Span(
            row["start"],
            row["end"],
            row["type_code"],
            row["text"],
            row["confidence"],
            row["source"],
            row["level"],
        )
        for row in rows
    ]


def detect_document(ctx: "AppContext", doc_id: str, use_llm: bool = True) -> dict:
    text = ctx.repo.get_text(doc_id, "original")
    types = ctx.types.list()
    rule_spans = RuleEngine(types).detect(text)
    llm_spans: list[Span] = []
    mode = "rules"
    if use_llm:
        llm_spans, mode = ctx.llm_service.detect(text, rule_spans, types)
    spans = fuse(rule_spans, llm_spans, types)
    version_id = ctx.repo.latest_version_id(doc_id, "original")
    ctx.repo.save_detections(doc_id, version_id, spans)
    ctx.repo.update_status(doc_id, "detected")
    ctx.repo.audit("document.detect", {"doc_id": doc_id, "count": len(spans), "mode": mode})
    return {"spans": spans, "mode": mode, "text_length": len(text)}


def mask_document(
    ctx: "AppContext",
    doc_id: str,
    actions: dict[str, dict] | None = None,
    verify: bool = True,
) -> dict:
    original = ctx.repo.get_text(doc_id, "original")
    spans = _spans_from_rows(ctx.repo.get_detections(doc_id))
    started = time.perf_counter()
    engine = MaskEngine(ctx.vault.data_key(), ctx.types, actions)
    result = engine.apply(original, spans, aad_prefix=doc_id)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    verify_result = None
    if verify:
        verify_result = Verifier(ctx.types, RuleEngine(ctx.types.list())).verify(
            original, result.masked_text
        )
    ctx.repo.save_version(doc_id, "masked", result.masked_text)
    stats = {
        "detected": len(spans),
        "applied": len(result.applied),
        "mapping": result.mapping_size,
        "elapsed_ms": elapsed_ms,
    }
    job_id = ctx.repo.save_mask_job(doc_id, {"actions": actions or {}}, stats)
    report = build_json_report(
        ctx.repo.get_document(doc_id)["name"],
        ctx.llm_service.mode(),
        spans,
        result.applied,
        verify_result,
        stats,
    )
    ctx.repo.save_report(
        doc_id, job_id, "json", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    )
    ctx.repo.save_report(doc_id, job_id, "pdf", build_pdf_report(report))
    status = "verified" if verify_result and verify_result.passed else "masked"
    ctx.repo.update_status(doc_id, status)
    ctx.repo.audit(
        "document.mask", {"doc_id": doc_id, "detected": len(spans), "applied": len(result.applied)}
    )
    return {
        "masked_text": result.masked_text,
        "applied": result.applied,
        "stats": stats,
        "verify": verify_result.to_dict() if verify_result else None,
        "report": report,
        "job_id": job_id,
    }


def compare_document(ctx: "AppContext", doc_id: str) -> dict:
    return {
        "original": ctx.repo.get_text(doc_id, "original"),
        "masked": ctx.repo.get_text(doc_id, "masked"),
        "detections": ctx.repo.get_detections(doc_id),
    }


def verify_document(ctx: "AppContext", doc_id: str) -> dict:
    original = ctx.repo.get_text(doc_id, "original")
    masked = ctx.repo.get_text(doc_id, "masked")
    result = Verifier(ctx.types, RuleEngine(ctx.types.list())).verify(original, masked)
    ctx.repo.update_status(doc_id, "verified" if result.passed else "masked")
    return result.to_dict()


def process_batch(ctx: "AppContext", batch_id: str, item_ids: list[str], items: list[tuple[str, bytes]]) -> None:
    def run_one(item_id: str, item: tuple[str, bytes]) -> None:
        filename, raw = item
        try:
            doc_id = create_document_from_bytes(ctx, filename, raw)
            detect_document(ctx, doc_id, use_llm=True)
            mask_document(ctx, doc_id, verify=True)
            ctx.repo.update_batch_item(item_id, "done", "", doc_id)
        except Exception as exc:
            ctx.repo.update_batch_item(item_id, "failed", str(exc)[:200])

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(run_one, item_id, item)
            for item_id, item in zip(item_ids, items)
        ]
        for future in futures:
            future.result()
    ctx.repo.finish_batch(batch_id)
```

`app/api/documents.py`:

```python
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.api.deps import get_context, require_unlocked
from app.context import AppContext
from app.core import pipeline
from app.core.ingest.docx_loader import load_docx
from app.core.ingest.registry import export_document
from app.core.ingest.writer import write_pdf

router = APIRouter(prefix="/documents", tags=["documents"])


class DetectIn(BaseModel):
    use_llm: bool = True


class MaskIn(BaseModel):
    actions: dict[str, dict] = {}
    verify: bool = True


class EditIn(BaseModel):
    text: str


def _not_found() -> HTTPException:
    return HTTPException(404, "文档不存在")


@router.post("")
async def upload(
    file: UploadFile = File(...), ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    raw = await file.read()
    try:
        doc_id = pipeline.create_document_from_bytes(ctx, file.filename or "upload.txt", raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ctx.repo.get_document(doc_id)


@router.get("")
def list_documents(ctx: AppContext = Depends(get_context)) -> list[dict]:
    require_unlocked(ctx)
    return ctx.repo.list_documents()


@router.get("/{doc_id}")
def get_document(doc_id: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        document = ctx.repo.get_document(doc_id)
        document["text"] = ctx.repo.get_text(doc_id, "original")
        document["detections"] = ctx.repo.get_detections(doc_id)
        return document
    except KeyError as exc:
        raise _not_found() from exc


@router.put("/{doc_id}/content")
def edit_content(
    doc_id: str, payload: EditIn, ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    try:
        ctx.repo.get_document(doc_id)
    except KeyError as exc:
        raise _not_found() from exc
    ctx.repo.save_version(doc_id, "original", payload.text)
    ctx.repo.update_status(doc_id, "uploaded")
    return {"id": doc_id, "length": len(payload.text)}


@router.post("/{doc_id}/detect")
def detect(
    doc_id: str, payload: DetectIn, ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    try:
        result = pipeline.detect_document(ctx, doc_id, payload.use_llm)
    except KeyError as exc:
        raise _not_found() from exc
    return {
        "spans": [span.to_dict() for span in result["spans"]],
        "mode": result["mode"],
        "text_length": result["text_length"],
    }


@router.post("/{doc_id}/mask")
def mask(
    doc_id: str, payload: MaskIn, ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    try:
        result = pipeline.mask_document(ctx, doc_id, payload.actions, payload.verify)
    except KeyError as exc:
        raise _not_found() from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "masked_text": result["masked_text"],
        "applied": result["applied"],
        "stats": result["stats"],
        "verify": result["verify"],
        "job_id": result["job_id"],
        "summary": result["report"]["summary"],
    }


@router.post("/{doc_id}/verify")
def verify(doc_id: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        return pipeline.verify_document(ctx, doc_id)
    except KeyError as exc:
        raise HTTPException(404, "文档或脱敏结果不存在") from exc


@router.get("/{doc_id}/compare")
def compare(doc_id: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        return pipeline.compare_document(ctx, doc_id)
    except KeyError as exc:
        raise HTTPException(404, "文档或脱敏结果不存在") from exc


@router.get("/{doc_id}/export")
def export(
    doc_id: str,
    kind: str = "masked",
    fmt: str = "auto",
    ctx: AppContext = Depends(get_context),
):
    require_unlocked(ctx)
    try:
        document = ctx.repo.get_document(doc_id)
        if kind == "report":
            report_format = "pdf" if fmt == "pdf" else "json"
            payload = ctx.repo.latest_report(doc_id, report_format)
            media = "application/pdf" if report_format == "pdf" else "application/json"
            return Response(
                payload,
                media_type=media,
                headers={"Content-Disposition": f'attachment; filename="report.{report_format}"'},
            )
        masked = ctx.repo.get_text(doc_id, "masked")
        ext = document["ext"] if fmt == "auto" else fmt
        workdir = Path(tempfile.mkdtemp())
        target = workdir / f"masked.{ext}"
        if ext == "docx":
            source_path = workdir / "source.docx"
            source_path.write_bytes(ctx.repo.get_blob(doc_id, "source"))
            export_document(load_docx(source_path), masked, target, "docx")
        elif ext == "pdf":
            write_pdf(masked, target)
        else:
            target.write_text(masked, encoding="utf-8")
        return FileResponse(target, filename=f"masked.{ext}")
    except KeyError as exc:
        raise HTTPException(404, "文档或导出结果不存在") from exc
```

在 `app/main.py` 中增加导入与挂载：

```python
from app.api import documents, session
...
    app.include_router(session.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_documents_api.py -v`
Expected: `2 passed`。

---

## Task 17: 类型、设置与批量 API

**Files:**
- Create: `privacy-desk/backend/app/api/types.py`
- Create: `privacy-desk/backend/app/api/settings.py`
- Create: `privacy-desk/backend/app/api/batches.py`
- Modify: `privacy-desk/backend/app/main.py`
- Create: `privacy-desk/backend/tests/test_admin_api.py`

- [ ] **Step 1: 写失败测试**

`tests/test_admin_api.py`:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_api.py -v`
Expected: FAIL，`/api/v1/types` 返回 404。

- [ ] **Step 3: 写实现**

`app/api/types.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_context, require_unlocked
from app.context import AppContext
from app.core.detect.rule_engine import RuleEngine
from app.core.detect.types import TypeDefinition

router = APIRouter(prefix="/types", tags=["types"])


class TypeTestIn(BaseModel):
    type: TypeDefinition
    samples: list[str]


@router.get("")
def list_types(ctx: AppContext = Depends(get_context)) -> list[dict]:
    require_unlocked(ctx)
    return [item.model_dump(by_alias=True) for item in ctx.types.all()]


@router.put("/{code}")
def save_type(
    code: str, payload: TypeDefinition, ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    if payload.code != code:
        raise HTTPException(400, "路径中的类型代码与请求体不一致")
    if not payload.detectors:
        raise HTTPException(400, "至少需要一个识别器")
    ctx.types.upsert(payload)
    ctx.repo.save_type(code, payload.model_dump(by_alias=True))
    ctx.repo.audit("type.save", {"code": code})
    return payload.model_dump(by_alias=True)


@router.post("/test")
def test_type(payload: TypeTestIn, ctx: AppContext = Depends(get_context)) -> dict:
    engine = RuleEngine([payload.type])
    results = [
        {"sample": sample, "spans": [span.to_dict() for span in engine.detect(sample)]}
        for sample in payload.samples
    ]
    return {"results": results}
```

`app/api/settings.py`:

```python
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_context, require_unlocked
from app.context import AppContext

router = APIRouter(prefix="/settings", tags=["settings"])


class LLMConfig(BaseModel):
    mode: Literal["online", "ollama", "rules"] = "online"
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    api_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"


def _public(config: dict) -> dict:
    return {
        "mode": config.get("mode", "rules"),
        "base_url": config.get("base_url", ""),
        "model": config.get("model", ""),
        "ollama_url": config.get("ollama_url", ""),
        "ollama_model": config.get("ollama_model", ""),
        "has_key": bool(config.get("api_key")),
    }


@router.get("/llm")
def get_llm(ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    return _public(ctx.llm_service.config())


@router.put("/llm")
def put_llm(payload: LLMConfig, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    current = ctx.llm_service.config()
    config = payload.model_dump()
    if not config["api_key"]:
        config["api_key"] = current.get("api_key", "")
    ctx.llm_service.set_config(config)
    ctx.repo.audit("settings.llm", {"mode": config["mode"]})
    return _public(config)


@router.post("/llm/test")
def test_llm(ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    mode = ctx.llm_service.mode()
    if mode == "rules":
        return {"ok": False, "mode": "rules", "message": "未配置在线或本地模型"}
    client = ctx.llm_service.build_client()
    started = time.perf_counter()
    try:
        items = client.extract(
            "联系人张三，电话13800138000",
            [{"code": "NAME_CN", "name": "姓名", "hint": "中文人名"}],
        )
    except Exception as exc:
        raise HTTPException(502, f"模型调用失败：{exc}") from exc
    return {
        "ok": True,
        "mode": mode,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "items": len(items),
    }
```

`app/api/batches.py`:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.api.deps import get_context, require_unlocked
from app.context import AppContext
from app.core import pipeline

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("")
async def create_batch(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    ctx: AppContext = Depends(get_context),
) -> dict:
    require_unlocked(ctx)
    if not files:
        raise HTTPException(400, "请选择文件")
    payload = [(file.filename or "upload.txt", await file.read()) for file in files]
    batch_id = ctx.repo.create_batch(len(payload))
    item_ids = [ctx.repo.add_batch_item(batch_id) for _ in payload]
    background.add_task(pipeline.process_batch, ctx, batch_id, item_ids, payload)
    return {"id": batch_id, "total": len(payload)}


@router.get("/{batch_id}")
def get_batch(batch_id: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        return ctx.repo.get_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(404, "批量任务不存在") from exc
```

在 `app/main.py` 中挂载：

```python
from app.api import batches, documents, session, settings, types
...
    app.include_router(session.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(types.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")
    app.include_router(batches.router, prefix="/api/v1")
```

注意 `app/api/settings.py` 与 `app/config.py` 模块名不同，避免导入冲突。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_api.py -v`
Expected: `4 passed`。

---

## Task 18: 加密资源与完整性校验

**Files:**
- Create: `privacy-desk/backend/app/core/security/resources.py`
- Create: `privacy-desk/backend/app/core/security/integrity.py`
- Modify: `privacy-desk/backend/app/core/detect/types.py`
- Modify: `privacy-desk/backend/app/llm/client.py`
- Create: `privacy-desk/backend/build/encrypt_resources.py`
- Create: `privacy-desk/backend/tests/test_resources.py`
- Create: `privacy-desk/backend/tests/test_integrity.py`

- [ ] **Step 1: 写失败测试**

`tests/test_resources.py`:

```python
import json
from pathlib import Path

import pytest

from app.core.detect.types import load_builtin_types
from app.core.security.resources import load_bundle, pack_bundle

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def test_pack_and_load_bundle(tmp_path):
    pack_bundle(RESOURCES, tmp_path / "rules.enc")
    bundle = load_bundle(tmp_path)
    assert len(bundle["types"]) == 10
    assert "隐私" in bundle["prompt"]


def test_tampered_bundle_fails(tmp_path):
    target = tmp_path / "rules.enc"
    pack_bundle(RESOURCES, target)
    blob = bytearray(target.read_bytes())
    blob[-1] ^= 0xFF
    target.write_bytes(bytes(blob))
    with pytest.raises(Exception):
        load_bundle(tmp_path)


def test_load_builtin_types_prefers_encrypted_bundle(tmp_path):
    original = json.loads((RESOURCES / "types.default.json").read_text(encoding="utf-8"))
    (tmp_path / "types.default.json").write_text(
        json.dumps(original[:1], ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "llm_extract.txt").write_text("提示词", encoding="utf-8")
    bundle = {
        "types": original,
        "prompt": "来自加密包",
    }
    from app.core.security import crypto
    from app.core.security.resources import resource_key

    payload = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    (tmp_path / "rules.enc").write_bytes(crypto.encrypt(resource_key(), payload, b"rules"))
    assert len(load_builtin_types(tmp_path)) == 10
```

`tests/test_integrity.py`:

```python
from app.core.security.integrity import (
    build_manifest,
    sign_manifest,
    verify_manifest,
)


def test_manifest_detects_tamper(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    manifest = build_manifest(tmp_path)
    signature = sign_manifest(manifest)
    assert verify_manifest(tmp_path, manifest, signature) == []

    (tmp_path / "a.txt").write_text("changed", encoding="utf-8")
    problems = verify_manifest(tmp_path, manifest, signature)
    assert any("篡改" in item for item in problems)


def test_bad_signature_rejected(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    manifest = build_manifest(tmp_path)
    problems = verify_manifest(tmp_path, manifest, "bad-signature")
    assert problems and "签名" in problems[0]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_resources.py tests/test_integrity.py -v`
Expected: FAIL，`No module named 'app.core.security.resources'`。

- [ ] **Step 3: 写实现**

`app/core/security/resources.py`:

```python
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.security import crypto

BUNDLE_VERSION = "v1"
_SEED = b"privacy-desk-resources"


def resource_key(version: str = BUNDLE_VERSION) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"resources/" + version.encode("utf-8"),
    ).derive(_SEED)


def pack_bundle(resources_dir: Path, out_path: Path) -> None:
    bundle = {
        "types": json.loads((resources_dir / "types.default.json").read_text(encoding="utf-8")),
        "prompt": (resources_dir / "prompts" / "llm_extract.txt").read_text(encoding="utf-8"),
    }
    payload = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    out_path.write_bytes(crypto.encrypt(resource_key(), payload, b"rules"))


def load_bundle(resources_dir: Path) -> dict:
    encrypted = resources_dir / "rules.enc"
    if encrypted.exists():
        payload = crypto.decrypt(resource_key(), encrypted.read_bytes(), b"rules")
        return json.loads(payload.decode("utf-8"))
    return {
        "types": json.loads((resources_dir / "types.default.json").read_text(encoding="utf-8")),
        "prompt": (resources_dir / "prompts" / "llm_extract.txt").read_text(encoding="utf-8"),
    }


def load_prompt(resources_dir: Path) -> str:
    return load_bundle(resources_dir)["prompt"]
```

`app/core/security/integrity.py`:

```python
import hashlib
import hmac
import json
from pathlib import Path

INTEGRITY_SECRET = b"privacy-desk-integrity-v1"


def build_manifest(root: Path) -> dict:
    files: dict[str, str] = {}
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": files}


def sign_manifest(manifest: dict, secret: bytes = INTEGRITY_SECRET) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret, canonical, hashlib.sha256).hexdigest()


def verify_manifest(
    root: Path, manifest: dict, signature: str, secret: bytes = INTEGRITY_SECRET
) -> list[str]:
    if not hmac.compare_digest(sign_manifest(manifest, secret), signature):
        return ["manifest 签名无效"]
    problems: list[str] = []
    for relative, expected in manifest["files"].items():
        path = Path(root) / relative
        if not path.exists():
            problems.append(f"缺失文件：{relative}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            problems.append(f"文件被篡改：{relative}")
    return problems
```

修改 `app/core/detect/types.py` 中的 `load_builtin_types`：

```python
def load_builtin_types(resources_dir: Path) -> list[TypeDefinition]:
    from app.core.security.resources import load_bundle

    payload = load_bundle(resources_dir)["types"]
    return [TypeDefinition.model_validate(item) for item in payload]
```

修改 `app/llm/client.py` 中的 `load_prompt`：

```python
def load_prompt() -> str:
    try:
        from app.core.security.resources import load_prompt as load_resource_prompt

        return load_resource_prompt(Path(__file__).resolve().parents[2] / "resources")
    except Exception:
        return DEFAULT_PROMPT
```

`build/encrypt_resources.py`:

```python
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.security.integrity import build_manifest, sign_manifest  # noqa: E402
from app.core.security.resources import pack_bundle  # noqa: E402


def main() -> None:
    resources = BACKEND / "resources"
    pack_bundle(resources, resources / "rules.enc")
    print(f"已生成加密资源：{resources / 'rules.enc'}")

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "dist" / "privacy-backend"
    if target.exists():
        manifest = build_manifest(target)
        payload = {"manifest": manifest, "signature": sign_manifest(manifest)}
        (target / "manifest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已生成完整性清单：{target / 'manifest.json'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_resources.py tests/test_integrity.py -v`
Expected: `5 passed`。

- [ ] **Step 5: 运行全量后端测试**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: 全部通过，约 40 个用例。

---

## 自检结果

- **Spec 覆盖**：类型体系（Task 5）、规则+LLM+融合（Task 6/10/11）、预遮蔽上云（Task 10/11）、四种脱敏与一致性映射（Task 12）、校验器（Task 13）、多格式解析与导出（Task 7/8/9）、批量（Task 17）、报告（Task 14）、加密存储与主密码（Task 2/3/4/15）、算法资源加密与完整性（Task 18）均有对应任务。
- **占位符**：无 TBD/TODO；每个代码步骤给出完整实现。
- **类型一致性**：`Span`、`TypeDefinition`、`TypeRegistry`、`MaskResult`、`VerifyResult` 在任务间签名一致；API 字段与设计文档一致。


