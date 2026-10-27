"""SQLite 存储层：统一连接参数并建表；敏感列以 BLOB 存放加密后的密文。"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

# 业务表的 doc_id 均声明 ON DELETE CASCADE，删除文档时版本/识别/作业/报告一并清除；
# 仅 batch_items.doc_id 无外键约束，删除前需由调用方先置空，否则会留下悬空引用。
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
        # 外键检查是连接级开关，SQLite 默认关闭；不显式打开则 ON DELETE CASCADE 不会生效
        conn.execute("PRAGMA foreign_keys=ON")
        # WAL 与忙等待降低批量并发写入时的锁冲突
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            # 仅在上下文正常退出时提交；异常时 close() 会丢弃未提交的改动
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
