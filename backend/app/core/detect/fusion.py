"""规则与大模型结果融合：按等级 / 来源 / 置信度 / 长度贪心消解重叠。"""

from dataclasses import replace

from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeDefinition

# 结构固定、可被校验位或格式验证的类型，规则命中通常更可信
RULE_PRIORITY_TYPES = {
    "ID_CARD_CN",
    "BANK_CARD",
    "PHONE_CN",
    "EMAIL",
    "IPV4",
    "PLATE_CN",
    "PASSPORT_CN",
}
# 依赖上下文语义、正则难以覆盖的类型，以模型结果为准
LLM_PRIORITY_TYPES = {"NAME_CN", "ADDRESS_CN", "SECRET_INFO"}
# 等级数值化，便于参与排序比较
LEVEL_RANK = {"high": 2, "medium": 1, "low": 0}


def _source_bonus(span: Span) -> int:
    # 同类型同等级时，按该类型更擅长的一方加分，用来打破置信度相近的平局
    if span.type_code in RULE_PRIORITY_TYPES:
        return 1 if span.source == "rule" else 0
    if span.type_code in LLM_PRIORITY_TYPES:
        return 1 if span.source == "llm" else 0
    return 0


def fuse(rule_spans: list[Span], llm_spans: list[Span], types: list[TypeDefinition]) -> list[Span]:
    """按等级、来源优先级、置信度与长度贪心选取互不重叠的 span。"""
    levels = {definition.code: definition.level for definition in types}

    def score(span: Span) -> tuple[int, int, float, int]:
        # 依次比较：等级 → 来源加分 → 置信度 → 长度（更长的匹配更完整）
        return (
            LEVEL_RANK.get(span.level, 1),
            _source_bonus(span),
            span.confidence,
            span.end - span.start,
        )

    accepted: list[Span] = []
    for candidate in sorted(rule_spans + llm_spans, key=score, reverse=True):
        # 按分数降序贪心：先接受者占位，与之重叠的候选无论多长都直接丢弃
        if any(
            candidate.start < kept.end and kept.start < candidate.end for kept in accepted
        ):
            continue
        accepted.append(replace(candidate, level=levels.get(candidate.type_code, candidate.level)))
    return sorted(accepted, key=lambda item: (item.start, item.end, item.type_code))
