import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.security import crypto

SALT_LEN = 16
CANARY = b"PRIVACY-DESK-CANARY-V1"


def new_salt() -> bytes:
    return os.urandom(SALT_LEN)


def derive_master_key(password: str, salt: bytes) -> bytes:
    """Argon2id 派生主密钥；参数固定，保证跨启动可复现。"""
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        type=Type.ID,
    )


def derive_data_key(master_key: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"data/v1",
    ).derive(master_key)


def seal_canary(master_key: bytes) -> bytes:
    return crypto.encrypt(master_key, CANARY, b"meta:canary")


def verify_canary(master_key: bytes, sealed: bytes) -> bool:
    try:
        return crypto.decrypt(master_key, sealed, b"meta:canary") == CANARY
    except Exception:
        return False
