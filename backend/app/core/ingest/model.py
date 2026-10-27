"""文档块模型：以换行拼接块文本，并为每块记录其在全文中的偏移区间。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Block:
    kind: str
    text: str
    # start/end 为左闭右开区间，指向 DocumentModel.text；build_model 之前两者均为 0
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
        # 块间固定插入一个 "\n"，所以下一块起点是上一块 end + 1（而不是 +0）
        block.start = cursor
        block.end = cursor + len(block.text)
        parts.append(block.text)
        cursor = block.end + 1
    return DocumentModel(text="\n".join(parts), blocks=blocks, fmt=fmt, meta=meta or {})
