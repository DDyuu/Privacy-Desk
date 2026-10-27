"""PDF 加载：逐页抽取文本并按行切块；不保留版面结构，仅服务于识别与重建导出。"""

from pathlib import Path

import pdfplumber

from app.core.ingest.model import Block, DocumentModel, build_model


def load_pdf(path: Path) -> DocumentModel:
    blocks: list[Block] = []
    page_texts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            # 扫描件或整页无文字时 extract_text 返回 None，统一当空页处理
            text = page.extract_text() or ""
            page_texts.append(text)
            for line in text.split("\n"):
                blocks.append(Block(kind="paragraph", text=line))
    model = build_model(blocks, "pdf")
    # 保留分页原文，供报告或后续按页定位使用
    model.meta["pages"] = page_texts
    return model
