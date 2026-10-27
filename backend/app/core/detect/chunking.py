def chunk_text(text: str, size: int = 2000, overlap: int = 100) -> list[tuple[int, int]]:
    """按字符数切块，优先在空白处断开，块间保留重叠。"""
    # overlap 必须小于块长，否则游标无法前进（死循环）
    if size <= overlap or overlap < 0:
        raise ValueError(f"非法分块参数：size={size}, overlap={overlap}")
    if not text:
        # 空文本也返回一个空块，调用方无需特判
        return [(0, 0)]
    if len(text) <= size:
        return [(0, len(text))]
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # 尽量在空白处断开，避免把实体截成两半
            cut = max(text.rfind(char, start, end) for char in ("\n", "\r", "\t", " ", "　"))
            # 断点太靠前会让块过短，此时退化为硬切
            if cut > start + size // 2:
                # +1 把分隔符留在本块，下一块从其后开始
                end = cut + 1
        chunks.append((start, end))
        if end >= len(text):
            break
        # 回退 overlap 让跨块边界的实体完整落入某一块；max 兜底防止游标停滞
        start = max(end - overlap, start + 1)
    return chunks
