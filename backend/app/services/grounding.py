"""Xếp hạng lại và quyết định có đủ căn cứ hay không — US-011, US-031.

Đây là ranh giới giữa *"trả lời có căn cứ"* và *"tôi không biết"*, và `SPEC.md`
đặt nó thành một **tiêu chí định lượng** thay vì để mô hình tự quyết. Lý do:
một hệ thống tự quyết khi nào mình biết sẽ luôn nghiêng về phía trả lời, vì
đó là thứ nó được huấn luyện để làm.

Cách hoạt động::

    ~100 ứng viên sau RRF
        ↓  giữ RERANK_CANDIDATES đầu bảng   (mặc định 50)
        ↓  cross-encoder chấm từng cặp (câu hỏi, đoạn)
    xếp lại theo điểm, giữ RERANK_TOP_K     (mặc định 8)
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
    bảng ablation) — lúc đó `top_score` là cosine của nhánh vector và
    `threshold` là TAU_NO_RERANK, không phải τ."""

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
    candidates: int | None = None,
) -> list[ScoredChunk]:
    """Chấm lại các ứng viên đầu bảng bằng cross-encoder rồi giữ top-k.

    Điểm mới ghi đè `rrf_score` trong bản sao trả về — nhưng `ranks` được giữ
    nguyên, nên vẫn truy được một đoạn đã lọt vào từ nhánh nào.

    Chỉ chấm `candidates` ứng viên đầu, không chấm tất cả. Đây là tầng thứ hai
    của một cascade: RRF vốn đã xếp hạng chúng, và cross-encoder — thứ đắt hơn
    hai bậc — chỉ nên chạy trên phần đầu bảng. Chấm hết vừa không cải thiện kết
    quả (thứ hạng 80 gần như không bao giờ leo lên top 8) vừa nhân độ trễ lên
    nhiều lần.
    """
    top_k = top_k or settings.rerank_top_k
    candidates = candidates or settings.rerank_candidates
    if not result.chunks:
        return []

    pool = result.chunks[:candidates]
    scores = reranker.score(question, [s.candidate.content for s in pool])
    if len(scores) != len(pool):  # pragma: no cover - phòng thủ
        raise RuntimeError(f"Reranker trả về {len(scores)} điểm cho {len(pool)} đoạn.")

    scored = [replace(s, rrf_score=score) for s, score in zip(pool, scores, strict=True)]
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
        top_score = chunks[0].rrf_score if chunks else 0.0
    else:
        # Cấu hình C của bảng ablation: bỏ rerank. Điểm RRF nằm quanh 1/60 và
        # KHÔNG cùng thang với τ — so thẳng thì mọi câu đều bị từ chối và dòng
        # C của bảng ablation vô nghĩa. Thay vào đó dùng cosine của nhánh
        # vector (đã chuẩn hoá, [-1, 1]) với ngưỡng riêng TAU_NO_RERANK. Không
        # có nhánh vector thì không có thang nào hợp lý: coi như có căn cứ khi
        # còn ứng viên, và ghi rõ trong `reranked=False`.
        chunks = result.chunks[:top_k]
        reranked = False
        threshold = settings.tau_no_rerank if threshold == settings.tau else threshold
        cos = [result.vector_scores.get(c.chunk_id) for c in chunks]
        cos = [x for x in cos if x is not None]
        top_score = max(cos) if cos else (1.0 if chunks else 0.0)

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
