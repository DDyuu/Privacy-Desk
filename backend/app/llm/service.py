from __future__ import annotations

from app.config import Settings
from app.core.detect.llm_engine import LLMEngine
from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeDefinition
from app.core.store.repository import Repository
from app.llm.client import LLMError, NullLLM, OllamaLLM, OpenAICompatLLM
from app.llm.env_keys import detect_env_keys, normalize_names


class LLMService:
    def __init__(self, repo: Repository, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings

    def _stored(self) -> dict:
        try:
            return self._repo.get_setting("llm") or {}
        except Exception:
            return {}

    def env_key_names(self) -> list[str]:
        return normalize_names(self._stored().get("env_key_names") or [])

    def stored_api_key(self) -> str:
        """已保存（加密落库）的 Key；不包含环境变量回退结果。"""
        return str(self._stored().get("api_key") or "")

    def _resolve_key(self) -> tuple[str, str]:
        """返回 (明文 Key, 来源)，来源为 stored / env:变量名 / none。"""
        saved = self.stored_api_key()
        if saved:
            return saved, "stored"
        for item in detect_env_keys(self.env_key_names()):
            return item["value"], f"env:{item['name']}"
        return "", "none"

    def key_source(self) -> str:
        return self._resolve_key()[1]

    def preview_key_source(self, names: list[str]) -> str:
        """按给定变量名预览 Key 来源：已保存的 Key 优先，否则取首个命中的环境变量。"""
        if self.stored_api_key():
            return "stored"
        detected = detect_env_keys(normalize_names(names))
        return f"env:{detected[0]['name']}" if detected else "none"

    def env_key_candidates(
        self, names: list[str] | None = None, source: str | None = None
    ) -> list[dict]:
        """对外暴露的环境变量候选，只含掩码，不含明文 Key。"""
        source = self.key_source() if source is None else source
        custom = self.env_key_names() if names is None else normalize_names(names)
        return [
            {
                "name": item["name"],
                "provider": item["provider"],
                "masked": item["masked"],
                "base_url": item["base_url"],
                "model": item["model"],
                "active": source == f"env:{item['name']}",
            }
            for item in detect_env_keys(custom)
        ]

    def default_config(self) -> dict:
        return {
            "mode": "online" if self._settings.llm_api_key else "rules",
            "base_url": self._settings.llm_base_url,
            "model": self._settings.llm_model,
            "api_key": "",
            "env_key_names": [],
            "ollama_url": self._settings.ollama_url,
            "ollama_model": self._settings.ollama_model,
        }

    def config(self) -> dict:
        stored = self._stored()
        merged = {**self.default_config(), **stored}
        key, _ = self._resolve_key()
        if not merged.get("api_key") and key:
            merged["api_key"] = key
            # 首次运行尚未保存过配置时，检测到 Key 即启用在线模式
            if "mode" not in stored:
                merged["mode"] = "online"
        merged["env_key_names"] = self.env_key_names()
        return merged

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
            return OpenAICompatLLM(config["base_url"], config["api_key"], config["model"])
        if config.get("mode") == "ollama":
            return OllamaLLM(config.get("ollama_url", ""), config.get("ollama_model", ""))
        return NullLLM()

    def _engine(self, client, types: list[TypeDefinition]) -> LLMEngine:
        return LLMEngine(
            client,
            types,
            chunk_size=self._settings.chunk_size,
            chunk_overlap=self._settings.chunk_overlap,
        )

    def detect(
        self, text: str, high_spans: list[Span], types: list[TypeDefinition]
    ) -> tuple[list[Span], str]:
        config = self.config()
        attempts: list[tuple[str, object]] = []
        if config.get("mode") == "online" and config.get("api_key"):
            attempts.append(
                (
                    "online",
                    OpenAICompatLLM(
                        config["base_url"], config["api_key"], config["model"]
                    ),
                )
            )
        if config.get("mode") == "ollama" or attempts:
            attempts.append(
                (
                    "ollama",
                    OllamaLLM(
                        config.get("ollama_url", ""),
                        config.get("ollama_model", ""),
                        timeout=5.0,
                    ),
                )
            )
        if not attempts:
            return [], "rules"
        for name, client in attempts:
            try:
                return self._engine(client, types).detect(text, high_spans), name
            except LLMError:
                continue
        return [], "rules"
