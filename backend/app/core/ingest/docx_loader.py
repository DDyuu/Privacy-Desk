from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from app.core.ingest.model import Block, DocumentModel, build_model


def _in_textbox(element) -> bool:
    parent = element.getparent()
    while parent is not None:
        if parent.tag == qn("w:txbxContent"):
            return True
        parent = parent.getparent()
    return False


def _collect(root, document: Document, blocks: list[Block], seen: set[int]) -> None:
    for element in root.iter(qn("w:p")):
        if id(element) in seen or _in_textbox(element):
            continue
        seen.add(id(element))
        paragraph = Paragraph(element, document)
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
    model.meta["docx"] = document
    return model
