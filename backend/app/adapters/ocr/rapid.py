"""Nhận dạng chữ bằng RapidOCR — đường ONNX, chạy được trên CPU.

Chạy chính họ mô hình PP-OCRv5 mà `SPEC.md` US-024 chỉ định, nhưng qua ONNX
Runtime nên nhẹ hơn hẳn: vài chục MB thay vì vài trăm, và không kéo theo
PaddlePaddle — thứ mà bản 3.0 hiện không nạp được chính mô hình do PaddleOCR
tải về (`ValueError: Type of attribute: strides is not right`).

Chọn mô hình nhận dạng: đo, không đoán
---------------------------------------
Đây là chỗ quyết định đầu ra dùng được hay không, và cả ba lựa chọn đã được thử
trên cùng một trang của Thông tư 08/2021 bản scan:

============  ==========================================  =========
Mô hình       Đọc ra                                      Kết luận
============  ==========================================  =========
CH (mặc định) ``Thong tu s6 10/2018 ... ngay 30 thang 3``  Mất **sạch** dấu
LATIN         ``Thông tur só 10/2018 ... ngày 30 tháng 3`` Có dấu, sai ư/ơ/ă/đ
============  ==========================================  =========

Mô hình mặc định tự báo độ tin cậy 0.98 cho một kết quả không còn dấu nào — tức
là **không tin được vào điểm tin cậy của engine** để phát hiện ca này. Cổng chất
lượng US-056 mới là thứ bắt được, vì nó đo tỉ lệ dấu trên văn bản trông như
tiếng Việt.

LATIN là lựa chọn tốt nhất trong những gì có sẵn, nhưng **vẫn chưa đủ cho tiếng
Việt**: nó không có ư, ơ, ă, đ trong bộ ký tự, nên *"thư"* thành *"thur"*,
*"năm"* thành *"nm"*, *"đại học"* thành *"dai hoc"*. Đây là hạn chế phải nêu ở
Chương 5 chứ không phải giấu đi — và là lý do `OCR_REC_LANG` tồn tại: có mô hình
tiếng Việt riêng thì đổi một dòng cấu hình.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

from app.ports.ocr import OcrLine, OcrPage
from app.settings import settings

__all__ = ["RapidOcrProvider"]

log = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def _engine(lang: str):
    try:
        from rapidocr import EngineType, LangRec, ModelType, OCRVersion, RapidOCR
    except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
        raise RuntimeError(
            "Thiếu rapidocr. Cài bằng: pip install rapidocr"
        ) from exc

    try:
        lang_rec = LangRec[lang.upper()]
    except KeyError as exc:
        co = ", ".join(x.name.lower() for x in LangRec)
        raise RuntimeError(
            f"OCR_REC_LANG='{lang}' không có. Chọn một trong: {co}"
        ) from exc

    log.info("Nạp RapidOCR (mô hình nhận dạng: %s) …", lang_rec.name)
    return RapidOCR(
        params={
            "Rec.lang_type": lang_rec,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.engine_type": EngineType.ONNXRUNTIME,
        }
    )


class RapidOcrProvider:
    name = "rapidocr-ppocrv5"

    def read_page(self, image_png: bytes, page: int, scale: float) -> OcrPage:
        engine = _engine(settings.ocr_rec_lang)

        started = time.perf_counter()
        ket_qua = engine(image_png)
        elapsed = time.perf_counter() - started

        lines: list[OcrLine] = []
        boxes = ket_qua.boxes if ket_qua.boxes is not None else []
        for box, text, conf in zip(
            boxes, ket_qua.txts or [], ket_qua.scores or [], strict=False
        ):
            # `box` là bốn đỉnh của tứ giác bao quanh dòng chữ. Trang chụp lệch
            # cho ra tứ giác không vuông góc, nên lấy hộp bao ngoài thay vì giả
            # định bốn góc vuông.
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            lines.append(
                OcrLine(
                    text=str(text),
                    confidence=float(conf),
                    # Chia cho `scale` để về hệ toạ độ trang PDF — cùng hệ với
                    # `bbox` của PyMuPDF, nếu không thì tô sáng lệch đúng bằng
                    # tỉ lệ dpi.
                    x0=min(xs) / scale, y0=min(ys) / scale,
                    x1=max(xs) / scale, y1=max(ys) / scale,
                )
            )

        return OcrPage(page=page, lines=lines, seconds=elapsed)

    def unload(self) -> None:
        _engine.cache_clear()
