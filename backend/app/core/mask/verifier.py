from __future__ import annotations

from dataclasses import dataclass

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

    def verify(self, original_text: str, masked_text: str) -> VerifyResult:
        residuals = self._rule_engine.detect(masked_text)
        high = [span for span in residuals if span.level == "high"]
        ratio = len(masked_text) / max(len(original_text), 1)
        marker_count = sum(masked_text.count(char) for char in ("█", "*", "[", "ENC:"))
        density = marker_count / max(len(masked_text), 1)
        issues: list[str] = []
        if high:
            issues.append(f"仍有 {len(high)} 处高敏信息未清除")
        if ratio < 0.6:
            issues.append("文本长度变化超过 40%")
        if len(masked_text) >= 100 and density > 0.4:
            issues.append("占位符字符占比超过 40%")
        metrics = {
            "ratio": round(ratio, 3),
            "placeholder_density": round(density, 3),
            "residual_count": len(residuals),
            "high_risk_residual_count": len(high),
        }
        return VerifyResult(
            passed=not high, residuals=residuals, metrics=metrics, issues=issues
        )
