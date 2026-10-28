"""运行期配置：集中从环境变量读取，便于打包后的桌面端在不改代码的前提下覆盖。"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _default_resources() -> Path:
    """源码运行时用 backend/resources，PyInstaller 冻结后优先用 _MEIPASS/resources。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return Path(os.environ.get("PRIVACY_DESK_RESOURCES", str(base / "resources")))


@dataclass(frozen=True)
class Settings:
    """运行期配置；测试可传入临时目录。"""

    data_dir: Path = field(
        # 数据库默认放用户主目录而非安装目录，避免只读安装路径和升级覆盖导致丢数据
        default_factory=lambda: Path(_env("PRIVACY_DESK_DATA", str(Path.home() / ".privacy-desk")))
    )
    resources_dir: Path = field(default_factory=_default_resources)
    # 启动令牌只从环境变量读取，运行期不落库，也不随接口回传
    app_token: str | None = field(default_factory=lambda: os.environ.get("APP_TOKEN"))
    max_upload_mb: int = 20
    max_docs: int = field(default_factory=lambda: _env_int("PRIVACY_DESK_MAX_DOCS", 100))
    chunk_size: int = 2000
    chunk_overlap: int = 100
    llm_base_url: str = field(
        default_factory=lambda: _env("PRIVACY_DESK_LLM_BASE", "https://api.deepseek.com/v1")
    )
    llm_model: str = field(
        default_factory=lambda: _env("PRIVACY_DESK_LLM_MODEL", "deepseek-flash")
    )
    # 环境变量 Key 是数据库保存值之外的备选来源（DB 优先），仅在首次启动时用于推导默认模式
    llm_api_key: str | None = field(default_factory=lambda: os.environ.get("PRIVACY_DESK_LLM_KEY"))
    ollama_url: str = field(
        default_factory=lambda: _env("PRIVACY_DESK_OLLAMA", "http://127.0.0.1:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: _env("PRIVACY_DESK_OLLAMA_MODEL", "qwen2.5:7b")
    )
    # 本地模型冷启动与首 token 可能远超 5 秒，默认给足 120 秒，可用环境变量覆盖
    ollama_timeout: float = field(
        default_factory=lambda: _env_float("PRIVACY_DESK_OLLAMA_TIMEOUT", 120.0)
    )
    # 以下三个加固开关默认关闭，正式分发时由启动脚本/构建流程显式打开
    enforce_integrity: bool = field(
        default_factory=lambda: os.environ.get("PRIVACY_DESK_ENFORCE_INTEGRITY") == "1"
    )
    require_encrypted_resources: bool = field(
        default_factory=lambda: os.environ.get("PRIVACY_DESK_REQUIRE_ENCRYPTED_RESOURCES") == "1"
    )
    require_token: bool = field(
        default_factory=lambda: os.environ.get("PRIVACY_DESK_REQUIRE_TOKEN") == "1"
    )
    ui_dir: Path | None = None

    @property
    def db_path(self) -> Path:
        # SQLite 文件固定落在数据目录下，随 data_dir 一起迁移或清理
        return self.data_dir / "privacy.db"
