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
