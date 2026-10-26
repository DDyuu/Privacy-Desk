from dataclasses import replace

from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeDefinition

RULE_PRIORITY_TYPES = {
    "ID_CARD_CN",
    "BANK_CARD",
    "PHONE_CN",
    "EMAIL",
    "IPV4",
    "PLATE_CN",
    "PASSPORT_CN",
}
LLM_PRIORITY_TYPES = {"NAME_CN", "ADDRESS_CN", "SECRET_INFO"}
LEVEL_RANK = {"high": 2, "medium": 1, "low": 0}


def _source_bonus(span: Span) -> int:
    if span.type_code in RULE_PRIORITY_TYPES:
        return 1 if span.source == "rule" else 0
    if span.type_code in LLM_PRIORITY_TYPES:
        return 1 if span.source == "llm" else 0
    return 0


def fuse(rule_spans: list[Span], llm_spans: list[Span], types: list[TypeDefinition]) -> list[Span]:
    """按等级、来源优先级、置信度与长度贪心选取互不重叠的 span。"""
    levels = {definition.code: definition.level for definition in types}

    def score(span: Span) -> tuple[int, int, float, int]:
        return (
            LEVEL_RANK.get(span.level, 1),
            _source_bonus(span),
            span.confidence,
            span.end - span.start,
        )

    accepted: list[Span] = []
    for candidate in sorted(rule_spans + llm_spans, key=score, reverse=True):
        if any(
            candidate.start < kept.end and kept.start < candidate.end for kept in accepted
        ):
            continue
        accepted.append(replace(candidate, level=levels.get(candidate.type_code, candidate.level)))
    return sorted(accepted, key=lambda item: (item.start, item.end, item.type_code))
