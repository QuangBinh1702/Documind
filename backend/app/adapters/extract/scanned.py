"""Trích xuất tài liệu scan bằng nhận dạng chữ — US-024.

Đường này chạy khi `extract_pdf` trả về gần như rỗng và cổng phát hiện scan
(US-023) kết luận tài liệu không có lớp văn bản.

Giữ nguyên hợp đồng của đường có lớp text
------------------------------------------
Kết quả đi qua đúng `TextBuilder` mà PDF thường dùng, nên mọi thứ phía sau —
chunk, offset, `bbox`, bất biến INV-1 — hoạt động y hệt. Tài liệu scan vì thế
cũng tô sáng trích dẫn được (US-015), chứ không phải hạng hai.

Đó là lý do `OcrProvider.read_page` trả về toạ độ thay vì chỉ trả về chữ. Nếu
OCR chỉ trả chuỗi thì tài liệu scan sẽ trích dẫn được về *trang* nhưng không về
*vị trí*, và người dùng phải tự dò trong cả trang.

Sắp dòng theo thứ tự đọc
-------------------------
OCR trả về các dòng theo thứ tự nó phát hiện, không theo thứ tự đọc. Ghép thẳng
thì văn bản lộn xộn, và chunk sinh ra từ đó vô nghĩa. Sắp theo (y, x) như
`extract_pdf` đã làm với khối văn bản — cùng một quy tắc cho cả hai đường.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.adapters.extract.base import BBox, ExtractionError, ExtractResult, TextBuilder
from app.ports.ocr import OcrProvider
from app.settings import settings

__all__ = ["METHOD", "extract_scanned_pdf"]

log = logging.getLogger(__name__)

METHOD = "ocr"

# Dòng nằm trong khoảng này coi như cùng một hàng chữ, dù toạ độ y lệch vài
# điểm. Không gộp thì hai cột chữ cạnh nhau bị đọc xen kẽ thành một mớ.
_CUNG_HANG = 8.0


def extract_scanned_pdf(
    path,
    ocr: OcrProvider,
    on_page: Callable[[int, int], None] | None = None,
) -> ExtractResult:
    """Render từng trang rồi nhận dạng chữ.

    `on_page(da_xong, tong)` được gọi sau mỗi trang. OCR là bước lâu nhất của cả
    đường ống — hàng chục giây mỗi trang trên CPU — nên không báo tiến độ ở đây
    thì người dùng nhìn một màn hình đứng yên hàng chục phút (US-022 AC-3).
    """
    import pymupdf

    doc = pymupdf.open(path)
    builder = TextBuilder()
    tong_giay = 0.0
    tong_dong = 0
    thap = 0

    # Ảnh render ở `OCR_DPI`; trang PDF đo bằng điểm (72 dpi). Tỉ lệ giữa hai hệ
    # là thứ đưa toạ độ OCR về đúng hệ toạ độ trang.
    scale = settings.ocr_dpi / 72.0

    try:
        for i in range(doc.page_count):
            page_no = i + 1
            builder.start_page(page_no)

            pix = doc[i].get_pixmap(dpi=settings.ocr_dpi)
            ket_qua = ocr.read_page(pix.tobytes("png"), page_no, scale)
            tong_giay += ket_qua.seconds

            for line in sorted(ket_qua.lines, key=_thu_tu_doc):
                if not line.text.strip():
                    continue
                tong_dong += 1
                if line.confidence < settings.ocr_min_confidence:
                    thap += 1
                builder.add_block(
                    line.text,
                    BBox(page=page_no, x0=line.x0, y0=line.y0, x1=line.x1, y1=line.y1),
                )

            builder.end_page()
            log.info(
                "OCR trang %d/%d: %d dòng, tin cậy %.2f, %.1fs",
                page_no, doc.page_count, len(ket_qua.lines),
                ket_qua.confidence, ket_qua.seconds,
            )
            if on_page:
                on_page(page_no, doc.page_count)
    finally:
        doc.close()

    ket = builder.build(method=f"{METHOD}:{ocr.name}")
    if not ket.full_text.strip():
        raise ExtractionError(
            "OCR_EMPTY",
            "Nhận dạng chữ không đọc được nội dung nào từ tệp này. "
            "Ảnh có thể quá mờ, quá nghiêng, hoặc trang trắng.",
        )

    log.info(
        "OCR xong %s: %d dòng, %d dòng dưới ngưỡng tin cậy, %.1fs",
        getattr(path, "name", path), tong_dong, thap, tong_giay,
    )
    return ket


def _thu_tu_doc(line) -> tuple[float, float]:
    """Trên xuống dưới, trái sang phải — cùng quy tắc với `extract_pdf`.

    Làm tròn `y` về từng nhóm `_CUNG_HANG` điểm trước khi so: chữ trên cùng một
    hàng hiếm khi có `y` bằng nhau tuyệt đối, và so `y` thô sẽ xé một hàng thành
    nhiều hàng theo thứ tự lộn xộn.
    """
    return (round(line.y0 / _CUNG_HANG), line.x0)
