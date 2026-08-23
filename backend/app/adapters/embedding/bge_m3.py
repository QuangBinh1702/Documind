"""Adapter nhúng thật bằng `BAAI/bge-m3`.

Nạp mô hình **lười**: chỉ khi lần nhúng đầu tiên được gọi. Nhờ vậy import
module này không kéo theo 2.2 GB, và test nào không chạm tới nó thì không phải
trả giá.

Trên máy phát triển đặt `DEVICE=cpu` — chạy được nhưng chậm khoảng 10–20 lần.
Mọi số đo hiệu năng chỉ có nghĩa trên máy đích (`SPEC-v1.md` §10.0).
"""

from __future__ import annotations

import logging

from app.settings import settings

__all__ = ["BgeM3EmbeddingProvider"]

log = logging.getLogger(__name__)


class BgeM3EmbeddingProvider:
    """Nhúng bằng bge-m3, trả về vector dày đã chuẩn hoá L2."""

    def __init__(
        self,
        model_name: str | None = None,
        revision: str | None = None,
        device: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.model_name = model_name or settings.embedding_model
        self.revision = revision or settings.embedding_revision
        self.device = device or settings.embed_device
        self.batch_size = batch_size or settings.embedding_batch_size
        self.dim = settings.embedding_dim
        self._model = None

    @property
    def name(self) -> str:
        """Ghi cả revision vào tên để metadata lần chạy tái lập được."""
        return f"{self.model_name}@{self.revision or 'unpinned'}"

    @property
    def da_san_sang(self) -> bool:
        """Trọng số đã nằm trong bộ nhớ chưa.

        Chỗ gọi dùng nó để biết lượt `warm()` sắp tới là tức thời hay là một
        lượt tải về vài GB — và nói cho người dùng biết trước điều đó.
        """
        return self._model is not None

    def warm(self) -> None:
        """Nạp mô hình ngay bây giờ thay vì đợi lượt nhúng đầu tiên.

        Không có hàm này thì việc tải trọng số xảy ra lặng lẽ bên trong
        `embed_documents`, tức là **sau khi** thanh tiến trình đã nhảy lên 85%.
        Người dùng thấy 85% đứng im hàng phút và kết luận hệ thống treo.
        """
        self._load()

    def _load(self):
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise RuntimeError(
                "Thiếu sentence-transformers. Cài bằng: pip install -e \".[ml]\"\n"
                "Trên máy phát triển có thể đặt EMBEDDING_PROVIDER=fake để bỏ qua."
            ) from exc

        log.info("Nạp %s trên %s …", self.model_name, self.device)
        model = SentenceTransformer(
            self.model_name, revision=self.revision, device=self.device
        )

        # sentence-transformers đã đổi tên hàm này; bản cũ chỉ có tên cũ, bản
        # mới cảnh báo khi gọi tên cũ. Hỏi tên mới trước để chạy được trên cả
        # hai mà không phải ghim phiên bản.
        get_dim = getattr(model, "get_embedding_dimension", None) or (
            model.get_sentence_embedding_dimension
        )
        actual = get_dim()
        if actual != self.dim:
            # Lệch số chiều làm cột vector(1024) từ chối ghi, nhưng thông báo
            # lỗi của Postgres khó lần ra nguyên nhân. Chặn ngay tại đây.
            raise RuntimeError(
                f"{self.model_name} sinh vector {actual} chiều nhưng cấu hình và "
                f"lược đồ mong đợi {self.dim}. Sửa EMBEDDING_DIM và cột "
                f"source_chunks.embedding cho khớp."
            )

        self._model = model
        return model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,  # phần của hợp đồng cổng, xem ports/embedding.py
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def unload(self) -> None:
        """Giải phóng VRAM. Cần cho chính sách nạp/giải phóng ở US-057."""
        if self._model is None:
            return
        self._model = None
        try:
            import gc

            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:  # pragma: no cover
            pass
