"""从正例归纳一个可编辑的候选正则，全部在本地完成。"""

from __future__ import annotations

import re

# 样例越多越泛化，但计算量和 ReDoS 风险也随之上升
MAX_SAMPLES = 20
# 过长的“样例”通常是误贴整段文本，无法参与归纳
MAX_SAMPLE_LEN = 200


def _classify(ch: str) -> str:
    # 只分五类；其余标点按字面量处理，用 lit: 前缀标记
    if "0" <= ch <= "9":
        return "digit"
    if ("A" <= ch <= "Z") or ("a" <= ch <= "z"):
        return "alpha"
    if "\u4e00" <= ch <= "\u9fa5":
        return "han"
    if ch.isspace():
        return "space"
    return "lit:" + ch


def _tokenize(text: str) -> list[tuple[str, str]]:
    """把样例拆成字符类别段，例如 EMP-23003 → [alpha"EMP", "-", digit"23003"]。"""
    tokens: list[tuple[str, str]] = []
    for ch in text:
        cls = _classify(ch)
        # 同类字符合并成段；字面量不合并，保持每个符号独立，便于原样保留
        if tokens and tokens[-1][0] == cls and not cls.startswith("lit:"):
            tokens[-1] = (cls, tokens[-1][1] + ch)
        else:
            tokens.append((cls, ch))
    return tokens


def _atom(cls: str) -> str:
    if cls == "digit":
        return r"\d"
    if cls == "alpha":
        return "[A-Za-z]"
    if cls == "han":
        return r"[\u4e00-\u9fa5]"
    if cls == "space":
        return r"\s"
    # lit: 前缀去掉后就是原字符，转义后作为字面量
    return re.escape(cls[4:])


def _part(cls: str, length: int) -> str:
    atom = _atom(cls)
    if cls.startswith("lit:"):
        return atom
    if length <= 1:
        return atom
    # 多字符段用精确长度量词，长度区间在外面按样例最大最小补齐
    return f"{atom}{{{length}}}"


def _build_pattern(groups: dict[tuple[str, ...], list[list[tuple[str, str]]]]) -> str:
    alternatives: list[str] = []
    # 按字符类别序列分组：结构相同的样例才能合并到同一个分支
    for signature, token_lists in groups.items():
        # 同一分支至少有两个样例才谈得上“共同固定段”
        same_segment = len(token_lists) >= 2
        parts: list[str] = []
        for index, cls in enumerate(signature):
            texts = [tokens[index][1] for tokens in token_lists]
            first = texts[0]
            if same_segment and all(text == first for text in texts):
                # 所有样例中这一段完全相同，保留字面量，避免把固定前缀泛化掉
                parts.append(re.escape(first))
                continue
            low = min(len(text) for text in texts)
            high = max(len(text) for text in texts)
            if low == high:
                parts.append(_part(cls, low))
            else:
                # 长度不一致时用区间量词，保证每个样例都被覆盖
                parts.append(f"{_atom(cls)}{{{low},{high}}}")
        alternatives.append("".join(parts))
    body = alternatives[0] if len(alternatives) == 1 else "(?:" + "|".join(alternatives) + ")"
    # 两侧加非字母数字断言，避免在更长的串里截取子串
    return r"(?<![0-9A-Za-z])" + body + r"(?![0-9A-Za-z])"


def _count_full_matches(pattern: str, samples: list[str]) -> int:
    try:
        compiled = re.compile(pattern)
    except re.error:
        return 0
    matched = 0
    for sample in samples:
        found = compiled.search(sample)
        # 只有命中区间恰好覆盖整串才算数，防止宽松模式虚高
        if found and found.group(0) == sample:
            matched += 1
    return matched


def _fallback_pattern(samples: list[str]) -> str:
    # 归纳失败时退化为样例的精确并集，至少保证可用
    body = "|".join(re.escape(sample) for sample in samples)
    return r"(?<![0-9A-Za-z])(?:" + body + r")(?![0-9A-Za-z])"


def synthesize_pattern(samples: list[str]) -> dict:
    """根据正例归纳正则；无法完全命中时退化为逐条精确匹配。"""
    cleaned: list[str] = []
    for raw in samples:
        sample = (raw or "").strip()
        # 去重并限制条数：重复样例不影响结果，过多则会让模式过度泛化
        if sample and len(sample) <= MAX_SAMPLE_LEN and sample not in cleaned:
            cleaned.append(sample)
        if len(cleaned) >= MAX_SAMPLES:
            break
    if not cleaned:
        return {"pattern": "", "matched": 0, "total": 0, "message": "请至少提供一条有效样例"}

    groups: dict[tuple[str, ...], list[list[tuple[str, str]]]] = {}
    for sample in cleaned:
        tokens = _tokenize(sample)
        signature = tuple(cls for cls, _ in tokens)
        groups.setdefault(signature, []).append(tokens)

    pattern = _build_pattern(groups)
    matched = _count_full_matches(pattern, cleaned)
    if matched < len(cleaned):
        pattern = _fallback_pattern(cleaned)
        matched = _count_full_matches(pattern, cleaned)

    return {
        "pattern": pattern,
        "matched": matched,
        "total": len(cleaned),
        "message": "" if matched == len(cleaned) else "部分样例无法完全命中，已退化为精确匹配",
    }
