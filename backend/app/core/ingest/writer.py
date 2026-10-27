"""导出写回：文本整篇覆盖，DOCX 原位替换段落，PDF 按文本重建。"""

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
    # 只保留 w:pPr（段落样式/缩进/编号），其余子节点（含超链接里的原文本）全部移除，
    # 否则旧内容会残留，脱敏结果不彻底。
    for child in list(element):
        if child.tag != qn("w:pPr"):
            element.remove(child)
    run = paragraph.add_run(text)
    if run_properties is not None:
        # 复制首个 run 的 rPr（字体/字号/颜色）到新 run，避免整段丢失原有字符格式
        run._element.insert(0, deepcopy(run_properties))


def map_offset(position: int, applied: list[dict]) -> int:
    """把原文偏移映射到脱敏后文本的偏移。"""
    # 前提：applied 按原文起点升序（脱敏引擎已按 start 排序后生成），否则遇到第一个
    # 更靠后的替换就会 break，后续长度差漏加。完全位于替换之后的偏移累加长度差；
    # 落在替换区间内部的偏移统一对齐到替换串起点，避免切出半个占位符。
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
    # 等长脱敏（如逐字符替换）时块边界不变，可不传 applied；
    # 变长时缺映射就无法从原文偏移定位块边界，直接报错而不是静默写错。
    if applied is None and len(masked_text) != len(model.text):
        raise ValueError("变长脱敏导出必须提供 applied 偏移映射")
    document = model.meta["docx"]
    replacements = applied or []
    for block in model.blocks:
        # 块端点都先换算到脱敏后坐标，再整体切片，保证每段拿到的是对应位置的新文本
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
    # PDF 没有可原地编辑的段落对象，这里放弃原版面，按行重建一份新 PDF；
    # reportlab 的 Paragraph 会解析迷你 HTML，故先转义 & < > 防止文本被当作标签。
    story = []
    for line in masked_text.split("\n"):
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # 空行用 &nbsp; 占位，否则 Paragraph 会丢弃该行，导致行距塌缩
        story.append(PdfParagraph(safe or "&nbsp;", _PDF_STYLE))
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4)
    document.build(story)
    Path(out_path).write_bytes(buffer.getvalue())
