from pathlib import Path

from app.core.ingest.model import Block, build_model
from app.core.ingest.registry import export_document, load_document
from app.core.ingest.text_loader import decode_text


def test_build_model_offsets():
    model = build_model([Block("paragraph", "abc"), Block("paragraph", "defg")], "txt")
    assert model.text == "abc\ndefg"
    assert model.text[model.blocks[0].start:model.blocks[0].end] == "abc"
    assert model.text[model.blocks[1].start:model.blocks[1].end] == "defg"


def test_decode_gbk_fallback():
    assert decode_text("中文内容".encode("gbk")) == "中文内容"


def test_load_and_export_text(tmp_path):
    source = tmp_path / "a.txt"
    source.write_text("第一行\n电话13800138000", encoding="utf-8")
    model = load_document(source, "txt")
    assert "13800138000" in model.text
    masked = model.text.replace("13800138000", "138****8000")
    target = tmp_path / "out.txt"
    export_document(model, masked, target, "txt")
    assert "138****8000" in target.read_text(encoding="utf-8")
