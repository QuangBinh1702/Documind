"""Kiểu dữ liệu và lỗi dùng chung cho mọi trình trích xuất.

Nguyên tắc xuyên suốt: **offset được dựng lên, không đi tìm.**

Mỗi khối văn bản được nối vào `full_text` và vị trí của nó được ghi lại ngay
tại lúc nối. Không có bước nào phải `full_text.find(block_text)` — đó là cách
offset lệch khi cùng một đoạn xuất hiện hai lần trong tài liệu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.text.normalize import is_normalized, normalize
from app.text.quality import TextQuality, assess

__all__ = [
    "BBox",
    "ExtractResult",
    "ExtractionError",
    "PageSpan",
    "TextBlock",
    "TextBuilder",
]


class ExtractionError(Exception):
    """Lỗi trích xuất có mã ổn định và thông báo tiếng Việt.

    `code` dùng để tra chuỗi i18n và thống kê; `message_vi` là bản đã dựng sẵn
    để hiển thị. Tách hai thứ này là yêu cầu của `sources.error_code` /
    `sources.error_message` trong lược đồ (SPEC-v1.md §4.2), và nó tránh việc
    hardcode tiếng Việt ở tầng service.
    """

    def __init__(self, code: str, message_vi: str) -> None:
        super().__init__(f"{code}: {message_vi}")
        self.code = code
        self.message_vi = message_vi


@dataclass(frozen=True, slots=True)
class BBox:
    """Toạ độ trên trang, hệ toạ độ PDF (điểm, gốc ở góc trên bên trái)."""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "page": self.page,
            "x0": round(self.x0, 2),
            "y0": round(self.y0, 2),
            "x1": round(self.x1, 2),
            "y1": round(self.y1, 2),
        }


@dataclass(frozen=True, slots=True)
class PageSpan:
    """Khoảng ký tự mà một trang chiếm trong `full_text`."""

    page: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class TextBlock:
    """Một khối văn bản kèm toạ độ và vị trí trong `full_text`.

    Đây là cầu nối giữa nội dung và toạ độ: chunker dùng `char_start`/`char_end`
    của chunk để tra ngược ra những khối nào chồng lấn, rồi lấy `bbox` của
    chúng làm vùng tô sáng cho trích dẫn (US-015).
    """

    page: int
    char_start: int
    char_end: int
    bbox: BBox | None = None


@dataclass
class ExtractResult:
    full_text: str
    pages: list[PageSpan]
    blocks: list[TextBlock]
    method: str
    quality: TextQuality
    page_count: int

    def page_of(self, pos: int) -> int:
        """Vị trí ký tự nằm ở trang nào."""
        for p in self.pages:
            if p.start <= pos < p.end:
                return p.page
        return self.pages[-1].page if self.pages else 0

    def bboxes_for(self, char_start: int, char_end: int) -> list[BBox]:
        """Các vùng toạ độ chồng lấn với một khoảng ký tự.

        Một chunk thường trải nhiều dòng nên trả về nhiều hộp — đúng như cột
        `bbox` kiểu JSONB trong lược đồ mong đợi.
        """
        return [
            b.bbox
            for b in self.blocks
            if b.bbox is not None and b.char_start < char_end and b.char_end > char_start
        ]


# ── Dựng văn bản kèm offset ────────────────────────────

# Ngăn cách giữa các khối và giữa các trang. Dùng ký tự xuống dòng có hai lý do:
# nó đúng về mặt ngữ nghĩa, và nó chặn việc tổ hợp Unicode xảy ra vắt qua ranh
# giới — nhờ vậy `normalize(a) + "\n" + normalize(b)` luôn bằng
# `normalize(a + "\n" + b)`, tức là bản đồ trang tính ra là chính xác.
BLOCK_SEP = "\n"
PAGE_SEP = "\n"


@dataclass
class TextBuilder:
    """Gom văn bản lại và ghi offset ngay tại lúc gom.

    Cách dùng::

        b = TextBuilder()
        b.start_page(1)
        b.add_block("Điều 5. Phạm vi áp dụng", bbox)
        b.end_page()
        result = b.build(method="pymupdf")
    """

    _parts: list[str] = field(default_factory=list)
    _cursor: int = 0
    _pages: list[PageSpan] = field(default_factory=list)
    _blocks: list[TextBlock] = field(default_factory=list)
    _page_no: int | None = None
    _page_start: int = 0

    def start_page(self, page_no: int) -> None:
        if self._page_no is not None:
            raise RuntimeError("Trang trước chưa được đóng bằng end_page()")
        self._page_no = page_no
        self._page_start = self._cursor

    def add_block(self, raw: str, bbox: BBox | None = None) -> None:
        """Thêm một khối. Khối rỗng bị bỏ qua để không sinh khoảng trắng thừa."""
        if self._page_no is None:
            raise RuntimeError("Phải gọi start_page() trước khi thêm khối")

        text = normalize(raw)
        if not text.strip():
            return

        start = self._cursor
        self._parts.append(text)
        self._cursor += len(text)
        self._blocks.append(
            TextBlock(page=self._page_no, char_start=start, char_end=self._cursor, bbox=bbox)
        )

        self._parts.append(BLOCK_SEP)
        self._cursor += len(BLOCK_SEP)

    def end_page(self) -> None:
        if self._page_no is None:
            raise RuntimeError("Chưa mở trang nào")
        # Trang rỗng vẫn được ghi nhận, để số trang trong bản đồ khớp tài liệu gốc.
        if self._cursor == self._page_start:
            self._parts.append(PAGE_SEP)
            self._cursor += len(PAGE_SEP)
        self._pages.append(PageSpan(self._page_no, self._page_start, self._cursor))
        self._page_no = None

    def build(self, *, method: str) -> ExtractResult:
        if self._page_no is not None:
            raise RuntimeError("Còn trang chưa đóng")

        full_text = "".join(self._parts)

        # Bảo hiểm cho INV-2. Việc nối các mảnh ĐÃ chuẩn hoá về nguyên tắc vẫn
        # cho ra chuỗi chuẩn hoá (nhờ ngăn cách bằng '\n'), nhưng đây là bất
        # biến quan trọng nhất của hệ thống nên đáng kiểm tra thay vì tin tưởng.
        if not is_normalized(full_text):  # pragma: no cover - phòng thủ
            raise ExtractionError(
                "NORMALIZATION_DRIFT",
                "Lỗi nội bộ: văn bản ghép lại không ở dạng chuẩn Unicode.",
            )

        return ExtractResult(
            full_text=full_text,
            pages=list(self._pages),
            blocks=list(self._blocks),
            method=method,
            quality=assess(full_text),
            page_count=len(self._pages),
        )
