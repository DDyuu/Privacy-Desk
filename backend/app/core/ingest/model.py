from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Block:
    kind: str
    text: str
    start: int = 0
    end: int = 0
    ref: Any = None


@dataclass
class DocumentModel:
    text: str
    blocks: list[Block]
    fmt: str
    meta: dict = field(default_factory=dict)


def build_model(blocks: list[Block], fmt: str, meta: dict | None = None) -> DocumentModel:
    """用换行连接块文本，并记录每块在全文中的偏移。"""
    parts: list[str] = []
    cursor = 0
    for block in blocks:
        block.start = cursor
        block.end = cursor + len(block.text)
        parts.append(block.text)
        cursor = block.end + 1
    return DocumentModel(text="\n".join(parts), blocks=blocks, fmt=fmt, meta=meta or {})
