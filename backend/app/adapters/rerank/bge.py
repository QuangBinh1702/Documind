"""Bộ xếp hạng lại thật — `BAAI/bge-reranker-v2-m3`.

Nạp lười giống adapter nhúng: import module không kéo theo 2.2 GB.
"""

from __future__ import annotations

import logging

from app.settings import settings

__all__ = ["BgeRerankProvider"]

log = logging.getLogger(__name__)


class BgeRerankProvider:
    """Cross-encoder cho điểm đã sigmoid về [0, 1]."""

    def __init__(
        self,
        model_name: str | None = None,
        revision: str | None = None,
        device: str | None = None,
    ) -> None:
        self.model_name = model_name or settings.rerank_model
        self.revision = revision or settings.rerank_revision
        self.device = device or settings.rr_device
        self._model = None

    @property
    def name(self) -> str:
        return f"{self.model_name}@{self.revision or 'unpinned'}"

    def _load(self):
        if self._model is not None:
            return self._model

        try:
            from FlagEmbedding import FlagReranker
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise RuntimeError(
                'Thiếu FlagEmbedding. Cài bằng: pip install -e ".[ml]"\n'
                "Trên máy phát triển có thể đặt RERANK_PROVIDER=fake để bỏ qua."
            ) from exc

        log.info("Nạp %s trên %s …", self.model_name, self.device)
        self._model = FlagReranker(
            self.model_name,
            revision=self.revision,
            use_fp16=self.device == "cuda",
            devices=self.device,
        )
        return self._model

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []

        model = self._load()
        # normalize=True là BẮT BUỘC, không phải tuỳ chọn: thiếu nó model trả
        # về logit thô khoảng −10…+10, và ngưỡng τ = 0.35 ở US-031 sẽ nhận mọi
        # thứ là "đủ căn cứ" mà không có gì báo lỗi.
        raw = model.compute_score(
            [[query, d] for d in documents], normalize=True
        )
        scores = [float(raw)] if isinstance(raw, (int, float)) else [float(s) for s in raw]

        if len(scores) != len(documents):  # pragma: no cover - phòng thủ
            raise RuntimeError(
                f"Reranker trả về {len(scores)} điểm cho {len(documents)} đoạn."
            )
        return scores

    def unload(self) -> None:
        """Giải phóng VRAM — chính sách nạp/giải phóng ở US-057."""
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
