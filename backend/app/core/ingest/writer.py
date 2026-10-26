from copy import deepcopy
from io import BytesIO
from pathlib import Path

from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph as PdfParagraph, SimpleDocTemplate

from app.core.ingest.model import DocumentModel

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
_PDF_STYLE = ParagraphStyle("cn", fontName="STSong-Light", fontSize=11, leading=18)


def write_text(model: DocumentModel, masked_text: str, out_path: Path) -> None:
    Path(out_path).write_text(masked_text, encoding="utf-8")


def _set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    """清空段落内容（含超链接）后写入新文本，保留段落样式与首个 run 格式。"""
    element = paragraph._p
    run_properties = None
    if paragraph.runs:
        run_properties = paragraph.runs[0]._element.rPr
    for child in list(element):
        if child.tag != qn("w:pPr"):
            element.remove(child)
    run = paragraph.add_run(text)
    if run_properties is not None:
        run._element.insert(0, deepcopy(run_properties))


def map_offset(position: int, applied: list[dict]) -> int:
    """把原文偏移映射到脱敏后文本的偏移。"""
    shift = 0
    for item in applied:
        start = int(item["start"])
        end = int(item["end"])
        replacement = str(item["replacement"])
        if position >= end:
            shift += len(replacement) - (end - start)
        elif position > start:
            return start + shift
        else:
            break
    return position + shift


def write_docx(
    model: DocumentModel,
    masked_text: str,
    out_path: Path,
    applied: list[dict] | None = None,
) -> None:
    if applied is None and len(masked_text) != len(model.text):
        raise ValueError("变长脱敏导出必须提供 applied 偏移映射")
    document = model.meta["docx"]
    replacements = applied or []
    for block in model.blocks:
        start = map_offset(block.start, replacements)
        end = map_offset(block.end, replacements)
        new_text = masked_text[start:end]
        if block.kind == "table_cell":
            _, paragraph = block.ref
            _set_paragraph_text(paragraph, new_text)
        else:
            _set_paragraph_text(block.ref, new_text)
    document.save(str(out_path))


def write_pdf(masked_text: str, out_path: Path) -> None:
    story = []
    for line in masked_text.split("\n"):
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(PdfParagraph(safe or "&nbsp;", _PDF_STYLE))
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4)
    document.build(story)
    Path(out_path).write_bytes(buffer.getvalue())
