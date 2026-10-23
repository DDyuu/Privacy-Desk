from pathlib import Path

from app.core.detect.checksum import gb11643_valid, luhn_valid
from app.core.detect.types import load_builtin_types


def test_gb11643_checksum():
    assert gb11643_valid("11010519491231002X") is True
    assert gb11643_valid("110105194912310021") is False
    assert gb11643_valid("12345") is False


def test_luhn_checksum():
    assert luhn_valid("4111111111111111") is True
    assert luhn_valid("4111111111111112") is False


def test_builtin_types_loaded():
    types = load_builtin_types(Path(__file__).resolve().parents[1] / "resources")
    codes = {t.code for t in types}
    assert {"ID_CARD_CN", "PHONE_CN", "BANK_CARD", "NAME_CN", "ADDRESS_CN", "SECRET_INFO"} <= codes
    assert len(types) == 10
    id_card = next(t for t in types if t.code == "ID_CARD_CN")
    assert id_card.level == "high"
    assert id_card.default_action == "mask"
    assert any(d.kind == "checksum" and d.algo == "gb11643" for d in id_card.detectors)
