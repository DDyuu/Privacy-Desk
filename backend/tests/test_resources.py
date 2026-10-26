import json
from pathlib import Path

import pytest

from app.core.detect.types import load_builtin_types
from app.core.security.resources import load_bundle, pack_bundle

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def test_pack_and_load_bundle(tmp_path):
    pack_bundle(RESOURCES, tmp_path / "rules.enc")
    bundle = load_bundle(tmp_path)
    assert len(bundle["types"]) == 15
    assert "隐私" in bundle["prompt"]


def test_tampered_bundle_fails(tmp_path):
    target = tmp_path / "rules.enc"
    pack_bundle(RESOURCES, target)
    blob = bytearray(target.read_bytes())
    blob[-1] ^= 0xFF
    target.write_bytes(bytes(blob))
    with pytest.raises(Exception):
        load_bundle(tmp_path)


def test_require_encrypted_rejects_plaintext(tmp_path, monkeypatch):
    from app.core.security.resources import load_bundle

    (tmp_path / "types.default.json").write_text("[]", encoding="utf-8")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "llm_extract.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("PRIVACY_DESK_REQUIRE_ENCRYPTED_RESOURCES", "1")
    with pytest.raises(RuntimeError, match="rules.enc"):
        load_bundle(tmp_path)


def test_load_builtin_types_prefers_encrypted_bundle(tmp_path):
    original = json.loads((RESOURCES / "types.default.json").read_text(encoding="utf-8"))
    (tmp_path / "types.default.json").write_text(
        json.dumps(original[:1], ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "llm_extract.txt").write_text("提示词", encoding="utf-8")
    bundle = {
        "types": original,
        "prompt": "来自加密包",
    }
    from app.core.security import crypto
    from app.core.security.resources import resource_key

    payload = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    (tmp_path / "rules.enc").write_bytes(crypto.encrypt(resource_key(), payload, b"rules"))
    assert len(load_builtin_types(tmp_path)) == 15
