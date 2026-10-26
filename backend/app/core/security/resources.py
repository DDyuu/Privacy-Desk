import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.security import crypto

BUNDLE_VERSION = "v1"
_SEED = b"privacy-desk-resources"


def resource_key(version: str = BUNDLE_VERSION) -> bytes:
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
            raise RuntimeError("加密资源解密失败，可能被篡改") from exc
    if _require_encrypted():
        raise RuntimeError("缺少加密资源 rules.enc")
    return {
        "types": json.loads((resources_dir / "types.default.json").read_text(encoding="utf-8")),
        "prompt": (resources_dir / "prompts" / "llm_extract.txt").read_text(encoding="utf-8"),
    }


def load_prompt(resources_dir: Path) -> str:
    return load_bundle(resources_dir)["prompt"]
