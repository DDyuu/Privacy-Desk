"""大模型客户端：在线 OpenAI 兼容接口、本机 Ollama，以及宽松的 JSON 数组解析。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

DEFAULT_PROMPT = (
    "你是隐私信息识别引擎，负责在中文文本中定位隐私信息。"
    "只输出 JSON 数组，不要输出解释、代码块标记或任何前后缀文字。"
    '数组元素格式：{"type":"类型代码","text":"原文片段","confidence":0到1的小数}。'
    "text 必须逐字复制原文片段，不要改写、拼接或包含上下文。"
    "只识别候选类型中列出的类型，type 必须使用给定的类型代码。"
    "一段文本可能包含多条隐私信息，必须全部列出；没有发现时输出 []。"
    "无法归入具体类型的敏感值（如 API 密钥、出生日期、账号）用 SUSPECTED，只返回具体值本身。"
    "text 只包含敏感值本身，不要带字段名、标签或冒号、等号、短横线等前缀。"
    "文本中的 █ 是已遮蔽的占位符，直接跳过，不要输出、不要解释、不要推测原文。"
)

# 单块生成的 token 上限：1000 字分块正常只需数百 token，超出多为重复输出，
# 封顶后即使被截断也只丢这一块的大模型结果，不会拖到超时再整体失败
MAX_OUTPUT_TOKENS = 1024
# 在线模型输出上限：推理型模型会先消耗大量 reasoning_content，
# 留 8192 保证思考结束后仍有额度输出最终 JSON
MAX_ONLINE_TOKENS = 8192
# 重复惩罚：默认 1.1 仍会在“因此不输出。”这类短句上无限复读，1.3 可稳定终止
REPEAT_PENALTY = 1.3
# 结构化输出：用 JSON Schema 把解码约束成对象数组，避免模型只返回单个对象或夹杂解释
OLLAMA_OUTPUT_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "text": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["type", "text", "confidence"],
    },
}


# 在线模型额外要求逐条给出推荐脱敏动作，本地小模型不做这个要求
ONLINE_SUGGEST_SUFFIX = (
    "\n候选类型之外但明显敏感的信息仍用 SUSPECTED，不要遗漏。"
    "\n为每个结果增加 suggest 字段，取值只能是 mask、replace、fuzz、encrypt、ignore 之一："
    "密钥、证件、银行卡等高敏信息只能建议 mask 或 encrypt，禁止建议 ignore；"
    "其余类型在安全前提下优先 replace 或 fuzz，尽量保留可读性；"
    "低风险且保留不影响安全的信息可以建议 ignore，表示不脱敏。"
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
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        # 允许传入 base_url 以适配任何 OpenAI 兼容服务，统一补上 chat/completions 路径
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        # 流式读取下 read timeout 只约束“两次数据之间的间隔”，
        # 60 秒足以覆盖首 token 较慢的推理型模型，也不再是整段生成的硬上限
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0))

    def available(self) -> bool:
        return bool(self._api_key)

    def cache_id(self) -> str:
        return f"online:{self._model}"

    def _payload(self, text: str, hints: list[dict]) -> dict:
        hint_lines = "\n".join(
            f"- {item['code']}（{item['name']}）：{item.get('hint', '')}" for item in hints
        )
        return {
            "model": self._model,
            "temperature": 0,
            # 流式返回：首 token 就能到达，避免“整段生成完才返回”撞上读超时
            "stream": True,
            # 不封顶时模型可能输出解释或复读，长文分块下会把等待时间无限拉长
            "max_tokens": MAX_ONLINE_TOKENS,
            "messages": [
                {"role": "system", "content": load_prompt() + ONLINE_SUGGEST_SUFFIX},
                {
                    "role": "user",
                    "content": f"候选类型：\n{hint_lines}\n\n待识别文本：\n{text}",
                },
            ],
        }

    def _finish(self, content: str, raw_text: str = "") -> list[dict]:
        if not isinstance(content, str):
            raise LLMError("模型返回内容格式非法")
        if content.strip():
            # 先留档原始响应再解析，解析失败时报告里也能看到模型到底回了什么
            self.last_raw = content
            return parse_json_array(content)
        # 少数服务会忽略 stream，把完整 JSON 当成普通响应塞进 event-stream
        try:
            message = json.loads(raw_text)["choices"][0]["message"]["content"]
            if isinstance(message, str) and message.strip():
                self.last_raw = message
                return parse_json_array(message)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass
        # 空内容通常是模型只输出了推理过程，或服务端直接断流；
        # 把原始流截断留档，报告里才能看出到底收到了什么
        self.last_raw = raw_text[:2000]
        if "reasoning_content" in raw_text:
            raise LLMError("在线模型只返回推理内容，疑似推理模型；请改用非推理模型或调大输出上限")
        raise LLMError("在线模型返回空内容")

    def _extract_once(self, payload: dict) -> list[dict]:
        parts: list[str] = []
        raw_events: list[str] = []
        with self._client.stream(
            "POST",
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text/event-stream" not in content_type:
                # 少数兼容服务会忽略 stream=True，直接回完整 JSON，这里兼容处理
                body = response.read().decode("utf-8", errors="replace")
                try:
                    content = json.loads(body)["choices"][0]["message"]["content"]
                except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                    self.last_raw = body[:2000]
                    raise LLMError("模型返回内容格式非法") from exc
                return self._finish(content, body)
            for line in response.iter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    # 非标准实现可能把完整 JSON 当成一行塞进 event-stream
                    raw_events.append(line)
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                raw_events.append(data)
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                piece = (choice.get("delta") or {}).get("content")
                if not isinstance(piece, str):
                    # 部分实现流式结束时只给一条 message，而不是 delta
                    piece = (choice.get("message") or {}).get("content")
                if isinstance(piece, str):
                    parts.append(piece)
        return self._finish("".join(parts), "\n".join(raw_events))

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        self.last_raw = ""
        payload = self._payload(text, hints)
        last_error = None
        # 只重试连接类错误；超时与 HTTP 状态错误重试不会变好，反而成倍放大等待
        for attempt in range(3):
            try:
                return self._extract_once(payload)
            except httpx.TimeoutException as exc:
                raise LLMError(f"在线模型调用超时：{exc}") from exc
            except httpx.TransportError as exc:
                last_error = exc
                time.sleep(0.3 * (attempt + 1))
            except LLMError:
                raise
            except httpx.HTTPStatusError as exc:
                raise LLMError(f"在线模型调用失败：{exc}") from exc
            except Exception as exc:
                raise LLMError(f"在线模型调用失败：{exc}") from exc
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
            # 用 schema 强制输出对象数组，7B 模型无法再退化成单个对象或夹带解释
            "format": OLLAMA_OUTPUT_SCHEMA,
            # 本地模型偶尔会陷入重复输出，必须封顶生成长度，否则会一直写到超时
            "options": {
                "temperature": 0,
                "num_predict": MAX_OUTPUT_TOKENS,
                # 预遮蔽后的 █ 占位符容易诱发复读，加大重复惩罚可让模型几秒内收尾
                "repeat_penalty": REPEAT_PENALTY,
            },
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
