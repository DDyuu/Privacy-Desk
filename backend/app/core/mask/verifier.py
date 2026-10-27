"""脱敏后校验：对遮蔽文本重跑规则识别，检查残留与文本形态是否异常。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.detect.rule_engine import RuleEngine, Span
from app.core.detect.types import TypeRegistry


@dataclass
class VerifyResult:
    passed: bool
    residuals: list[Span]
    metrics: dict
    issues: list[str]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "residuals": [span.to_dict() for span in self.residuals],
            "metrics": self.metrics,
            "issues": self.issues,
        }


class Verifier:
    def __init__(self, registry: TypeRegistry, rule_engine: RuleEngine) -> None:
        self._registry = registry
        self._rule_engine = rule_engine

    def verify(
        self,
        original_text: str,
        masked_text: str,
        ignored_spans: list[Span] | None = None,
    ) -> VerifyResult:
        # 只用确定性规则复检：不依赖大模型，离线或模型异常时校验仍可执行
        residuals = self._rule_engine.detect(masked_text)
        ignored_texts = [span.text for span in (ignored_spans or []) if span.text]
        if ignored_texts:
            # 用户明确排除的片段仍留在正文里，不能算作残留
            residuals = [
                replace(span, ignored=True)
                # 遮蔽后偏移已变化，只能用文本包含判断残留是否属于豁免片段
                if span.text and any(span.text in text for text in ignored_texts)
                else span
                for span in residuals
            ]
        # 豁免片段只进报告展示，不参与风险判定
        effective = [span for span in residuals if not span.ignored]
        high = [span for span in effective if span.level == "high"]
        # 遮蔽一般只会让文本变短，用保留率判断是否误删了正文
        ratio = len(masked_text) / max(len(original_text), 1)
        # 覆盖各算子的占位形态：█ 遮蔽、* 打码、[ 替换、ENC: 加密
        marker_count = sum(masked_text.count(char) for char in ("█", "*", "[", "ENC:"))
        density = marker_count / max(len(masked_text), 1)
        issues: list[str] = []
        if high:
            issues.append(f"仍有 {len(high)} 处高敏信息未清除")
        if ratio < 0.6:
            issues.append("文本长度变化超过 40%")
        # 短文本分母太小，密度指标没有参考价值，只在足够长时判定
        if len(masked_text) >= 100 and density > 0.4:
            issues.append("占位符字符占比超过 40%")
        metrics = {
            "ratio": round(ratio, 3),
            "placeholder_density": round(density, 3),
            "residual_count": len(effective),
            "high_risk_residual_count": len(high),
        }
        return VerifyResult(
            # 只有高风险残留会判失败，中低风险留在 metrics / issues 供人工复核
            passed=not high, residuals=residuals, metrics=metrics, issues=issues
        )
