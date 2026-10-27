"""纯文本加载：按行切块；编码回退顺序兼顾 BOM 与中文环境。"""

from pathlib import Path

from app.core.ingest.model import Block, DocumentModel, build_model


def decode_text(raw: bytes) -> str:
    # 依次尝试带 BOM 的 UTF-8、普通 UTF-8、GB18030（兼容 GBK），覆盖常见中文文本
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    # 全部失败时用替换符兜底，避免个别坏字节导致整篇无法导入
    return raw.decode("utf-8", errors="replace")


def load_text(path: Path) -> DocumentModel:
    text = decode_text(Path(path).read_bytes())
    blocks = [Block(kind="paragraph", text=line) for line in text.split("\n")]
    fmt = Path(path).suffix.lstrip(".").lower() or "txt"
    return build_model(blocks, fmt)
