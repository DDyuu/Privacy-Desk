from __future__ import annotations

import hashlib
import json
import math
import re

from app.core.detect.chunking import chunk_text
from app.core.detect.pre_redact import pre_redact
from app.core.detect.rule_engine import Span, _find_all
from app.core.detect.types import TypeDefinition
from app.llm.client import BaseLLM

MIN_FRAGMENT_LEN = 2
MAX_HITS_PER_FRAGMENT = 20
MAX_SPANS = 500

_LABEL_SEPARATOR = re.compile(r"^[\u4e00-\u9fa5]{2,8}\s*[:：=＝\-—]\s*")
_LABEL_BEFORE_ASCII = re.compile(r"^[\u4e00-\u9fa5]{2,8}(?=[A-Za-z0-9])")
_CHINESE = re.compile(r"[\u4e00-\u9fa5]")


def _trim_field_label(fragment: str) -> str:
    """模型偶尔把字段名一起返回（如“密钥sk-...”），这里只保留字段值。"""
    trimmed = _LABEL_SEPARATOR.sub("", fragment, count=1)
    if trimmed != fragment and len(trimmed) >= MIN_FRAGMENT_LEN:
        return trimmed
    matched = _LABEL_BEFORE_ASCII.match(fragment)
    if matched:
        rest = fragment[matched.end() :]
        # 值部分不再包含中文时才认为是“标签+值”，避免把地址里的地名截掉
        if len(rest) >= MIN_FRAGMENT_LEN and not _CHINESE.search(rest):
            return rest
    return fragment


class LLMEngine:
    """把分块文本交给大模型，返回可直接定位的 span。"""

    def __init__(
        self,
        client: BaseLLM,
        types: list[TypeDefinition],
        chunk_size: int = 2000,
        chunk_overlap: int = 100,
    ) -> None:
        self._client = client
        self._types = types
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._cache: dict[str, list[dict]] = {}

    def _cache_key(self, chunk: str, hints: list[dict]) -> str:
        payload = chunk + "\x00" + json.dumps(hints, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def detect(self, text: str, high_spans: list[Span]) -> list[Span]:
        if not self._client.available():
            return []
        hints = [
            {
                "code": definition.code,
                "name": definition.name,
                "hint": next(
                    (d.hint for d in definition.detectors if d.kind == "llm" and d.hint), ""
                ),
            }
            for definition in self._types
            if definition.enabled and any(d.kind == "llm" for d in definition.detectors)
        ]
        allowed = {item["code"] for item in hints}
        levels = {definition.code: definition.level for definition in self._types}
        found: dict[tuple[int, int, str], Span] = {}
        for start, end in chunk_text(text, self._chunk_size, self._chunk_overlap):
            chunk = text[start:end]
            if not chunk.strip():
                continue
            local_high = [
                Span(
                    max(span.start, start) - start,
                    min(span.end, end) - start,
                    span.type_code,
                    span.text,
                    span.confidence,
                    span.source,
                    span.level,
                )
                for span in high_spans
                if span.start < end and span.end > start
            ]
            redacted = pre_redact(chunk, local_high)
            key = self._cache_key(redacted, hints)
            if key in self._cache:
                items = self._cache[key]
            else:
                items = self._client.extract(redacted, hints)
                if len(self._cache) < 128:
                    self._cache[key] = items
            for item in items:
                code = str(item.get("type") or "")
                fragment = _trim_field_label(str(item.get("text") or "").strip())
                if (
                    code not in allowed
                    or len(fragment) < MIN_FRAGMENT_LEN
                    or "█" in fragment
                    or len(fragment) > 200
                ):
                    continue
                try:
                    confidence = float(item.get("confidence", 0.7))
                except (TypeError, ValueError):
                    confidence = 0.7
                if not math.isfinite(confidence):
                    confidence = 0.7
                confidence = min(max(confidence, 0.0), 1.0)
                positions = list(_find_all(chunk, fragment))[:MAX_HITS_PER_FRAGMENT]
                for position in positions:
                    key_span = (start + position, start + position + len(fragment), code)
                    candidate = Span(
                        key_span[0],
                        key_span[1],
                        code,
                        fragment,
                        confidence,
                        "llm",
                        levels.get(code, "medium"),
                    )
                    if key_span not in found or candidate.confidence > found[key_span].confidence:
                        found[key_span] = candidate
                    if len(found) >= MAX_SPANS:
                        break
        return sorted(found.values(), key=lambda item: (item.start, item.end))
