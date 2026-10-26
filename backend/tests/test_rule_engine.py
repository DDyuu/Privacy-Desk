from pathlib import Path

from app.core.detect.rule_engine import RuleEngine, Span
from app.core.detect.types import Detector, TypeDefinition, load_builtin_types

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def engine():
    return RuleEngine(load_builtin_types(RESOURCES))


def test_detects_phone_and_valid_id():
    text = "联系人电话13800138000，身份证11010519491231002X。"
    spans = engine().detect(text)
    found = {(s.type_code, s.text) for s in spans}
    assert ("PHONE_CN", "13800138000") in found
    assert ("ID_CARD_CN", "11010519491231002X") in found


def test_rejects_invalid_id_checksum():
    spans = engine().detect("身份证110105194912310021")
    assert all(s.type_code != "ID_CARD_CN" for s in spans)


def test_detects_keyword_secret():
    spans = engine().detect("以下内容属于内部资料，请勿外传")
    assert any(s.type_code == "SECRET_INFO" for s in spans)


def test_span_offsets_point_to_original_text():
    text = "电话：13800138000"
    span = next(s for s in engine().detect(text) if s.type_code == "PHONE_CN")
    assert text[span.start:span.end] == span.text


def test_detects_bank_card():
    spans = engine().detect("银行卡4111111111111111")
    cards = [s for s in spans if s.type_code == "BANK_CARD"]
    assert len(cards) == 1
    assert cards[0].text == "4111111111111111"


def test_overlapping_candidates_keep_longest():
    definition = TypeDefinition(
        code="TEST_NUM",
        name="测试数字",
        category="custom",
        detectors=[
            Detector(kind="regex", pattern=r"\d{4}"),
            Detector(kind="regex", pattern=r"\d{6}"),
        ],
    )
    spans = RuleEngine([definition]).detect("编号123456结束")
    assert [s.text for s in spans] == ["123456"]


def test_detects_labeled_name_and_employee_id():
    text = "姓名:成语\n性别男\n工号--23003"
    found = {(s.type_code, s.text) for s in engine().detect(text)}
    assert ("NAME_CN", "成语") in found
    assert ("EMPLOYEE_ID", "--23003") in found


def test_detects_loose_variants_with_labels():
    text = (
        "手机号:138-0013-8000\n"
        "电话:010-12345678\n"
        "身份证:110105491231002\n"
        "身份证:110105 1949 1231 002X\n"
        "银行卡:4111 1111 1111 1111\n"
        "广东省深圳市南山区"
    )
    found = {(s.type_code, s.text) for s in engine().detect(text)}
    assert ("PHONE_LOOSE", "138-0013-8000") in found
    assert ("PHONE_LOOSE", "010-12345678") in found
    assert ("ID_CARD_LOOSE", "110105491231002") in found
    assert ("ID_CARD_LOOSE", "110105 1949 1231 002X") in found
    assert ("BANK_CARD_LOOSE", "4111 1111 1111 1111") in found
    assert any(code == "ADDRESS_PARTIAL" for code, _ in found)


def test_span_to_dict():
    span = Span(0, 3, "X", "abc", 0.9, "rule", "low")
    assert span.to_dict()["type_code"] == "X"
