from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.detect.checksum import validate_checksum
from app.core.detect.types import TypeDefinition


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    type_code: str
    text: str
    confidence: float
    source: str
    level: str = "medium"

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "type_code": self.type_code,
            "text": self.text,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "level": self.level,
        }


def _find_all(text: str, needle: str):
    start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            return
        yield index
        start = index + 1


class RuleEngine:
    """正则、关键词、校验位与词典的确定性识别。"""

    def __init__(self, types: list[TypeDefinition]) -> None:
        self._types = [item for item in types if item.enabled]

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for definition in self._types:
            checksum = next(
                (d.algo for d in definition.detectors if d.kind == "checksum" and d.algo), None
            )
            candidates: list[tuple[int, int, float]] = []
            for detector in definition.detectors:
                if detector.kind == "regex" and detector.pattern:
                    flags = re.IGNORECASE if "i" in detector.flags else 0
                    for match in re.finditer(detector.pattern, text, flags):
                        candidates.append((match.start(), match.end(), 0.9))
                elif detector.kind in ("keyword", "dict"):
                    for word in detector.words:
                        if not word:
                            continue
                        for position in _find_all(text, word):
                            candidates.append((position, position + len(word), 0.8))
            kept: list[tuple[int, int, float]] = []
            for start, end, confidence in sorted(
                candidates, key=lambda item: (item[0], -(item[1] - item[0]))
            ):
                if kept and start < kept[-1][1]:
                    continue
                if checksum and not validate_checksum(checksum, text[start:end]):
                    continue
                kept.append((start, end, confidence))
            for start, end, confidence in kept:
                spans.append(
                    Span(
                        start=start,
                        end=end,
                        type_code=definition.code,
                        text=text[start:end],
                        confidence=0.99 if checksum else confidence,
                        source="rule",
                        level=definition.level,
                    )
                )
        return spans
