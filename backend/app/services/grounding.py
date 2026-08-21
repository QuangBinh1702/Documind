"""Xếp hạng lại và quyết định có đủ căn cứ hay không — US-011, US-031.

Đây là ranh giới giữa *"trả lời có căn cứ"* và *"tôi không biết"*, và `SPEC.md`
đặt nó thành một **tiêu chí định lượng** thay vì để mô hình tự quyết. Lý do:
một hệ thống tự quyết khi nào mình biết sẽ luôn nghiêng về phía trả lời, vì
đó là thứ nó được huấn luyện để làm.

Cách hoạt động::

    50 ứng viên sau RRF
        ↓  cross-encoder chấm từng cặp (câu hỏi, đoạn)
    xếp lại theo điểm, giữ top 5–8
        ↓
    điểm cao nhất ≥ τ ?
     ├─ CÓ     → đủ căn cứ, đi đường sinh câu trả lời
     └─ KHÔNG  → không đủ căn cứ, trả lời "không tìm thấy"

Ngưỡng τ mặc định 0.35 là **giá trị khởi đầu**, không phải kết quả đo. US-047
quét τ từ 0.10 đến 0.70 trên bộ câu hỏi có nhãn và chọn theo F1 cao nhất. Cho
tới lúc đó, mọi con số sinh ra từ ngưỡng này chỉ mang tính tham khảo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from app.ports.rerank import RerankProvider
from app.services.retrieval import RetrievalResult, ScoredChunk
from app.settings import settings

__all__ = ["GroundingDecision", "decide", "rerank"]

log = logging.getLogger(__name__)


@dataclass
class GroundingDecision:
    """Kết quả của cổng ngưỡng."""

    grounded: bool
    top_score: float
    threshold: float
    chunks: list[ScoredChunk]
    """Các đoạn đã xếp lại, cao nhất trước. Vẫn trả về khi `grounded` là False —
    đường từ chối cần chúng để giải thích và để hiệu chỉnh τ ở US-047."""

    reranked: bool
    """Đã chạy cross-encoder chưa. False khi rerank bị tắt (cấu hình C của
    bảng ablation) — lúc đó `top_score` là điểm RRF và **không so được với τ**."""

    @property
    def reason(self) -> str:
        if not self.chunks:
            return "Không tìm thấy đoạn nào liên quan trong tài liệu."
        if self.grounded:
            return f"Điểm cao nhất {self.top_score:.3f} ≥ ngưỡng {self.threshold:.2f}."
        return (
            f"Điểm cao nhất {self.top_score:.3f} < ngưỡng {self.threshold:.2f} — "
            f"tài liệu không chứa đủ căn cứ để trả lời."
        )


def rerank(
    question: str,
    result: RetrievalResult,
    *,
    reranker: RerankProvider,
    top_k: int | None = None,
) -> list[ScoredChunk]:
    """Chấm lại từng ứng viên bằng cross-encoder rồi giữ top-k.

    Điểm mới ghi đè `rrf_score` trong bản sao trả về — nhưng `ranks` được giữ
    nguyên, nên vẫn truy được một đoạn đã lọt vào từ nhánh nào.
    """
    top_k = top_k or settings.rerank_top_k
    if not result.chunks:
        return []

    scores = reranker.score(question, [s.candidate.content for s in result.chunks])
    if len(scores) != len(result.chunks):  # pragma: no cover - phòng thủ
        raise RuntimeError(
            f"Reranker trả về {len(scores)} điểm cho {len(result.chunks)} đoạn."
        )

    scored = [replace(s, rrf_score=score) for s, score in zip(result.chunks, scores, strict=True)]
    # Phá hoà bằng chunk_id để thứ tự tái lập được giữa các lần chạy.
    scored.sort(key=lambda s: (-s.rrf_score, s.chunk_id))
    return scored[:top_k]


def decide(
    question: str,
    result: RetrievalResult,
    *,
    reranker: RerankProvider | None = None,
    threshold: float | None = None,
    top_k: int | None = None,
) -> GroundingDecision:
    """Xếp hạng lại (nếu bật) rồi áp cổng ngưỡng."""
    threshold = settings.tau if threshold is None else threshold
    top_k = top_k or settings.rerank_top_k

    if settings.rerank_enabled and reranker is not None:
        chunks = rerank(question, result, reranker=reranker, top_k=top_k)
        reranked = True
    else:
        # Cấu hình C của bảng ablation: bỏ rerank. Điểm còn lại là RRF, vốn
        # nằm quanh 1/60 và KHÔNG cùng thang với τ. Vẫn giữ nguyên phép so
        # sánh để đường mã chỉ có một nhánh, nhưng đánh dấu `reranked=False`
        # để chỗ đọc kết quả biết con số này không diễn giải như bình thường.
        chunks = result.chunks[:top_k]
        reranked = False

    top_score = chunks[0].rrf_score if chunks else 0.0
    grounded = bool(chunks) and top_score >= threshold

    log.info(
        "Cổng ngưỡng: top=%.4f τ=%.2f rerank=%s → %s",
        top_score,
        threshold,
        reranked,
        "grounded" if grounded else "no_answer",
    )

    return GroundingDecision(
        grounded=grounded,
        top_score=top_score,
        threshold=threshold,
        chunks=chunks,
        reranked=reranked,
    )
