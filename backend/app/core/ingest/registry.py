"""按扩展名分派加载/导出实现；TEXT_EXTS 中的纯文本格式共用同一条读写路径。"""

from pathlib import Path

from app.core.ingest.docx_loader import load_docx
from app.core.ingest.model import DocumentModel
from app.core.ingest.pdf_loader import load_pdf
from app.core.ingest.text_loader import load_text
from app.core.ingest.writer import write_docx, write_pdf, write_text

TEXT_EXTS = {"txt", "md", "log", "py", "java", "js", "ts", "json", "csv", "eml"}


def load_document(path: Path, ext: str) -> DocumentModel:
    # 扩展名统一小写后再比对，避免 ".DOCX" 之类的写法落到不支持分支
    ext = ext.lower()
    if ext == "docx":
        return load_docx(Path(path))
    if ext == "pdf":
        return load_pdf(Path(path))
    if ext in TEXT_EXTS:
        return load_text(Path(path))
    raise ValueError(f"暂不支持的格式：{ext}")


def export_document(
    model: DocumentModel,
    masked_text: str,
    out_path: Path,
    ext: str,
    applied: list[dict] | None = None,
) -> None:
    ext = ext.lower()
    if ext == "docx":
        write_docx(model, masked_text, Path(out_path), applied)
        return
    if ext == "pdf":
        # PDF 没有可原地改写的段落对象，只能按脱敏后文本整篇重建
        write_pdf(masked_text, Path(out_path))
        return
    if ext in TEXT_EXTS:
        write_text(model, masked_text, Path(out_path))
        return
    raise ValueError(f"暂不支持的导出格式：{ext}")
