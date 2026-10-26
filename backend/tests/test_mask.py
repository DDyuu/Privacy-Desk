from pathlib import Path

import pytest

from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeRegistry, load_builtin_types
from app.core.mask.engine import MaskEngine
from app.core.mask.operators import encrypt_value, fuzz_value, mask_value, replace_value
from app.core.security import crypto

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def registry():
    return TypeRegistry(load_builtin_types(RESOURCES))


def test_mask_value_keeps_edges():
    assert mask_value("13800138000", 0, 4) == "*******8000"
    assert mask_value("abc", 0, 0) == "***"


def test_replace_value():
    assert replace_value("张三", "[姓名_1]") == "[姓名_1]"


def test_fuzz_address_and_name():
    assert fuzz_value("北京市朝阳区建国路88号", "ADDRESS_CN") == "北京市某处"
    assert fuzz_value("张三", "NAME_CN") == "张*"


def test_encrypt_value_roundtrip():
    key = b"k" * 32
    aad = b"doc:SECRET_INFO:0"
    token = encrypt_value("机密内容", key, aad)
    assert token.startswith("ENC:")
    plain = crypto.decrypt(key, crypto.b64url_decode(token[4:]), aad)
    assert plain.decode("utf-8") == "机密内容"


def test_engine_uses_consistent_placeholder_for_same_name():
    spans = [
        Span(0, 2, "NAME_CN", "张三", 0.9, "llm", "medium"),
        Span(4, 6, "NAME_CN", "张三", 0.9, "llm", "medium"),
    ]
    engine = MaskEngine(b"k" * 32, registry(), {"NAME_CN": {"action": "replace"}})
    result = engine.apply("张三说，张三走了", spans)
    assert result.masked_text == "[姓名_1]说，[姓名_1]走了"
    assert result.mapping_size == 1


def test_engine_applies_default_mask_to_phone():
    # “电话：”占 3 个字符，手机号从下标 3 开始到 14 结束
    span = Span(3, 14, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    engine = MaskEngine(b"k" * 32, registry())
    result = engine.apply("电话：13800138000", [span])
    assert result.masked_text == "电话：*******8000"
    assert result.applied[0]["action"] == "mask"


def test_engine_rejects_unknown_action():
    with pytest.raises(ValueError, match="未知脱敏方式"):
        MaskEngine(b"k" * 32, registry(), {"PHONE_CN": {"action": "maskk"}})


def test_engine_merges_default_options_when_action_only():
    span = Span(3, 14, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    engine = MaskEngine(b"k" * 32, registry(), {"PHONE_CN": {"action": "mask"}})
    result = engine.apply("电话：13800138000", [span])
    assert result.masked_text == "电话：*******8000"


def test_engine_rejects_span_text_mismatch():
    span = Span(0, 5, "PHONE_CN", "99999", 0.9, "rule", "high")
    engine = MaskEngine(b"k" * 32, registry())
    with pytest.raises(ValueError, match="不一致"):
        engine.apply("13800138000", [span])


def test_engine_rejects_overlapping_spans():
    spans = [
        Span(0, 5, "PHONE_CN", "13800", 0.9, "rule", "high"),
        Span(3, 11, "NAME_CN", "某某某", 0.9, "llm", "medium"),
    ]
    engine = MaskEngine(b"k" * 32, registry())
    try:
        engine.apply("13800138000", spans)
    except ValueError as exc:
        assert "重叠" in str(exc)
    else:
        raise AssertionError("重叠 span 应报错")
