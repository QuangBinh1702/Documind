"""Chọn adapter nhúng theo cấu hình.

Tầng nghiệp vụ gọi `get_embedding_provider()` và không biết mô hình nào đứng
sau — đó là điều kiện để ablation US-046 chạy được mà không sửa code.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.adapters.embedding.bge_m3 import BgeM3EmbeddingProvider
from app.adapters.embedding.fake import FakeEmbeddingProvider
from app.ports.embedding import EmbeddingProvider
from app.settings import settings

__all__ = [
    "BgeM3EmbeddingProvider",
    "FakeEmbeddingProvider",
    "get_embedding_provider",
]

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """Trả về adapter theo `EMBEDDING_PROVIDER`.

    Được nhớ kết quả (`lru_cache`) vì nạp mô hình tốn hàng chục giây và hàng GB
    VRAM — mỗi tiến trình chỉ nên nạp một lần.
    """
    if settings.embedding_provider == "fake":
        # Cảnh báo to, mỗi tiến trình một lần. Chạy nhầm bản giả rồi đưa số vào
        # báo cáo là lỗi im lặng và rất tốn kém.
        log.warning(
            "Đang dùng adapter nhúng GIẢ (EMBEDDING_PROVIDER=fake). "
            "Nó chỉ nắm trùng lặp từ vựng, KHÔNG nắm ngữ nghĩa. "
            "Mọi số liệu chất lượng đo bằng nó đều không dùng được cho báo cáo."
        )
        return FakeEmbeddingProvider(dim=settings.embedding_dim)

    return BgeM3EmbeddingProvider()
