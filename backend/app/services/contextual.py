"""Contextual Retrieval — US-049.

Vấn đề nó giải quyết
--------------------
Một đoạn văn tách khỏi tài liệu thường mất đi thứ làm nó tìm được. Đoạn::

    "Mức thu được xác định theo từng năm học và công bố trước kỳ tuyển sinh."

không chứa từ nào cho biết nó nói về **học phí**, cũng không cho biết nó thuộc
**quy chế của trường nào**. Truy vấn "học phí đại học Bách khoa" sẽ trượt nó ở
cả hai nhánh.

Cách làm: sinh 2–3 câu mô tả vị trí của đoạn trong tài liệu, rồi **ghép vào
đầu văn bản đem đi lập chỉ mục** — nhưng không ghép vào nội dung hiển thị.

Ghép vào CẢ HAI nhánh
---------------------
`SPEC.md` US-049 AC-2 yêu cầu prefix vào cả embedding lẫn `tsvector`. Số liệu
gốc của Anthropic cho thấy vì sao: chỉ contextual embedding giảm 35% tỉ lệ
trượt, thêm contextual BM25 nâng lên 49%. Bỏ một nửa là bỏ một nửa lợi ích.

Bất biến INV-1 không bị ảnh hưởng
---------------------------------
`content` vẫn là **đúng lát cắt** từ `full_text`. Prefix nằm ở cột riêng
`context_prefix`, chỉ tham gia vào lúc tính vector và `tsv`. Nhờ vậy trích dẫn
vẫn trỏ về đúng vị trí trên trang, và người dùng vẫn đọc đúng nguyên văn tài
liệu chứ không đọc phần mô tả do mô hình sinh ra.

Chi phí
-------
Một lượt gọi mô hình cho mỗi chunk. Với LLM cục bộ đó là thời gian GPU chứ
không phải tiền, nhưng vẫn phải đo và báo cáo (US-049 AC-4) — nó là cái giá
của dòng **E** trong bảng ablation.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.ports.llm import LLMProvider
from app.text.chunker import Chunk

__all__ = ["ContextualResult", "build_prefixes", "indexed_text"]

log = logging.getLogger(__name__)

# Bao nhiêu ký tự đầu tài liệu đưa vào prompt làm bối cảnh. Đủ để mô hình biết
# tài liệu nói về gì mà không thổi phồng chi phí cho mỗi chunk.
DOCUMENT_HEAD_CHARS = 2000

PREFIX_PROMPT = """Bạn nhận phần đầu của một tài liệu và một đoạn trích từ \
chính tài liệu đó.

Hãy viết 2–3 câu ngắn đặt đoạn trích vào bối cảnh: nó thuộc tài liệu gì, nói \
về chủ đề nào, và liên quan tới phần nào của tài liệu.

QUY TẮC
1. Chỉ dùng thông tin có trong hai phần được cung cấp. Không suy đoán.
2. Nêu rõ chủ thể mà đoạn trích nói tới, kể cả khi đoạn trích chỉ dùng đại từ.
3. KHÔNG chép lại nguyên văn đoạn trích.
4. Chỉ trả về phần mô tả. Không thêm lời dẫn, không giải thích."""


@dataclass
class ContextualResult:
    prefixes: list[str]
    seconds: float
    """Thời gian sinh toàn bộ prefix cho một tài liệu — số liệu cho US-049 AC-4."""

    failed: int
    """Số chunk không sinh được prefix. Chúng vẫn lập chỉ mục bình thường, chỉ
    là không có phần bối cảnh — suy giảm êm, không chặn cả tài liệu."""


def indexed_text(content: str, prefix: str | None) -> str:
    """Văn bản đem đi nhúng và sinh `tsvector`.

    KHÔNG phải văn bản hiển thị: trích dẫn luôn hiện `content` nguyên bản.
    """
    return f"{prefix}\n\n{content}" if prefix else content


async def build_prefixes(
    full_text: str,
    chunks: list[Chunk],
    *,
    llm: LLMProvider,
    on_progress: Callable[[int, int], None] | None = None,
) -> ContextualResult:
    """Sinh phần mô tả bối cảnh cho từng chunk."""
    head = full_text[:DOCUMENT_HEAD_CHARS]
    prefixes: list[str] = []
    failed = 0
    started = time.perf_counter()

    for i, chunk in enumerate(chunks, start=1):
        user = (
            f"PHẦN ĐẦU TÀI LIỆU:\n{head}\n\n"
            f"ĐOẠN TRÍCH{f' ({chunk.heading_path})' if chunk.heading_path else ''}:\n"
            f"{chunk.content[:1500]}"
        )
        try:
            pieces = [
                p
                async for p in llm.stream(
                    PREFIX_PROMPT, [{"role": "user", "content": user}],
                    temperature=0.0, max_tokens=160,
                )
            ]
            prefix = " ".join("".join(pieces).split()).strip()
        except Exception as exc:
            log.warning("Không sinh được bối cảnh cho chunk %d: %s", chunk.chunk_index, exc)
            prefix = ""

        if not prefix:
            failed += 1
        prefixes.append(prefix)

        if on_progress:
            on_progress(i, len(chunks))

    elapsed = time.perf_counter() - started
    log.info(
        "Sinh bối cảnh cho %d đoạn trong %.1fs (%d thất bại)",
        len(chunks), elapsed, failed,
    )
    return ContextualResult(prefixes=prefixes, seconds=elapsed, failed=failed)
