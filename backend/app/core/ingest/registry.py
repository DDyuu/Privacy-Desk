from pathlib import Path

from app.core.ingest.docx_loader import load_docx
from app.core.ingest.model import DocumentModel
from app.core.ingest.pdf_loader import load_pdf
from app.core.ingest.text_loader import load_text
from app.core.ingest.writer import write_docx, write_pdf, write_text

TEXT_EXTS = {"txt", "md", "log", "py", "java", "js", "ts", "json", "csv", "eml"}


def load_document(path: Path, ext: str) -> DocumentModel:
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
        write_pdf(masked_text, Path(out_path))
        return
    if ext in TEXT_EXTS:
        write_text(model, masked_text, Path(out_path))
        return
    raise ValueError(f"暂不支持的导出格式：{ext}")
