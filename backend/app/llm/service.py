"""LLM 服务层：合并默认配置与落库配置，解析 Key 来源，并实现 online→ollama→rules 降级链。"""

from __future__ import annotations

import time

from app.config import Settings
from app.core.detect.llm_engine import LLMEngine
from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeDefinition
from app.core.store.repository import Repository
from app.llm.client import LLMError, NullLLM, OllamaLLM, OpenAICompatLLM, probe_ollama
from app.llm.env_keys import detect_env_keys, normalize_names


class LLMService:
    def __init__(self, repo: Repository, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings
        # Ollama 可达性缓存：url -> (检测时间, 是否可连)，避免每次识别都等连接超时
        self._ollama_probe: dict[str, tuple[float, bool]] = {}

    def _stored(self) -> dict:
        # 配置读取失败按“未配置”处理，避免数据库异常直接拖垮会话状态等基础接口
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
        # 已保存的 Key 优先；否则按内置清单在前、自定义清单在后的顺序取首个命中的变量
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
        """默认配置与落库配置合并；落库值覆盖默认值。"""
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
        """对外的实际生效模式：online 必须同时具备 mode 与 Key，否则按配置降级。"""
        config = self.config()
        if config.get("mode") == "online" and config.get("api_key"):
            return "online"
        # 选了在线却没有可用 Key 时不会报错，而是退到规则模式
        if config.get("mode") == "ollama":
            return "ollama"
        return "rules"

    def build_client(self):
        config = self.config()
        if config.get("mode") == "online" and config.get("api_key"):
            return OpenAICompatLLM(config["base_url"], config["api_key"], config["model"])
        if config.get("mode") == "ollama":
            return OllamaLLM(
                config.get("ollama_url", ""),
                config.get("ollama_model", ""),
                timeout=self._settings.ollama_timeout,
            )
        return NullLLM()

    def _engine(self, client, types: list[TypeDefinition]) -> LLMEngine:
        return LLMEngine(
            client,
            types,
            chunk_size=self._settings.chunk_size,
            chunk_overlap=self._settings.chunk_overlap,
        )

    def _ollama_reachable(self, url: str) -> bool:
        """探测 Ollama 是否可连，结果缓存 30 秒；服务没启动时直接跳过兜底。"""
        url = (url or "").strip()
        if not url:
            return False
        now = time.monotonic()
        cached = self._ollama_probe.get(url)
        if cached is not None and now - cached[0] < 30:
            return cached[1]
        reachable = bool(probe_ollama(url, timeout=2.0).get("reachable"))
        self._ollama_probe[url] = (now, reachable)
        return reachable

    def detect(
        self, text: str, high_spans: list[Span], types: list[TypeDefinition]
    ) -> tuple[list[Span], str, list[dict]]:
        """返回 (片段, 实际模式, 调用留档)；沿 online → ollama → rules 逐级降级。"""
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
        # 在线模式也把 ollama 作为兜底加入；纯 ollama 模式则只有它自己。
        # 先探测再尝试：服务没启动时直接跳过，避免连接重试白等数秒。
        ollama_url = config.get("ollama_url", "")
        if (config.get("mode") == "ollama" or attempts) and self._ollama_reachable(ollama_url):
            attempts.append(
                (
                    "ollama",
                    # 冷启动/首次推理很慢，兜底也沿用同一超时，避免刚加载就被判失败
                    OllamaLLM(
                        config.get("ollama_url", ""),
                        config.get("ollama_model", ""),
                        timeout=self._settings.ollama_timeout,
                    ),
                )
            )
        if not attempts:
            return [], "rules", []
        trace: list[dict] = []
        for name, client in attempts:
            engine = self._engine(client, types)
            try:
                spans = engine.detect(text, high_spans)
                # 每一块的成功调用都带上来源客户端名，便于报告区分在线与本地
                return spans, name, [{**call, "provider": name} for call in engine.trace]
            except LLMError:
                # 失败尝试的调用记录也保留，报告里能看到降级原因
                trace.extend({**call, "provider": name} for call in engine.trace)
                continue
        return [], "rules", trace
