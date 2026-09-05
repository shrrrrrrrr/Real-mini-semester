"""语义分块：把解析产物切成适合检索的文本块。

策略（开发文档 §5.2 技术点④）：
- 优先在段落边界切分，贪心合并到目标长度（默认 400 字符）；
- 相邻块保留 overlap 字重叠提升检索召回；
- 重叠不跨"定位单元"（页/幻灯片/章节），保证引用定位符精确；
- 超长单段（如 PDF 整页塞进一个 ParsedUnit）需要二次切分。
"""

from app.core.parser import ParsedUnit

TARGET_LEN = 400  # 目标块长（中文字符）
OVERLAP = 50      # 相邻块重叠长度


def _split_long_text(text: str, target: int) -> list[str]:
    """超长文本二次切分：在句读处优先断开，避免把句子拦腰截断。"""
    pieces: list[str] = []
    rest = text
    while len(rest) > target:
        # 在目标位置附近向前找最近的句读符号（中文句号/分号/换行/英文句号）
        cut = target
        for i in range(target, max(target - 150, 0), -1):
            if rest[i - 1] in "。；\n.!?；":
                cut = i
                break
        pieces.append(rest[:cut])
        rest = rest[cut:]
    if rest.strip():
        pieces.append(rest)
    return pieces


def chunk_units(
    units: list[ParsedUnit],
    target: int = TARGET_LEN,
    overlap: int = OVERLAP,
) -> list[dict]:
    """把 ParsedUnit 列表分块。

    返回：[{"locator": str, "content": str, "token_count": int}]
    同一 ParsedUnit 内的多个块共享定位符；相邻块仅在单元内做重叠。
    """
    chunks: list[dict] = []
    for unit in units:
        # 单元文本过短直接成块（保留页码/章节上下文）
        pieces = _split_long_text(unit.text, target)
        carry = ""  # 单元内上一块尾部，用于重叠衔接
        for piece in pieces:
            content = (carry + piece) if carry else piece
            if len(content) < 40:  # 过碎的块并入下一块
                carry = content
                continue
            chunks.append(
                {
                    "locator": unit.locator,
                    "content": content,
                    "token_count": len(content),
                }
            )
            # 重叠 = 本块尾部 OVERLAP 字，作为下一块开头
            carry = content[-overlap:] if overlap > 0 else ""
        if carry and carry.strip():
            # 尾部残留（过碎未并入的）合并进本单元最后一块
            if chunks and chunks[-1]["locator"] == unit.locator:
                chunks[-1]["content"] += "\n" + carry
            else:
                chunks.append(
                    {
                        "locator": unit.locator,
                        "content": carry,
                        "token_count": len(carry),
                    }
                )
    return chunks
