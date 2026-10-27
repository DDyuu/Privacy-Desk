"""AES-256-GCM 对称加密封装：固定 nonce 长度与密文拼接格式。"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_LEN = 12


def encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM 加密，返回 nonce(12B) + 密文 + tag。"""
    # 整个密文布局为 nonce || ciphertext || tag(16B)，tag 由 AESGCM 附在密文尾部；
    # aad 只参与认证、不写入结果，用于把密文绑定到某个固定上下文（如行 id）。
    nonce = os.urandom(NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if len(blob) <= NONCE_LEN:
        # 连 nonce 都切不出来就必然是脏数据；提前给出明确错误，tag 校验仍交给 AESGCM
        raise ValueError("密文长度非法")
    return AESGCM(key).decrypt(blob[:NONCE_LEN], blob[NONCE_LEN:], aad)


def b64url_encode(data: bytes) -> str:
    # 去掉 "=" 填充，使结果可直接放进 URL 或文件名
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)
