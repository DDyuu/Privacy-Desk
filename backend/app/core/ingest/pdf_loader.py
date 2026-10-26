from pathlib import Path

import pdfplumber

from app.core.ingest.model import Block, DocumentModel, build_model


def load_pdf(path: Path) -> DocumentModel:
    blocks: list[Block] = []
    page_texts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            page_texts.append(text)
            for line in text.split("\n"):
                blocks.append(Block(kind="paragraph", text=line))
    model = build_model(blocks, "pdf")
    model.meta["pages"] = page_texts
    return model
