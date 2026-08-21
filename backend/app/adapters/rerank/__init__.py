"""Chọn bộ xếp hạng lại theo cấu hình."""

from __future__ import annotations

import logging
from functools import lru_cache

from app.adapters.rerank.bge import BgeRerankProvider
from app.adapters.rerank.fake import FakeRerankProvider
from app.ports.rerank import RerankProvider
from app.settings import settings

__all__ = ["BgeRerankProvider", "FakeRerankProvider", "get_rerank_provider"]

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_rerank_provider() -> RerankProvider:
    if settings.rerank_provider == "fake":
        log.warning(
            "Đang dùng bộ xếp hạng lại GIẢ (RERANK_PROVIDER=fake). "
            "Nó chấm theo độ bao phủ từ vựng, không hiểu phủ định hay điều kiện."
        )
        return FakeRerankProvider()
    return BgeRerankProvider()
