from pathlib import Path

from app.core.detect.fusion import fuse
from app.core.detect.rule_engine import Span
from app.core.detect.types import load_builtin_types

RESOURCES = Path(__file__).resolve().parents[1] / "resources"
TYPES = load_builtin_types(RESOURCES)


def test_rule_wins_for_phone_when_overlapping():
    rule = Span(0, 11, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    llm = Span(0, 11, "PHONE_CN", "13800138000", 0.80, "llm", "high")
    result = fuse([rule], [llm], TYPES)
    assert len(result) == 1
    assert result[0].source == "rule"


def test_non_overlapping_spans_both_kept():
    rule = Span(4, 15, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    llm = Span(0, 2, "NAME_CN", "张三", 0.85, "llm", "medium")
    result = fuse([rule], [llm], TYPES)
    assert [item.type_code for item in result] == ["NAME_CN", "PHONE_CN"]


def test_higher_level_secret_beats_medium_name():
    secret = Span(0, 4, "SECRET_INFO", "内部资料", 0.8, "rule", "high")
    name = Span(0, 4, "NAME_CN", "内部资料", 0.95, "llm", "medium")
    result = fuse([secret], [name], TYPES)
    assert result[0].type_code == "SECRET_INFO"


def test_llm_wins_for_address_against_rule():
    rule = Span(0, 10, "ADDRESS_CN", "北京市某区某路1号", 0.95, "rule", "medium")
    llm = Span(0, 10, "ADDRESS_CN", "北京市某区某路1号", 0.80, "llm", "medium")
    result = fuse([rule], [llm], TYPES)
    assert result[0].source == "llm"


def test_rule_span_inherits_llm_suggestion():
    rule = Span(0, 11, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    llm = Span(0, 11, "PHONE_CN", "13800138000", 0.80, "llm", "high", suggest="encrypt")
    result = fuse([rule], [llm], TYPES)
    assert result[0].source == "rule"
    assert result[0].suggest == "encrypt"


def test_longer_span_wins_inside_same_type():
    short = Span(0, 2, "NAME_CN", "张三", 0.8, "llm", "medium")
    long = Span(0, 4, "NAME_CN", "张三丰丰", 0.8, "llm", "medium")
    result = fuse([], [short, long], TYPES)
    assert result[0].text == "张三丰丰"
