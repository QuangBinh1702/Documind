"""Chia tài liệu thành đoạn tri thức — US-008.

Bất biến INV-1 (`SPEC-v1.md` §1.3)::

    full_text[chunk.char_start : chunk.char_end] == chunk.content

Toàn bộ tính năng trích dẫn đứng trên đẳng thức này. `SPEC.md` §J.6 gọi đây là
điều thứ nhất trong ba điều quyết định thành bại của đồ án, vì nếu offset sai
thì lỗi chỉ lộ ra ở M2 khi bấm chip trích dẫn và tô sáng nhảy sai chỗ — lúc đó
sửa gốc đã quá muộn.

Cách giữ bất biến
-----------------
`content` **không bao giờ** được ghép từ các mảnh rồi gán vào chunk. Nó luôn
được **cắt ra từ** `full_text` bằng chính cặp offset đã tính. Nhờ vậy hai vế
của đẳng thức đúng theo cách xây dựng, không phải theo may mắn::

    span = _trim(full_text, start, end)
    content = full_text[span.start : span.end]   # <- một nguồn duy nhất

Thứ tự cắt
----------
1. Cắt theo **ranh giới tiêu đề** trước (US-008 AC-3) — cả tiêu đề Markdown và
   cấu trúc văn bản pháp quy (Chương, Điều, Mục, Phụ lục).
2. Trong mỗi phần, gom **câu** cho tới khi đầy hạn mức token (US-008 AC-2).
3. Câu dài hơn một chunk thì cắt cứng theo ký tự, vẫn giữ offset đúng.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise

from app.adapters.extract.base import BBox, ExtractResult
from app.text.segment import Span, split_sentences

__all__ = [
    "Chunk",
    "TokenCounter",
    "chunk_document",
    "chunk_text",
    "estimate_tokens",
]

TokenCounter = Callable[[str], int]


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    token_count: int
    page_no: int | None = None
    heading_path: str | None = None
    bbox: list[BBox] = field(default_factory=list)


# ── Đếm token ──────────────────────────────────────────

# Số ký tự trung bình cho một token với bộ tách SentencePiece đa ngữ (họ
# XLM-R, mà bge-m3 dùng) trên văn bản tiếng Việt. Lấy giá trị THẤP hơn thực tế
# để ước lượng thừa số token, tức là chunk nhỏ hơn mong muốn một chút — an
# toàn hơn nhiều so với chunk tràn quá giới hạn ngữ cảnh của mô hình.
_CHARS_PER_TOKEN = 2.8


def estimate_tokens(text: str) -> int:
    """Ước lượng nhanh số token, không cần nạp mô hình.

    Dùng khi lập chỉ mục để quyết định chỗ cắt. Đây là **ước lượng**, không
    phải số đo: bộ đếm thật cần nạp tokenizer của bge-m3, quá nặng cho một bước
    chạy trên mọi tài liệu.

    Muốn đếm chính xác thì truyền `count_tokens` khác vào `chunk_document()` —
    tham số này tồn tại chính vì lý do đó.
    """
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


# ── Nhận diện tiêu đề ──────────────────────────────────

_MD_HEADING = re.compile(r"^(#{1,6})\s+(\S.*)$")

# Cấu trúc văn bản pháp quy Việt Nam, xếp theo cấp từ lớn đến nhỏ.
# US-008 AC-3 mở rộng cho miền tài liệu của đồ án.
_LEGAL_HEADING = re.compile(
    r"^\s*(PHẦN|Phần|CHƯƠNG|Chương|MỤC|Mục|Điều|PHỤ LỤC|Phụ lục)\s+"
    r"([IVXLCDM]+|\d+)\b\.?\s*(.*)$"
)

_LEGAL_LEVEL = {
    "phần": 1,
    "chương": 2,
    "mục": 3,
    "điều": 4,
    "phụ lục": 1,
}

# Đánh số thập phân: "2.13 Tên mục", "2.1. Tên mục", "3.4.1 — Tên mục".
# Cấp = số thành phần, nên 2.13 nằm trên 2.13.1 mà không cần bảng tra.
#
# Ràng buộc chặt để không nuốt nhầm số liệu trong văn xuôi hay trong bảng: phải
# đứng đầu dòng, và phần chữ theo sau phải bắt đầu bằng **chữ HOA**.
#
# Chỉ đòi "bắt đầu bằng chữ cái" là không đủ — "2.5 kg mỗi ngày" và "1.2 triệu
# đồng" đều qua được. Chữ hoa mới là thứ tách được, vì tiêu đề tiếng Việt viết
# hoa chữ đầu còn số liệu giữa câu thì không. Đánh đổi: một tiêu đề viết thường
# hoàn toàn sẽ bị bỏ sót — chấp nhận được, vì bỏ sót chỉ mất một nhãn, còn nhận
# nhầm là dán nhãn SAI lên trích dẫn.
_DECIMAL_HEADING = re.compile(r"^(\d+(?:\.\d+){1,3})\s*[.\-—:]?\s+(\S.*)$")

# "Đề tài 2.10: …", "Bài 3. …", "Câu 5 …". Miền tài liệu của đồ án gồm cả đề
# cương môn học và danh sách đề tài, không chỉ văn bản pháp quy.
_ITEM_HEADING = re.compile(
    r"^(Đề\s*tài|ĐỀ\s*TÀI|Bài|BÀI|Câu|CÂU|Nhiệm\s*vụ|NHIỆM\s*VỤ)\s+"
    r"(\d+(?:\.\d+)*)\s*[.\-—:]?\s*(.*)$"
)
_ITEM_LEVEL = 4

# Dòng dài không phải tiêu đề mà là một câu bắt đầu bằng số. Giới hạn này rẻ và
# loại được gần hết ca nhập nhằng còn lại.
_MAX_HEADING_CHARS = 200

# Một tiêu đề chỉ được coi là "chỗ chứa" của đoạn nằm trong khoảng này. Xa hơn
# thì tài liệu có cấu trúc mà bộ nhận diện không thấy, và gán bừa tiêu đề gần
# nhất phía trước là **nói sai**, không phải nói thiếu.
#
# Đã gặp thật: một tài liệu 85 trang chỉ lộ ra đúng một tiêu đề, và 110/119 đoạn
# nhận cùng nhãn đó — kể cả đoạn cách nó ba mươi trang. Trên chip trích dẫn,
# một nhãn sai còn tệ hơn không có nhãn.
_MAX_HEADING_DISTANCE = 20_000


@dataclass(frozen=True, slots=True)
class _Heading:
    level: int
    title: str
    pos: int


def _find_headings(text: str) -> list[_Heading]:
    """Tìm mọi tiêu đề kèm vị trí ký tự của dòng chứa nó."""
    out: list[_Heading] = []
    pos = 0

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and len(stripped) <= _MAX_HEADING_CHARS:
            found = _match_heading(stripped, pos)
            if found is not None:
                out.append(found)

        pos += len(line) + 1  # +1 cho ký tự '\n' đã bị split ăn mất

    return out


def _match_heading(line: str, pos: int) -> _Heading | None:
    """Nhận diện một dòng tiêu đề. Thứ tự thử là từ chắc chắn nhất trở xuống."""
    md = _MD_HEADING.match(line)
    if md:
        return _Heading(len(md.group(1)), md.group(2).strip(), pos)

    legal = _LEGAL_HEADING.match(line)
    if legal:
        keyword = legal.group(1).lower()
        title = f"{legal.group(1)} {legal.group(2)}"
        if legal.group(3).strip():
            title = f"{title}. {legal.group(3).strip()}"
        return _Heading(_LEGAL_LEVEL.get(keyword, 4), title, pos)

    item = _ITEM_HEADING.match(line)
    if item:
        title = f"{item.group(1)} {item.group(2)}"
        if item.group(3).strip():
            title = f"{title}: {item.group(3).strip()}"
        return _Heading(_ITEM_LEVEL, title, pos)

    dec = _DECIMAL_HEADING.match(line)
    if dec:
        title = dec.group(2).strip()
        if title[:1].isupper():
            number = dec.group(1)
            return _Heading(number.count(".") + 1, f"{number} {title}", pos)

    return None


def _heading_path_at(headings: list[_Heading], pos: int) -> str | None:
    """Chuỗi tiêu đề tổ tiên tại một vị trí, ví dụ "Chương 3 > Điều 12".

    Trả về ``None`` khi tiêu đề gần nhất nằm quá xa: xem `_MAX_HEADING_DISTANCE`.
    """
    stack: list[_Heading] = []
    for h in headings:
        if h.pos > pos:
            break
        while stack and stack[-1].level >= h.level:
            stack.pop()
        stack.append(h)

    if not stack or pos - stack[-1].pos > _MAX_HEADING_DISTANCE:
        return None
    return " > ".join(h.title for h in stack)


# ── Cắt chunk ──────────────────────────────────────────


def _trim(text: str, start: int, end: int) -> Span:
    """Thu hẹp khoảng để bỏ khoảng trắng ở hai đầu.

    Thu hẹp **khoảng** rồi mới cắt, chứ không cắt rồi mới `strip()`. Nếu strip
    chuỗi sau khi cắt thì `content` không còn khớp `full_text[start:end]` và
    INV-1 gãy ngay lập tức.
    """
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return Span(start, end)


def _split_long_span(
    text: str, span: Span, max_tokens: int, count_tokens: TokenCounter
) -> list[Span]:
    """Cắt cứng một khoảng dài hơn hạn mức, ưu tiên ranh giới khoảng trắng."""
    if count_tokens(text[span.start : span.end]) <= max_tokens:
        return [span]

    approx_chars = max(200, int(max_tokens * _CHARS_PER_TOKEN))
    out: list[Span] = []
    pos = span.start

    while pos < span.end:
        stop = min(pos + approx_chars, span.end)
        if stop < span.end:
            # Lùi về khoảng trắng gần nhất để không cắt giữa từ.
            window = text.rfind(" ", pos + approx_chars // 2, stop)
            if window > pos:
                stop = window
        out.append(Span(pos, stop))
        pos = stop

    return out


def chunk_text(
    full_text: str,
    *,
    max_tokens: int = 768,
    overlap_ratio: float = 0.15,
    respect_headings: bool = True,
    count_tokens: TokenCounter = estimate_tokens,
) -> list[Chunk]:
    """Chia văn bản thành chunk, giữ nguyên INV-1.

    Không phụ thuộc `ExtractResult`, nên test được với chuỗi thuần.
    `chunk_document()` bọc hàm này để gắn thêm `page_no` và `bbox`.
    """
    if not full_text.strip():
        return []

    headings = _find_headings(full_text) if respect_headings else []
    boundaries = sorted({0, *(h.pos for h in headings), len(full_text)})
    sections = [
        Span(a, b) for a, b in pairwise(boundaries) if a < b
    ]

    overlap_tokens = int(max_tokens * overlap_ratio)
    chunks: list[Chunk] = []
    index = 0

    for section in sections:
        body = full_text[section.start : section.end]
        # Đưa offset của câu về hệ toạ độ của TOÀN văn bản ngay lập tức, để
        # không còn hai hệ toạ độ cùng tồn tại trong phần còn lại của hàm.
        units: list[Span] = []
        for s in split_sentences(body):
            absolute = Span(section.start + s.start, section.start + s.end)
            units.extend(_split_long_span(full_text, absolute, max_tokens, count_tokens))

        buffer: list[Span] = []
        buffer_tokens = 0

        def flush(buf: list[Span]) -> None:
            nonlocal index
            if not buf:
                return
            span = _trim(full_text, buf[0].start, buf[-1].end)
            if span.start >= span.end:
                return
            content = full_text[span.start : span.end]  # nguồn duy nhất của content
            chunks.append(
                Chunk(
                    chunk_index=index,
                    content=content,
                    char_start=span.start,
                    char_end=span.end,
                    token_count=count_tokens(content),
                    heading_path=_heading_path_at(headings, span.start),
                )
            )
            index += 1

        for unit in units:
            unit_tokens = count_tokens(full_text[unit.start : unit.end])

            if buffer and buffer_tokens + unit_tokens > max_tokens:
                flush(buffer)

                # Chồng lặp: giữ lại các câu cuối cho tới khi đủ hạn mức.
                carried: list[Span] = []
                carried_tokens = 0
                for prev in reversed(buffer):
                    t = count_tokens(full_text[prev.start : prev.end])
                    if carried_tokens + t > overlap_tokens:
                        break
                    carried.insert(0, prev)
                    carried_tokens += t
                buffer = carried
                buffer_tokens = carried_tokens

            buffer.append(unit)
            buffer_tokens += unit_tokens

        flush(buffer)

    return chunks


def chunk_document(
    result: ExtractResult,
    *,
    max_tokens: int = 768,
    overlap_ratio: float = 0.15,
    respect_headings: bool = True,
    count_tokens: TokenCounter = estimate_tokens,
) -> list[Chunk]:
    """Chia một tài liệu đã trích xuất, gắn thêm số trang và toạ độ.

    `page_no` lấy theo vị trí **bắt đầu** của chunk. Một chunk trải qua ranh
    giới trang vẫn được ghi là thuộc trang mở đầu — đó là trang mà người dùng
    sẽ được đưa tới khi bấm trích dẫn, và cũng là nơi đoạn văn bắt đầu.
    """
    base = chunk_text(
        result.full_text,
        max_tokens=max_tokens,
        overlap_ratio=overlap_ratio,
        respect_headings=respect_headings,
        count_tokens=count_tokens,
    )

    return [
        Chunk(
            chunk_index=c.chunk_index,
            content=c.content,
            char_start=c.char_start,
            char_end=c.char_end,
            token_count=c.token_count,
            page_no=result.page_of(c.char_start),
            heading_path=c.heading_path,
            bbox=result.bboxes_for(c.char_start, c.char_end),
        )
        for c in base
    ]
