import re

from app.core.security import crypto


def mask_value(value: str, keep_prefix: int = 0, keep_suffix: int = 0) -> str:
    if len(value) <= keep_prefix + keep_suffix:
        return "*" * len(value)
    head = value[:keep_prefix]
    tail = value[len(value) - keep_suffix:] if keep_suffix else ""
    return head + "*" * (len(value) - keep_prefix - keep_suffix) + tail


def replace_value(value: str, token: str) -> str:
    return token


def fuzz_value(value: str, type_code: str) -> str:
    if type_code == "ADDRESS_CN":
        match = re.match(r"^(.{2,6}?(?:省|市|自治区))", value)
        prefix = match.group(1) if match else value[:2]
        return f"{prefix}某处"
    if type_code == "NAME_CN":
        return value[:1] + "*" * max(len(value) - 1, 1)
    return "[已模糊]"


def encrypt_value(value: str, key: bytes, aad: bytes) -> str:
    token = crypto.encrypt(key, value.encode("utf-8"), aad)
    return "ENC:" + crypto.b64url_encode(token)
