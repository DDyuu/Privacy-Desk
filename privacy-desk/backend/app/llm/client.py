from __future__ import annotations

import json
import os
import time
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
    try:
        from app.core.security.resources import load_prompt as load_resource_prompt

        return load_resource_prompt(Path(__file__).resolve().parents[2] / "resources")
    except Exception:
        if os.environ.get("PRIVACY_DESK_REQUIRE_ENCRYPTED_RESOURCES") == "1":
            raise
        return DEFAULT_PROMPT


def parse_json_array(content: str) -> list[dict]:
    if not isinstance(content, str):
        return []
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
    if isinstance(data, dict):
        if "type" in data and "text" in data:
            return [data]
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

    def cache_id(self) -> str:
        return self.name


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

    def cache_id(self) -> str:
        return f"online:{self._model}"

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
        last_error = None
        for attempt in range(3):
            try:
                response = self._client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise LLMError("模型返回内容格式非法")
                return parse_json_array(content)
            except LLMError:
                raise
            except Exception as exc:
                last_error = exc
                time.sleep(0.3 * (attempt + 1))
        raise LLMError(f"在线模型调用失败：{last_error}") from last_error


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

    def cache_id(self) -> str:
        return f"ollama:{self._model}"

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
        last_error = None
        for attempt in range(3):
            try:
                response = self._client.post(self._url, json=payload)
                response.raise_for_status()
                content = response.json()["message"]["content"]
                if not isinstance(content, str):
                    raise LLMError("模型返回内容格式非法")
                return parse_json_array(content)
            except LLMError:
                raise
            except Exception as exc:
                last_error = exc
                time.sleep(0.3 * (attempt + 1))
        raise LLMError(f"本地模型调用失败：{last_error}") from last_error
