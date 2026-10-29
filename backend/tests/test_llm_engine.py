import pytest

from pathlib import Path

from app.core.detect.llm_engine import LLMEngine
from app.core.detect.rule_engine import Span
from app.core.detect.types import load_builtin_types
from app.llm.client import BaseLLM

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


class RecordingLLM(BaseLLM):
    name = "online"

    def __init__(self):
        self.inputs: list[str] = []

    def available(self) -> bool:
        return True

    def extract(self, text: str, hints: list[dict]) -> list[dict]:
        self.inputs.append(text)
        return [{"type": "NAME_CN", "text": "张三", "confidence": 0.9, "reason": "人名"}]


def test_llm_engine_pre_redacts_phone_before_sending():
    text = "张三电话13800138000"
    high_span = Span(4, 15, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    client = RecordingLLM()
    engine = LLMEngine(client, load_builtin_types(RESOURCES), chunk_size=2000)
    spans = engine.detect(text, [high_span])
    assert "13800138000" not in client.inputs[0]
    assert "█" in client.inputs[0]
    name = next(item for item in spans if item.type_code == "NAME_CN")
    assert text[name.start:name.end] == "张三"
    assert name.source == "llm"


def test_llm_engine_pre_redacts_spans_crossing_chunk_boundary():
    text = "a" * 1995 + "13800138000" + "b" * 100
    high_span = Span(1995, 2006, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    client = RecordingLLM()
    engine = LLMEngine(client, load_builtin_types(RESOURCES), chunk_size=2000, chunk_overlap=100)
    engine.detect(text, [high_span])
    joined = "".join(client.inputs)
    assert "13800138000" not in joined
    assert "13800" not in joined
    assert "138000" not in joined
    assert "█" in joined


def test_llm_engine_returns_empty_when_unavailable():
    engine = LLMEngine(BaseLLM(), load_builtin_types(RESOURCES))
    assert engine.detect("张三", []) == []
    assert engine.trace == []


def test_llm_engine_traces_raw_response_and_model():
    class RawLLM(BaseLLM):
        def available(self):
            return True

        def cache_id(self):
            return "fake:raw"

        def extract(self, text, hints):
            self.last_raw = '[{"type":"NAME_CN","text":"张三","confidence":0.9}]'
            return [{"type": "NAME_CN", "text": "张三", "confidence": 0.9}]

    engine = LLMEngine(RawLLM(), load_builtin_types(RESOURCES))
    engine.detect("张三", [])
    call = engine.trace[0]
    assert call["raw"].startswith("[")
    assert call["model"] == "fake:raw"
    assert call["cached"] is False
    assert call["items"] == 1


def test_llm_engine_traces_failed_call():
    class FailingLLM(BaseLLM):
        def available(self):
            return True

        def extract(self, text, hints):
            raise RuntimeError("boom")

    engine = LLMEngine(FailingLLM(), load_builtin_types(RESOURCES))
    with pytest.raises(RuntimeError):
        engine.detect("张三", [])
    assert "boom" in engine.trace[0]["error"]


def test_llm_engine_trims_field_labels_from_fragments():
    class LabeledLLM(BaseLLM):
        def available(self):
            return True

        def extract(self, text, hints):
            return [
                {"type": "NAME_CN", "text": "姓名:张三", "confidence": 0.9},
                {"type": "SECRET_INFO", "text": "密钥sk-test-123456", "confidence": 0.9},
            ]

    text = "姓名:张三\n密钥sk-test-123456"
    spans = LLMEngine(LabeledLLM(), load_builtin_types(RESOURCES)).detect(text, [])
    texts = {text[item.start : item.end] for item in spans}
    assert "张三" in texts
    assert "sk-test-123456" in texts
    assert "姓名:张三" not in texts
    assert "密钥sk-test-123456" not in texts


def test_llm_engine_keeps_address_with_digits():
    class AddressLLM(BaseLLM):
        def available(self):
            return True

        def extract(self, text, hints):
            return [{"type": "ADDRESS_CN", "text": "北京市朝阳区1号", "confidence": 0.9}]

    text = "地址：北京市朝阳区1号"
    spans = LLMEngine(AddressLLM(), load_builtin_types(RESOURCES)).detect(text, [])
    assert [text[item.start : item.end] for item in spans] == ["北京市朝阳区1号"]


def test_llm_engine_accepts_suspected_type_for_unknown_fields():
    class SuspectLLM(BaseLLM):
        def available(self):
            return True

        def extract(self, text, hints):
            assert any(item["code"] == "SUSPECTED" for item in hints)
            return [{"type": "SUSPECTED", "text": "2026/10/26", "confidence": 0.6}]

    engine = LLMEngine(SuspectLLM(), load_builtin_types(RESOURCES))
    spans = engine.detect("出生日期2026/10/26", [])
    assert spans[0].type_code == "SUSPECTED"
    assert spans[0].level == "low"
    assert spans[0].text == "2026/10/26"


def test_llm_engine_keeps_online_suggestion():
    class SuggestLLM(BaseLLM):
        name = "online"

        def available(self):
            return True

        def extract(self, text, hints):
            return [{"type": "NAME_CN", "text": "张三", "confidence": 0.9, "suggest": "replace"}]

    spans = LLMEngine(SuggestLLM(), load_builtin_types(RESOURCES)).detect("张三", [])
    assert spans[0].suggest == "replace"


def test_llm_engine_maps_unknown_type_to_suspected_for_online():
    class UnknownLLM(BaseLLM):
        name = "online"

        def available(self):
            return True

        def extract(self, text, hints):
            return [
                {
                    "type": "API_KEY",
                    "text": "sk-abc123456789012345",
                    "confidence": 0.8,
                    "suggest": "mask",
                }
            ]

    text = "密钥sk-abc123456789012345"
    spans = LLMEngine(UnknownLLM(), load_builtin_types(RESOURCES)).detect(text, [])
    assert spans[0].type_code == "SUSPECTED"
    assert spans[0].suggest == "mask"


def test_llm_engine_keeps_ignore_suggestion_for_low_risk():
    class IgnoreLLM(BaseLLM):
        name = "online"

        def available(self):
            return True

        def extract(self, text, hints):
            return [{"type": "SUSPECTED", "text": "2026/10/26", "confidence": 0.6, "suggest": "ignore"}]

    spans = LLMEngine(IgnoreLLM(), load_builtin_types(RESOURCES)).detect("出生日期2026/10/26", [])
    assert spans[0].suggest == "ignore"


def test_llm_engine_drops_ignore_suggestion_for_high_level():
    class IgnoreHighLLM(BaseLLM):
        name = "online"

        def available(self):
            return True

        def extract(self, text, hints):
            return [{"type": "PHONE_CN", "text": "13800138000", "confidence": 0.9, "suggest": "ignore"}]

    spans = LLMEngine(IgnoreHighLLM(), load_builtin_types(RESOURCES)).detect("13800138000", [])
    assert spans[0].suggest == ""


def test_llm_engine_normalizes_type_code_case():
    class LowerLLM(BaseLLM):
        def available(self):
            return True

        def extract(self, text, hints):
            return [{"type": "SusPected", "text": "2026/10/26", "confidence": 0.8}]

    spans = LLMEngine(LowerLLM(), load_builtin_types(RESOURCES)).detect("出生日期2026/10/26", [])
    assert spans[0].type_code == "SUSPECTED"


def test_llm_engine_skips_whitespace_and_single_char_fragments():
    class BadLLM(BaseLLM):
        def available(self):
            return True

        def extract(self, text, hints):
            return [
                {"type": "NAME_CN", "text": " ", "confidence": 0.9},
                {"type": "NAME_CN", "text": "A", "confidence": 0.9},
            ]

    engine = LLMEngine(BadLLM(), load_builtin_types(RESOURCES))
    assert engine.detect("A B C", []) == []


def test_llm_engine_clamps_confidence():
    class HighLLM(BaseLLM):
        def available(self):
            return True

        def extract(self, text, hints):
            return [{"type": "NAME_CN", "text": "张三", "confidence": 9.5}]

    engine = LLMEngine(HighLLM(), load_builtin_types(RESOURCES))
    spans = engine.detect("张三", [])
    assert spans[0].confidence == 1.0


def test_llm_engine_ignores_unknown_type_and_masked_fragment():
    class BadLLM(BaseLLM):
        def available(self):
            return True

        def extract(self, text, hints):
            return [
                {"type": "UNKNOWN", "text": "张三", "confidence": 0.9},
                {"type": "NAME_CN", "text": "██", "confidence": 0.9},
            ]

    engine = LLMEngine(BadLLM(), load_builtin_types(RESOURCES))
    assert engine.detect("张三", []) == []
