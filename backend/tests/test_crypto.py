import pytest

from app.core.security import crypto


def test_encrypt_decrypt_roundtrip():
    key = b"k" * 32
    blob = crypto.encrypt(key, b"hello", b"aad")
    assert blob != b"hello"
    assert crypto.decrypt(key, blob, b"aad") == b"hello"


def test_decrypt_with_wrong_aad_fails():
    key = b"k" * 32
    blob = crypto.encrypt(key, b"hello", b"aad-1")
    with pytest.raises(Exception):
        crypto.decrypt(key, blob, b"aad-2")


def test_tampered_ciphertext_fails():
    key = b"k" * 32
    blob = crypto.encrypt(key, b"hello", b"aad")
    tampered = blob[:-1] + bytes([blob[-1] ^ 0xFF])
    with pytest.raises(Exception):
        crypto.decrypt(key, tampered, b"aad")


def test_base64url_roundtrip():
    data = bytes(range(32))
    assert crypto.b64url_decode(crypto.b64url_encode(data)) == data
