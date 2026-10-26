from pathlib import Path

import pdfplumber
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.ingest.pdf_loader import load_pdf
from app.core.ingest.registry import export_document


def make_pdf(path: Path, text: str) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.drawString(72, 720, text)
    pdf.save()


def test_pdf_extract_and_rebuild(tmp_path):
    source = tmp_path / "a.pdf"
    make_pdf(source, "Phone 13800138000")
    model = load_pdf(source)
    assert "13800138000" in model.text

    masked = model.text.replace("13800138000", "138****8000")
    target = tmp_path / "out.pdf"
    export_document(model, masked, target, "pdf")
    assert target.read_bytes().startswith(b"%PDF")

    with pdfplumber.open(target) as pdf:
        assert "138****8000" in "\n".join(page.extract_text() or "" for page in pdf.pages)
