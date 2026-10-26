import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _default_resources() -> Path:
    """源码运行时用 backend/resources，PyInstaller 冻结后优先用 _MEIPASS/resources。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return Path(os.environ.get("PRIVACY_DESK_RESOURCES", str(base / "resources")))


@dataclass(frozen=True)
class Settings:
    """运行期配置；测试可传入临时目录。"""

    data_dir: Path = field(
        default_factory=lambda: Path(_env("PRIVACY_DESK_DATA", str(Path.home() / ".privacy-desk")))
    )
    resources_dir: Path = field(default_factory=_default_resources)
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
        return self.data_dir / "privacy.db"
