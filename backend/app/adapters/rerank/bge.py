"""Bộ xếp hạng lại thật — `BAAI/bge-reranker-v2-m3`.

Nạp lười giống adapter nhúng: import module không kéo theo 2.2 GB.

Vì sao dùng `sentence-transformers` chứ không dùng `FlagEmbedding`
------------------------------------------------------------------
`FlagEmbedding` là thư viện của chính nhóm tác giả bge, nhưng nó gọi vào
`tokenizer.prepare_for_model` — một API đã bị gỡ ở `transformers` 5. Cài cả hai
cùng lúc thì reranker chết ngay lượt chấm đầu tiên với `AttributeError`.

`CrossEncoder` của `sentence-transformers` nạp đúng mô hình đó, và thư viện này
vốn đã có mặt vì adapter nhúng cần. Một phụ thuộc ít hơn, và không phải ghim
`transformers` xuống bản cũ chỉ để giữ một thư viện chạy được.
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
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise RuntimeError(
                'Thiếu sentence-transformers. Cài bằng: pip install -e ".[ml]"\n'
                "Trên máy phát triển có thể đặt RERANK_PROVIDER=fake để bỏ qua."
            ) from exc

        log.info("Nạp %s trên %s …", self.model_name, self.device)
        self._model = CrossEncoder(
            self.model_name,
            revision=self.revision,
            device=self.device,
            # fp16 chỉ có nghĩa trên GPU; ép trên CPU thì chậm hơn chứ không nhanh hơn.
            model_kwargs={"dtype": "float16"} if self.device == "cuda" else {},
        )
        return self._model

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []

        import torch

        model = self._load()
        # Sigmoid là BẮT BUỘC, không phải tuỳ chọn: thiếu nó mô hình trả về
        # logit thô khoảng −10…+10, và ngưỡng τ = 0.35 ở US-031 sẽ nhận mọi thứ
        # là "đủ căn cứ" mà không có gì báo lỗi.
        raw = model.predict(
            [(query, d) for d in documents],
            activation_fn=torch.nn.Sigmoid(),
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        scores = [float(s) for s in raw]

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
