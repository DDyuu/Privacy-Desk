"""DOCX 加载：把正文与页眉页脚里的非空段落收集为块，并保留段落对象用于写回。"""

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from app.core.ingest.model import Block, DocumentModel, build_model


def _in_textbox(element) -> bool:
    # 文本框内段落会被 w:p 遍历命中，但写回时定位不到对应文本流，导出会错位，故跳过
    parent = element.getparent()
    while parent is not None:
        if parent.tag == qn("w:txbxContent"):
            return True
        parent = parent.getparent()
    return False


def _collect(root, document: Document, blocks: list[Block], seen: set[int]) -> None:
    for element in root.iter(qn("w:p")):
        # 正文与页眉页脚可能重复命中同一段落，按对象身份去重，避免同一段重复成块
        if id(element) in seen or _in_textbox(element):
            continue
        seen.add(id(element))
        paragraph = Paragraph(element, document)
        # 空段落不产生块，否则会在全文里留下无意义的空行
        if not paragraph.text.strip():
            continue
        blocks.append(Block(kind="paragraph", text=paragraph.text, ref=paragraph))


def load_docx(path: Path) -> DocumentModel:
    document = Document(str(path))
    blocks: list[Block] = []
    seen: set[int] = set()
    _collect(document.element.body, document, blocks, seen)
    for section in document.sections:
        _collect(section.header._element, document, blocks, seen)
        _collect(section.footer._element, document, blocks, seen)
    model = build_model(blocks, "docx")
    # 保留原始 Document 对象，导出时直接在原文档上改段落再另存，而不是重新排版
    model.meta["docx"] = document
    return model
