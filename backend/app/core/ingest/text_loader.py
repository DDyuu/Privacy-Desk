from pathlib import Path

from app.core.ingest.model import Block, DocumentModel, build_model


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_text(path: Path) -> DocumentModel:
    text = decode_text(Path(path).read_bytes())
    blocks = [Block(kind="paragraph", text=line) for line in text.split("\n")]
    fmt = Path(path).suffix.lstrip(".").lower() or "txt"
    return build_model(blocks, fmt)
