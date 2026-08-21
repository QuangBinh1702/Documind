"""Điều phối trích xuất theo loại tệp.

Tầng service gọi `extract()` và không cần biết tệp là PDF, DOCX hay TXT — đúng
tinh thần ports & adapters ở `SPEC-v1.md` §3.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.adapters.extract.base import (
    BBox,
    ExtractionError,
    ExtractResult,
    PageSpan,
    TextBlock,
    TextBuilder,
)
from app.adapters.extract.docx import extract_docx
from app.adapters.extract.pdf import count_chars_per_page, extract_pdf
from app.adapters.extract.plain import decode_bytes, extract_plain

__all__ = [
    "BBox",
    "ExtractResult",
    "ExtractionError",
    "PageSpan",
    "TextBlock",
    "TextBuilder",
    "count_chars_per_page",
    "decode_bytes",
    "extract",
    "extract_docx",
    "extract_pdf",
    "extract_plain",
]

_BY_KIND: dict[str, Callable[[Path], ExtractResult]] = {
    "pdf": extract_pdf,
    "docx": extract_docx,
    "txt": extract_plain,
    "md": extract_plain,
}


def extract(path: Path, kind: str) -> ExtractResult:
    """Trích xuất theo loại nguồn đã ghi trong `sources.kind`.

    Ảnh (`image`) không đi qua đây — chúng thuộc đường OCR (US-024).
    """
    handler = _BY_KIND.get(kind)
    if handler is None:
        raise ExtractionError(
            "KIND_UNSUPPORTED",
            f"Chưa hỗ trợ trích xuất trực tiếp cho loại nguồn '{kind}'.",
        )
    return handler(path)
