from app.core.security.integrity import (
    build_manifest,
    sign_manifest,
    verify_manifest,
)


def test_manifest_detects_tamper(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    manifest = build_manifest(tmp_path)
    signature = sign_manifest(manifest)
    assert verify_manifest(tmp_path, manifest, signature) == []

    (tmp_path / "a.txt").write_text("changed", encoding="utf-8")
    problems = verify_manifest(tmp_path, manifest, signature)
    assert any("篡改" in item for item in problems)


def test_bad_signature_rejected(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    manifest = build_manifest(tmp_path)
    problems = verify_manifest(tmp_path, manifest, "bad-signature")
    assert problems and "签名" in problems[0]
