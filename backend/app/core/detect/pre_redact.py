from app.core.detect.rule_engine import Span


def pre_redact(text: str, spans: list[Span]) -> str:
    """对高敏片段做等长遮蔽，保证云端返回的片段仍能定位回原文。"""
    if not spans:
        return text
    chars = list(text)
    for span in spans:
        # 用等长 █ 覆盖：偏移保持不变，模型返回的片段仍能回定位到原文
        for index in range(max(span.start, 0), min(span.end, len(chars))):
            chars[index] = "█"
    return "".join(chars)
