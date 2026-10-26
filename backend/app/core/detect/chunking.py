def chunk_text(text: str, size: int = 2000, overlap: int = 100) -> list[tuple[int, int]]:
    """按字符数切块，优先在空白处断开，块间保留重叠。"""
    if size <= overlap or overlap < 0:
        raise ValueError(f"非法分块参数：size={size}, overlap={overlap}")
    if not text:
        return [(0, 0)]
    if len(text) <= size:
        return [(0, len(text))]
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = max(text.rfind(char, start, end) for char in ("\n", "\r", "\t", " ", "　"))
            if cut > start + size // 2:
                end = cut + 1
        chunks.append((start, end))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
