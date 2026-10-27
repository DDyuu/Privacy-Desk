"""内置规则与提示词资源的打包/加载；rules.enc 用固定密钥加密以便离线分发。"""

import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.security import crypto

BUNDLE_VERSION = "v1"
# 硬编码种子：资源包不依赖用户主密码，人人都能解开，只用于阻止直接阅读明文，
# 不能视为真正的机密性保护。
_SEED = b"privacy-desk-resources"


def resource_key(version: str = BUNDLE_VERSION) -> bytes:
    # 把版本号放进 info 做域分隔，换版本即换密钥，旧包与新包互不兼容
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"resources/" + version.encode("utf-8"),
    ).derive(_SEED)


def pack_bundle(resources_dir: Path, out_path: Path) -> None:
    bundle = {
        "types": json.loads((resources_dir / "types.default.json").read_text(encoding="utf-8")),
        "prompt": (resources_dir / "prompts" / "llm_extract.txt").read_text(encoding="utf-8"),
    }
    payload = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    # AAD 固定为 rules，把密文绑定到"规则包"这一用途
    out_path.write_bytes(crypto.encrypt(resource_key(), payload, b"rules"))


def _require_encrypted() -> bool:
    return os.environ.get("PRIVACY_DESK_REQUIRE_ENCRYPTED_RESOURCES") == "1"


def load_bundle(resources_dir: Path) -> dict:
    encrypted = resources_dir / "rules.enc"
    if encrypted.exists():
        try:
            payload = crypto.decrypt(resource_key(), encrypted.read_bytes(), b"rules")
            return json.loads(payload.decode("utf-8"))
        except Exception as exc:
            # 解密或解析失败一律视为被篡改，不静默回退到明文资源
            raise RuntimeError("加密资源解密失败，可能被篡改") from exc
    if _require_encrypted():
        # 生产环境通过环境变量强制要求加密包，缺失即失败；未设置时才允许回退读明文
        raise RuntimeError("缺少加密资源 rules.enc")
    return {
        "types": json.loads((resources_dir / "types.default.json").read_text(encoding="utf-8")),
        "prompt": (resources_dir / "prompts" / "llm_extract.txt").read_text(encoding="utf-8"),
    }


def load_prompt(resources_dir: Path) -> str:
    return load_bundle(resources_dir)["prompt"]
