"""从环境变量发现大模型 API Key：只返回掩码，明文仅在后端内部使用。"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping

BUILTIN_ENV_KEYS: tuple[dict[str, str], ...] = (
    {
        "name": "PRIVACY_DESK_LLM_KEY",
        "provider": "兼容服务",
        "base_url": "",
        "model": "",
    },
    {
        "name": "DEEPSEEK_API_KEY",
        "provider": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    {
        "name": "OPENAI_API_KEY",
        "provider": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
)

_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_CUSTOM_NAMES = 10


def normalize_names(names: Iterable[str]) -> list[str]:
    """清洗自定义变量名：去空白、校验标识符格式、去重并限制条数。"""
    result: list[str] = []
    for raw in names:
        name = (raw or "").strip()
        if not name or not _NAME_PATTERN.match(name) or name in result:
            continue
        result.append(name)
    return result[:MAX_CUSTOM_NAMES]


def mask_key(value: str) -> str:
    """掩码展示 Key：保留首尾各 4 位，过短的 Key 全部遮蔽。"""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}****{value[-4:]}"


def detect_env_keys(
    custom_names: Iterable[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """按内置清单 + 自定义清单顺序返回命中的环境变量（含明文 value，仅供内部使用）。"""
    env = os.environ if environ is None else environ
    specs = list(BUILTIN_ENV_KEYS) + [
        {"name": name, "provider": "自定义变量", "base_url": "", "model": ""}
        for name in normalize_names(custom_names or [])
    ]
    seen: set[str] = set()
    detected: list[dict[str, str]] = []
    for spec in specs:
        name = spec["name"]
        if name in seen:
            continue
        seen.add(name)
        value = (env.get(name) or "").strip()
        if not value:
            continue
        detected.append({**spec, "masked": mask_key(value), "value": value})
    return detected
