"""Nhận dạng chữ bằng PaddleOCR — engine chính, US-024.

Đây là engine mà `SPEC.md` chỉ định, và lý do quan trọng nhất là **tiếng Việt**:
PaddleOCR có mô hình nhận dạng riêng cho chữ Latin có dấu, tải về tự động theo
`lang`. Không có nó thì đầu ra mất sạch dấu, và với văn bản pháp quy tiếng Việt
thì mất dấu là mất nghĩa — *"hoc"* có thể là **học**, **hoặc**, hay **hóc**.

Nạp lười và giữ lại
-------------------
Mô hình nặng vài trăm MB và mất vài giây để dựng. Nạp ở lần dùng đầu tiên rồi
giữ nguyên: một tài liệu scan ba mươi trang mà dựng lại engine cho mỗi trang thì
phần lớn thời gian là dựng engine chứ không phải đọc chữ.

`unload()` có ở đây vì US-057: trên máy đích 16 GB, embedding, rerank, LLM và
OCR không cùng nằm trên GPU được, nên phải nạp và nhả luân phiên.
"""

from __future__ import annotations

import logging
import time

from app.ports.ocr import OcrLine, OcrPage
from app.settings import settings

__all__ = ["PaddleOcrProvider"]

log = logging.getLogger(__name__)


class PaddleOcrProvider:
    name = "paddleocr"

    def __init__(self, lang: str | None = None, device: str | None = None) -> None:
        self.lang = lang or settings.ocr_lang
        self.device = device or settings.ocr_dev
        self._engine = None

    def _load(self):
        if self._engine is not None:
            return self._engine

        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise RuntimeError(
                'Thiếu paddleocr. Cài bằng: pip install -e ".[ml]"\n'
                "Hoặc đặt OCR_ENGINE=rapid để dùng đường ONNX nhẹ hơn."
            ) from exc

        log.info("Nạp PaddleOCR (lang=%s, device=%s) …", self.lang, self.device)
        self._engine = PaddleOCR(
            lang=self.lang,
            device=self.device,
            # Ba bước phụ của PP-OCR. Tắt hết vì tài liệu ở đây là văn bản A4
            # quét thẳng, không phải ảnh chụp nghiêng: bật chúng tốn thêm thời
            # gian mỗi trang mà gần như không đổi kết quả. Ảnh chụp bằng điện
            # thoại (US-025) là chuyện khác, và thuộc về US-026.
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        return self._engine

    def read_page(self, image_png: bytes, page: int, scale: float) -> OcrPage:
        import numpy as np

        engine = self._load()
        started = time.perf_counter()

        # PaddleOCR nhận mảng numpy hoặc đường dẫn, không nhận bytes PNG.
        import cv2

        anh = cv2.imdecode(np.frombuffer(image_png, np.uint8), cv2.IMREAD_COLOR)
        ket_qua = engine.predict(anh)
        elapsed = time.perf_counter() - started

        lines: list[OcrLine] = []
        for trang in ket_qua or []:
            texts = trang.get("rec_texts") or []
            scores = trang.get("rec_scores") or []
            boxes = trang.get("rec_polys") or trang.get("dt_polys") or []
            for text, score, box in zip(texts, scores, boxes, strict=False):
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                lines.append(
                    OcrLine(
                        text=str(text),
                        confidence=float(score),
                        # Về hệ toạ độ trang PDF — cùng hệ với `bbox` của
                        # PyMuPDF, nếu không thì tô sáng lệch đúng bằng tỉ lệ dpi.
                        x0=min(xs) / scale, y0=min(ys) / scale,
                        x1=max(xs) / scale, y1=max(ys) / scale,
                    )
                )

        return OcrPage(page=page, lines=lines, seconds=elapsed)

    def unload(self) -> None:
        """Nhả mô hình — chính sách nạp/giải phóng của US-057."""
        self._engine = None
