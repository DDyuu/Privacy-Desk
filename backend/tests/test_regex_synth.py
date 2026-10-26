import re

from app.core.detect.regex_synth import synthesize_pattern


def full_match(pattern: str, sample: str) -> bool:
    found = re.search(pattern, sample)
    return found is not None and found.group(0) == sample


def test_preserves_identical_segments_as_literals():
    result = synthesize_pattern(["EMP-23003", "EMP-23004"])
    assert result["total"] == 2
    assert result["matched"] == 2
    assert "EMP" in result["pattern"]
    assert "[A-Za-z]" not in result["pattern"]
    assert full_match(result["pattern"], "EMP-23003")
    assert full_match(result["pattern"], "EMP-23004")


def test_single_sample_still_generalizes_classes():
    result = synthesize_pattern(["EMP-23003"])
    assert "[A-Za-z]{3}" in result["pattern"]
    assert "EMP" not in result["pattern"]


def test_generates_digit_pattern_with_length_range():
    result = synthesize_pattern(["13800138000", "1380013800"])
    assert result["matched"] == 2
    assert full_match(result["pattern"], "13800138000")
    assert full_match(result["pattern"], "1380013800")
    assert result["pattern"].startswith(r"(?<![0-9A-Za-z])\d{")


def test_preserves_identical_chinese_prefix():
    result = synthesize_pattern(
        ["广东省深圳市南山区科技园1号", "广东省深圳市南山区科技园2号"]
    )
    assert result["matched"] == 2
    assert "广东省深圳市南山区科技园" in result["pattern"]
    assert full_match(result["pattern"], "广东省深圳市南山区科技园1号")


def test_different_shapes_fall_back_to_alternation():
    result = synthesize_pattern(["EMP-23003", "23003"])
    assert result["matched"] == 2
    assert "|" in result["pattern"]
    assert full_match(result["pattern"], "EMP-23003")
    assert full_match(result["pattern"], "23003")


def test_ignores_empty_and_duplicate_samples():
    result = synthesize_pattern(["  ", "EMP-23003", "EMP-23003", ""])
    assert result["total"] == 1
    assert result["matched"] == 1


def test_empty_samples_return_empty_pattern():
    result = synthesize_pattern(["", "   "])
    assert result["pattern"] == ""
    assert result["total"] == 0
