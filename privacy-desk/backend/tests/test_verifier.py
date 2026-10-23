from pathlib import Path

from app.core.detect.rule_engine import RuleEngine
from app.core.detect.types import TypeRegistry, load_builtin_types
from app.core.mask.verifier import Verifier

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def verifier():
    types = load_builtin_types(RESOURCES)
    registry = TypeRegistry(types)
    return Verifier(registry, RuleEngine(types))


def test_passes_when_phone_is_masked():
    result = verifier().verify("电话13800138000", "电话*******8000")
    assert result.passed is True
    assert result.residuals == []
    assert result.metrics["residual_count"] == 0


def test_fails_when_high_risk_residual_remains():
    result = verifier().verify("电话13800138000", "电话13800138000")
    assert result.passed is False
    assert any("高敏" in issue for issue in result.issues)


def test_warns_on_extreme_length_change():
    result = verifier().verify("a" * 100, "a" * 10)
    assert any("长度" in issue for issue in result.issues)


def test_readability_warnings_do_not_block_passed():
    result = verifier().verify("a" * 100, "a" * 10)
    assert result.passed is True
    assert any("长度" in issue for issue in result.issues)


def test_warns_on_high_placeholder_density():
    result = verifier().verify("a" * 120, "*" * 120)
    assert any("占位符" in issue for issue in result.issues)


def test_to_dict_contains_metrics():
    payload = verifier().verify("电话13800138000", "电话*******8000").to_dict()
    assert payload["passed"] is True
    assert "placeholder_density" in payload["metrics"]
