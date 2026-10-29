"""确定性识别：正则 / 关键词 / 词典 / 校验位，产出可直接定位的 Span。"""

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
    # ignored：用户显式排除的片段，进入报告但不参与脱敏与风险判定
    ignored: bool = False
    # suggest：在线大模型给出的推荐动作（mask/replace/fuzz/encrypt），本地模式为空
    suggest: str = ""

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "type_code": self.type_code,
            "text": self.text,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "level": self.level,
            "ignored": self.ignored,
            "suggest": self.suggest,
        }


def _find_all(text: str, needle: str):
    # 每次只前进 1 个字符，允许命中相互重叠，避免漏掉紧邻重复的片段
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
            # 校验算法与剔除字符按类型整体生效，取该类型第一个声明的即可
            checksum = next(
                (d.algo for d in definition.detectors if d.kind == "checksum" and d.algo), None
            )
            strip_chars = next(
                (d.strip for d in definition.detectors if d.kind == "regex" and d.strip), None
            )
            candidates: list[tuple[int, int, float]] = []
            for detector in definition.detectors:
                if detector.kind == "regex" and detector.pattern:
                    # 只支持 i 标志：大小写不敏感是本链路唯一实际需要的开关
                    flags = re.IGNORECASE if "i" in detector.flags else 0
                    confidence = 0.9 if detector.confidence is None else detector.confidence
                    for match in re.finditer(detector.pattern, text, flags):
                        start, end = match.start(), match.end()
                        # 宽松规则常把“标签:号码”整体匹配进来，去掉号码前的分隔符
                        while start < end and text[start] in ":： \t":
                            start += 1
                        if start < end:
                            candidates.append((start, end, confidence))
                elif detector.kind in ("keyword", "dict"):
                    for word in detector.words:
                        if not word:
                            continue
                        for position in _find_all(text, word):
                            candidates.append((position, position + len(word), 0.8))
            kept: list[tuple[int, int, float]] = []
            # 同起点优先保留更长的候选：(起点升序, 长度降序)
            for start, end, confidence in sorted(
                candidates, key=lambda item: (item[0], -(item[1] - item[0]))
            ):
                if kept and start < kept[-1][1]:
                    # 已按起点升序处理，只需与最近保留项比较；重叠即丢弃（贪心去重）
                    continue
                target = text[start:end]
                if strip_chars:
                    # 校验位算法对分隔符敏感，先剔除再比对
                    target = target.translate(str.maketrans("", "", strip_chars))
                if checksum and not validate_checksum(checksum, target):
                    continue
                kept.append((start, end, confidence))
            for start, end, confidence in kept:
                spans.append(
                    Span(
                        start=start,
                        end=end,
                        type_code=definition.code,
                        text=text[start:end],
                        # 校验位通过后误报概率极低，直接抬到接近确定性的置信度
                        confidence=0.99 if checksum else confidence,
                        source="rule",
                        level=definition.level,
                    )
                )
        return spans
