"""Trích xuất TXT và Markdown — US-007 AC-4.

Nội dung được nạp nguyên vẹn. Việc duy nhất cần cẩn thận là **đoán mã hoá**:
tệp tiếng Việt cũ có thể là CP1258, hoặc UTF-8 có BOM. Đọc sai mã hoá cho ra
văn bản rác mà không báo lỗi — đúng dạng hỏng im lặng mà US-056 sinh ra để
chặn, nên ở đây ta thử theo thứ tự rồi để bộ chấm chất lượng phán quyết.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.adapters.extract.base import ExtractionError, ExtractResult, TextBuilder
from app.text.normalize import normalize
from app.text.quality import assess

__all__ = ["decode_bytes", "extract_plain"]

METHOD = "plain"

# Một dòng trống ngăn cách hai đoạn. Chỉ dùng được sau khi đã chuẩn hoá xuống
# dòng — xem ghi chú trong extract_plain().
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")

# Thứ tự thử. UTF-8 trước vì nó là chuẩn hiện nay và sai mã hoá sẽ lộ ra ngay
# bằng UnicodeDecodeError thay vì âm thầm cho ra ký tự sai.
_ENCODINGS = ("utf-8-sig", "utf-8", "cp1258", "cp1252", "latin-1")


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """Giải mã bytes thành chuỗi, trả về ``(văn bản, tên mã hoá)``.

    Thử lần lượt các mã hoá; với những mã hoá không bao giờ báo lỗi
    (``latin-1`` giải mã được mọi chuỗi byte), dùng điểm chất lượng để chọn
    kết quả tốt nhất thay vì lấy bừa cái đầu tiên không văng lỗi.
    """
    best: tuple[float, str, str] | None = None

    for enc in _ENCODINGS:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue

        score = assess(text).score
        # UTF-8 giải mã thành công gần như luôn là đáp án đúng: nó có cấu trúc
        # chặt nên chuỗi byte sai rất hiếm khi giải mã lọt.
        if enc.startswith("utf-8"):
            return text, enc
        if best is None or score > best[0]:
            best = (score, text, enc)

    if best is None:
        raise ExtractionError(
            "TEXT_UNDECODABLE",
            "Không xác định được bảng mã của tệp văn bản.",
        )
    return best[1], best[2]


def extract_plain(path: Path) -> ExtractResult:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ExtractionError(
            "FILE_UNREADABLE",
            "Không đọc được tệp trên máy chủ.",
        ) from exc

    if not raw.strip():
        raise ExtractionError(
            "TEXT_EMPTY",
            "Tệp rỗng, không có nội dung để lập chỉ mục.",
        )

    text, encoding = decode_bytes(raw)

    # CHUẨN HOÁ TRƯỚC KHI TÁCH ĐOẠN.
    #
    # Tệp tạo trên Windows dùng CRLF, nên ranh giới đoạn là "\r\n\r\n" chứ
    # không phải "\n\n". Tách trước khi chuẩn hoá thì không khớp mẫu nào và cả
    # tệp thành MỘT khối khổng lồ — hỏng im lặng, chỉ lộ ra ở chất lượng
    # chunking mãi về sau. `normalize` gom mọi kiểu xuống dòng về "\n" nên
    # tách sau đó là an toàn trên mọi hệ điều hành.
    text = normalize(text)

    builder = TextBuilder()
    builder.start_page(1)
    # Ranh giới đoạn = một dòng trống, cho phép có khoảng trắng thừa trên đó.
    for block in _PARAGRAPH_BREAK.split(text):
        builder.add_block(block)
    builder.end_page()

    return builder.build(method=f"{METHOD}:{encoding}")
