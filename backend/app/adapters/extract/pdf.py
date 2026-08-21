"""Trích xuất PDF bằng PyMuPDF — US-007 AC-1, AC-2, AC-5.

Trích theo **khối** chứ không theo cả trang, vì mỗi khối mang theo toạ độ
`bbox`. Đó là thứ mà tính năng tô sáng trích dẫn (US-015) cần, và không lấy
được nếu chỉ gọi ``page.get_text("text")``.
"""

from __future__ import annotations

from pathlib import Path

from app.adapters.extract.base import BBox, ExtractionError, ExtractResult, TextBuilder

__all__ = ["PdfPageText", "extract_pdf"]

METHOD = "pymupdf"

# Chỉ số của phần tử "loại khối" trong tuple mà PyMuPDF trả về: 0 là văn bản,
# 1 là ảnh. Ảnh không có nội dung để lập chỉ mục.
_BLOCK_TYPE_TEXT = 0


class PdfPageText(tuple):
    """Bí danh dễ đọc cho tuple khối của PyMuPDF: (x0, y0, x1, y1, text, no, type)."""


def _open(path: Path):
    try:
        # Tên `fitz` là bí danh cũ, đã bị đánh dấu ngừng hỗ trợ và sẽ biến mất
        # ở một bản phát hành sau. Dùng đúng tên gói ngay để khỏi phải đi tìm
        # trong ngày nó bị gỡ.
        import pymupdf
    except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
        raise ExtractionError(
            "PYMUPDF_MISSING",
            "Thiếu thư viện đọc PDF trên máy chủ.",
        ) from exc

    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ExtractionError(
            "PDF_UNREADABLE",
            "Không mở được tệp PDF — tệp có thể đã hỏng hoặc không đúng định dạng.",
        ) from exc

    if doc.needs_pass:
        doc.close()
        raise ExtractionError(
            "PDF_ENCRYPTED",
            "Tệp PDF có mật khẩu bảo vệ. Hãy gỡ mật khẩu rồi tải lên lại.",
        )

    if doc.page_count == 0:
        doc.close()
        raise ExtractionError(
            "PDF_EMPTY",
            "Tệp PDF không có trang nào.",
        )

    return doc


def extract_pdf(path: Path) -> ExtractResult:
    """Trích văn bản và toạ độ từ lớp text sẵn có của PDF.

    **Không** thực hiện OCR. Nếu PDF là bản scan, kết quả sẽ gần như rỗng và
    `quality` sẽ phản ánh điều đó — tầng gọi dựa vào đó để định tuyến sang OCR
    (US-023, US-056).
    """
    doc = _open(path)
    builder = TextBuilder()

    try:
        for index in range(doc.page_count):
            page = doc[index]
            page_no = index + 1
            builder.start_page(page_no)

            try:
                blocks = page.get_text("blocks")
            except Exception:
                blocks = []

            # Sắp theo thứ tự đọc: trên xuống dưới, trái sang phải. PyMuPDF trả
            # về theo thứ tự nội bộ của tệp, không đảm bảo đúng thứ tự đọc.
            blocks = sorted(blocks, key=lambda b: (round(b[1], 1), round(b[0], 1)))

            for b in blocks:
                if len(b) < 7 or b[6] != _BLOCK_TYPE_TEXT:
                    continue
                x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
                builder.add_block(
                    text,
                    BBox(page=page_no, x0=x0, y0=y0, x1=x1, y1=y1),
                )

            builder.end_page()
    finally:
        doc.close()

    return builder.build(method=METHOD)


def count_chars_per_page(path: Path) -> list[int]:
    """Số ký tự trích được trên mỗi trang — dữ liệu cho US-023 AC-1.

    Rẻ hơn nhiều so với trích xuất đầy đủ, dùng để quyết định có cần OCR không
    trước khi bỏ công xử lý cả tài liệu.
    """
    doc = _open(path)
    try:
        return [len(doc[i].get_text("text").strip()) for i in range(doc.page_count)]
    finally:
        doc.close()
