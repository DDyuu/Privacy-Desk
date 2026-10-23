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
