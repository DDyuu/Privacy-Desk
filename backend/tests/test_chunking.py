import pytest

from app.core.detect.chunking import chunk_text
from app.core.detect.pre_redact import pre_redact
from app.core.detect.rule_engine import Span


def test_short_text_single_chunk():
    assert chunk_text("hello", size=100, overlap=10) == [(0, 5)]


def test_chunks_cover_full_text():
    text = "word " * 500
    chunks = chunk_text(text, size=200, overlap=50)
    assert chunks[0][0] == 0
    assert chunks[-1][1] == len(text)
    for (_, end), (next_start, _) in zip(chunks, chunks[1:]):
        assert next_start <= end


def test_chunks_prefer_whitespace_boundary():
    text = "abcdefghij " * 50
    for start, end in chunk_text(text, size=100, overlap=10)[:-1]:
        assert text[end - 1] == " "


def test_chunk_text_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_text("abc", size=10, overlap=10)


def test_pre_redact_keeps_length_and_masks_span():
    text = "张三电话13800138000"
    span = Span(4, 15, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    redacted = pre_redact(text, [span])
    assert len(redacted) == len(text)
    assert "13800138000" not in redacted
    assert redacted[:4] == "张三电话"
    assert redacted[4:15] == "█" * 11
