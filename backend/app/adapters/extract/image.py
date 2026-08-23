"""Trích xuất chữ từ ảnh — US-025, US-026.

Ảnh chụp màn hình, ảnh chụp trang sách, ảnh chụp bảng biểu. Người dùng dán một
tấm ảnh vào và mong hỏi được về nội dung trong đó.

Vì sao không dùng lại `extract_scanned_pdf`
--------------------------------------------
Đường PDF scan render từng trang bằng PyMuPDF rồi mới OCR. Ảnh thì đã là ảnh
rồi — không có trang nào để render, và không có hệ toạ độ điểm để quy đổi về.

Ở đây `scale = 1.0`: toạ độ OCR trả về là **pixel của chính tấm ảnh**, và đó
cũng là hệ toạ độ mà giao diện dùng để tô sáng khi hiển thị lại ảnh. Không có
bước quy đổi nào, nên cũng không có chỗ nào để sai.

Tiền xử lý (US-026)
--------------------
OCR đọc ảnh chụp bằng điện thoại kém hơn hẳn ảnh quét. Ba phép biến đổi rẻ giúp
được nhiều nhất, và tất cả đều **không phá thông tin**:

- **Xoay theo EXIF** — ảnh điện thoại rất hay nằm ngang trong dữ liệu nhưng hiển
  thị đúng chiều nhờ thẻ EXIF. OCR đọc dữ liệu thô nên nó thấy ảnh nằm ngang.
- **Phóng to ảnh nhỏ** — mô hình nhận dạng cần chữ cao khoảng 32 px. Ảnh chụp
  màn hình một đoạn chữ nhỏ thường dưới ngưỡng đó, và phóng to bằng nội suy
  Lanczos cho kết quả tốt hơn hẳn để nguyên.
- **Thu nhỏ ảnh quá lớn** — ảnh 12 MP không đọc tốt hơn ảnh 4 MP, chỉ chậm hơn
  vài lần.

Cố tình **không** nhị phân hoá hay khử nhiễu: PP-OCRv5 được huấn luyện trên ảnh
màu tự nhiên, và ngưỡng hoá thủ công thường làm nó tệ đi chứ không tốt lên.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.adapters.extract.base import BBox, ExtractionError, ExtractResult, TextBuilder
from app.ports.ocr import OcrProvider
from app.settings import settings

__all__ = ["METHOD", "extract_image", "tien_xu_ly"]

log = logging.getLogger(__name__)

METHOD = "image-ocr"

# Cùng dung sai gộp hàng với đường PDF scan, nhưng tính bằng pixel: ở đây một
# đơn vị là một pixel ảnh chứ không phải một điểm trang.
_CUNG_HANG = 12.0


def tien_xu_ly(img):
    """Chuẩn hoá một ảnh trước khi đưa vào OCR. Nhận và trả `PIL.Image`."""
    from PIL import ImageOps

    # Áp thẻ xoay EXIF rồi xoá nó đi, để không bị xoay lần thứ hai về sau.
    img = ImageOps.exif_transpose(img)

    # Ảnh có kênh trong suốt: nền trong suốt bị coi là đen khi bỏ kênh alpha,
    # và chữ đen trên nền đen thì không đọc được gì. Ghép lên nền trắng trước.
    if img.mode in ("RGBA", "LA", "P"):
        from PIL import Image

        img = img.convert("RGBA")
        nen = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(nen, img)
    img = img.convert("RGB")

    canh_dai = max(img.size)
    if canh_dai < settings.image_min_side:
        ti_le = settings.image_min_side / canh_dai
        img = img.resize(
            (round(img.width * ti_le), round(img.height * ti_le)),
            _lanczos(),
        )
        log.info("Phóng to ảnh ×%.2f để chữ đủ cao cho OCR", ti_le)
    elif canh_dai > settings.image_max_side:
        ti_le = settings.image_max_side / canh_dai
        img = img.resize(
            (round(img.width * ti_le), round(img.height * ti_le)),
            _lanczos(),
        )
        log.info("Thu nhỏ ảnh ×%.2f — kích thước lớn hơn không giúp OCR", ti_le)

    return img


def _lanczos():
    from PIL import Image

    return Image.Resampling.LANCZOS


def extract_image(path: Path, ocr: OcrProvider) -> ExtractResult:
    """Đọc chữ trong một tấm ảnh. Kết quả là tài liệu **một trang**."""
    import io

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
        raise ExtractionError(
            "PILLOW_MISSING", "Thiếu thư viện Pillow để đọc ảnh."
        ) from exc

    try:
        with Image.open(path) as goc:
            img = tien_xu_ly(goc)
    except UnidentifiedImageError as exc:
        raise ExtractionError(
            "IMAGE_UNREADABLE",
            "Không mở được tệp ảnh này. Tệp có thể hỏng hoặc không đúng định dạng.",
        ) from exc

    dem = io.BytesIO()
    img.save(dem, format="PNG")

    ket_qua = ocr.read_page(dem.getvalue(), page=1, scale=1.0)

    builder = TextBuilder()
    builder.start_page(1)
    thap = 0
    for line in sorted(ket_qua.lines, key=_thu_tu_doc):
        if not line.text.strip():
            continue
        if line.confidence < settings.ocr_min_confidence:
            thap += 1
        builder.add_block(
            line.text,
            BBox(page=1, x0=line.x0, y0=line.y0, x1=line.x1, y1=line.y1),
        )
    builder.end_page()

    ket = builder.build(method=f"{METHOD}:{ocr.name}")
    if not ket.full_text.strip():
        raise ExtractionError(
            "OCR_EMPTY",
            "Không đọc được chữ nào trong ảnh này. Ảnh có thể không chứa chữ, "
            "quá mờ, hoặc chữ quá nhỏ.",
        )

    log.info(
        "OCR ảnh %s: %d dòng (%d dưới ngưỡng tin cậy), tin cậy %.2f, %.1fs",
        path.name, len(ket_qua.lines), thap, ket_qua.confidence, ket_qua.seconds,
    )
    return ket


def _thu_tu_doc(line) -> tuple[float, float]:
    return (round(line.y0 / _CUNG_HANG), line.x0)
