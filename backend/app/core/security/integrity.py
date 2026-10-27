"""资源目录完整性清单：逐文件算 SHA-256 汇总后用 HMAC 签名，防止清单本身被改写。"""

import hashlib
import hmac
import json
from pathlib import Path

# 签名密钥与代码同仓：只能发现意外损坏或局部篡改，
# 无法抵御能同时修改代码的攻击者。
INTEGRITY_SECRET = b"privacy-desk-integrity-v1"


def build_manifest(root: Path) -> dict:
    files: dict[str, str] = {}
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        # 跳过 Python 运行期产物，它们随执行变化且与资源内容无关
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        # 统一用正斜杠做键，避免 Windows/Linux 生成的清单不一致
        relative = str(path.relative_to(root)).replace("\\", "/")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": files}


def sign_manifest(manifest: dict, secret: bytes = INTEGRITY_SECRET) -> str:
    # 规范化为排序 + 紧凑 JSON，保证同一清单在不同 Python 版本下字节一致
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret, canonical, hashlib.sha256).hexdigest()


def verify_manifest(
    root: Path, manifest: dict, signature: str, secret: bytes = INTEGRITY_SECRET
) -> list[str]:
    # 先验签再逐个比对文件，否则清单可被随意改写后指向伪造的哈希
    if not hmac.compare_digest(sign_manifest(manifest, secret), signature):
        return ["manifest 签名无效"]
    problems: list[str] = []
    # 只核对清单中列出的文件；目录里多出来的文件不在检查范围内
    for relative, expected in manifest["files"].items():
        path = Path(root) / relative
        if not path.exists():
            problems.append(f"缺失文件：{relative}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            problems.append(f"文件被篡改：{relative}")
    return problems
