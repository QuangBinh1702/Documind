"""Chọn engine nhận dạng chữ theo cấu hình — US-024, US-048.

Đổi engine là đổi một dòng `.env`, không sửa đường xử lý. Đó là điều kiện để
US-048 so được ba engine trên cùng bộ mẫu.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.ports.ocr import OcrProvider
from app.settings import settings

__all__ = ["get_ocr_provider"]

log = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def _tao(engine: str) -> OcrProvider:
    if engine == "rapid":
        from app.adapters.ocr.rapid import RapidOcrProvider

        return RapidOcrProvider()

    from app.adapters.ocr.paddle import PaddleOcrProvider

    return PaddleOcrProvider()


def get_ocr_provider() -> OcrProvider:
    return _tao(settings.ocr_engine)
