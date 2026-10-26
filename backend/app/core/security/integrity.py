import hashlib
import hmac
import json
from pathlib import Path

INTEGRITY_SECRET = b"privacy-desk-integrity-v1"


def build_manifest(root: Path) -> dict:
    files: dict[str, str] = {}
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": files}


def sign_manifest(manifest: dict, secret: bytes = INTEGRITY_SECRET) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret, canonical, hashlib.sha256).hexdigest()


def verify_manifest(
    root: Path, manifest: dict, signature: str, secret: bytes = INTEGRITY_SECRET
) -> list[str]:
    if not hmac.compare_digest(sign_manifest(manifest, secret), signature):
        return ["manifest 签名无效"]
    problems: list[str] = []
    for relative, expected in manifest["files"].items():
        path = Path(root) / relative
        if not path.exists():
            problems.append(f"缺失文件：{relative}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            problems.append(f"文件被篡改：{relative}")
    return problems
