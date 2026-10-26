import json
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.security.integrity import build_manifest, sign_manifest  # noqa: E402
from app.core.security.resources import pack_bundle  # noqa: E402


def main() -> None:
    resources = BACKEND / "resources"
    pack_bundle(resources, resources / "rules.enc")
    print(f"已生成加密资源：{resources / 'rules.enc'}")

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "dist" / "privacy-backend"
    if not target.exists():
        return

    # PyInstaller 6 的 one-dir 产物把运行时目录放在 _internal（即运行期 _MEIPASS），
    # manifest 必须针对该目录生成，启动校验才能覆盖 exe 依赖与加密资源。
    internal = target / "_internal"
    base = internal if internal.is_dir() else target

    target_resources = base / "resources"
    target_resources.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(resources / "rules.enc", target_resources / "rules.enc")
    print(f"已复制加密资源到：{target_resources / 'rules.enc'}")
    print("提醒：分发时不要包含 resources/types.default.json 与 resources/prompts/llm_extract.txt")

    # 重复执行时先移除旧清单，避免清单把自身旧副本计入哈希。
    for stale in (base / "manifest.json", target / "manifest.json"):
        stale.unlink(missing_ok=True)

    manifest = build_manifest(base)
    payload = {"manifest": manifest, "signature": sign_manifest(manifest)}
    manifest_text = json.dumps(payload, ensure_ascii=False, indent=2)
    (base / "manifest.json").write_text(manifest_text, encoding="utf-8")
    print(f"已生成完整性清单：{base / 'manifest.json'}")

    if base != target:
        # 便于人工查看，根目录再放一份副本；启动校验只读取 _internal 下的正本。
        (target / "manifest.json").write_text(manifest_text, encoding="utf-8")
        print(f"已复制完整性清单副本：{target / 'manifest.json'}")


if __name__ == "__main__":
    main()
