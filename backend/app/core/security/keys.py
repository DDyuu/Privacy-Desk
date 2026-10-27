"""主密码派生链：Argon2id 生成主密钥，HKDF 再由主密钥派生出数据密钥。"""

import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.security import crypto

SALT_LEN = 16
# 固定的已知明文：解锁时用它验证密码是否正确（GCM 认证失败即视为密码错误）
CANARY = b"PRIVACY-DESK-CANARY-V1"


def new_salt() -> bytes:
    return os.urandom(SALT_LEN)


def derive_master_key(password: str, salt: bytes) -> bytes:
    """Argon2id 派生主密钥；参数固定，保证跨启动可复现。"""
    # 这组参数（3 轮 / 64 MiB / 并行度 2 / 32 字节输出）写死在代码里，
    # 一旦改动，旧库用同一密码也派生不出同一主密钥，将无法解密。
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
    # info 是域分隔标签：同一主密钥下，不同用途会派生出互不相干的子密钥
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"data/v1",
    ).derive(master_key)


def seal_canary(master_key: bytes) -> bytes:
    # AAD 固定为 meta:canary，把该密文绑定到"密码校验"用途，不能当普通数据密文挪用
    return crypto.encrypt(master_key, CANARY, b"meta:canary")


def verify_canary(master_key: bytes, sealed: bytes) -> bool:
    try:
        # 密码错误或 canary 被替换都会让 GCM 认证失败，统一当作"不正确"返回
        return crypto.decrypt(master_key, sealed, b"meta:canary") == CANARY
    except Exception:
        return False
