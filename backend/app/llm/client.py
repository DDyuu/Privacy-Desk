"""大模型客户端：在线 OpenAI 兼容接口、本机 Ollama，以及宽松的 JSON 数组解析。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

DEFAULT_PROMPT = (
    "你是隐私信息识别引擎。只在给定文本中找出属于候选类型的隐私信息。"
    '输出严格 JSON 数组，元素为 {"type":"类型代码","text":"原文片段","confidence":0到1的小数,"reason":"简短理由"}。'
    "text 只包含敏感值本身，不要带字段名、标签或冒号、等号、短横线等前缀。"
    "无法归入候选类型时用 SUSPECTED，只返回具体值。"
    "不要输出解释、代码块标记或多余文本；找不到时输出 []。"
)


class LLMError(RuntimeError):
    """大模型调用失败。"""


def load_prompt() -> str:
    """优先从加密资源包读取提示词；强制加密模式下解密失败必须抛出，不能静默退回内置明文。"""
    try:
        from app.core.security.resources import load_prompt as load_resource_prompt

        return load_resource_prompt(Path(__file__).resolve().parents[2] / "resources")
    except Exception:
        if os.environ.get("PRIVACY_DESK_REQUIRE_ENCRYPTED_RESOURCES") == "1":
            raise
        return DEFAULT_PROMPT


def parse_json_array(content: str) -> list[dict]:
    """容忍代码块标记和前后杂文本，尽量从模型输出中解析出对象数组；失败返回空列表。"""
    if not isinstance(content, str):
        return []
    text = content.strip()
    # 有些模型会包一层 ```json ... ```，先剥掉再解析
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
    # 最近一次调用模型返回的原始文本，由各实现写入，供识别报告留档
    last_raw = ""

    def available(self) -> bool:
        return False

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        raise NotImplementedError

    def cache_id(self) -> str:
        return self.name


class NullLLM(BaseLLM):
    """规则模式占位客户端：不可用且不产出结果，保证调用方代码路径一致。"""

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
        # 允许传入 base_url 以适配任何 OpenAI 兼容服务，统一补上 chat/completions 路径
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)

    def available(self) -> bool:
        return bool(self._api_key)

    def cache_id(self) -> str:
        return f"online:{self._model}"

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        self.last_raw = ""
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
        # 最多 3 次尝试，间隔 0.3/0.6/0.9 秒；只重试网络与响应类异常，
        # 内容格式非法（LLMError）重试也不会变好，直接上抛。
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
                # 先留档原始响应再解析，解析失败时报告里也能看到模型到底回了什么
                self.last_raw = content
                return parse_json_array(content)
            except LLMError:
                raise
            except Exception as exc:
                last_error = exc
                time.sleep(0.3 * (attempt + 1))
        raise LLMError(f"在线模型调用失败：{last_error}") from last_error


def probe_ollama(
    base_url: str,
    model: str = "",
    timeout: float = 2.0,
    client: httpx.Client | None = None,
) -> dict:
    """探测本机 Ollama 服务是否可连，并返回已拉取的模型列表。"""
    target = (base_url or "").strip().rstrip("/")
    if not target:
        return {
            "reachable": False,
            "models": [],
            "model_present": False,
            "message": "请先填写 Ollama 地址",
        }

    owns_client = client is None
    http_client = client or httpx.Client(timeout=timeout)
    try:
        response = http_client.get(f"{target}/api/tags")
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {
            "reachable": False,
            "models": [],
            "model_present": False,
            "message": f"无法连接 {target}：{exc}",
        }
    finally:
        # 只关闭自建连接，调用方传入的 client 由调用方负责生命周期
        if owns_client:
            http_client.close()

    raw_models = payload.get("models") if isinstance(payload, dict) else None
    models = [
        item["name"]
        for item in (raw_models or [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    wanted = (model or "").strip()
    # Ollama 返回的名字可能带 :tag 后缀，所以精确匹配之外也接受 "名字:" 前缀
    model_present = bool(wanted) and any(
        name == wanted or name.startswith(f"{wanted}:") for name in models
    )
    message = ""
    if wanted and not model_present:
        message = f"服务已连接，但未找到模型 {wanted}，请执行 ollama pull {wanted}"
    return {
        "reachable": True,
        "models": models,
        "model_present": model_present,
        "message": message,
    }


class OllamaLLM(BaseLLM):
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        # 本机模型冷启动和首次推理较慢，默认超时比在线接口更宽松
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)

    def available(self) -> bool:
        return True

    def cache_id(self) -> str:
        return f"ollama:{self._model}"

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        self.last_raw = ""
        hint_lines = "\n".join(
            f"- {item['code']}（{item['name']}）：{item.get('hint', '')}" for item in hints
        )
        payload = {
            "model": self._model,
            "stream": False,
            # 让 Ollama 以 JSON 模式作答，减少需要容错解析的杂文本
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
        # 与在线客户端一致：3 次尝试、线性退避，内容格式错误不再重试
        for attempt in range(3):
            try:
                response = self._client.post(self._url, json=payload)
                response.raise_for_status()
                content = response.json()["message"]["content"]
                if not isinstance(content, str):
                    raise LLMError("模型返回内容格式非法")
                self.last_raw = content
                return parse_json_array(content)
            except httpx.TimeoutException as exc:
                # 超时通常意味着模型在冷启动或本身过慢，重试只会成倍放大等待
                raise LLMError(f"本地模型调用超时：{exc}") from exc
            except LLMError:
                raise
            except Exception as exc:
                last_error = exc
                time.sleep(0.3 * (attempt + 1))
        raise LLMError(f"本地模型调用失败：{last_error}") from last_error
