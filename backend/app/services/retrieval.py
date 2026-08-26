"""Truy xuất lai và hợp nhất bằng RRF — US-010.

Hai nhánh chạy trên cùng bộ lọc rồi hợp nhất bằng **Reciprocal Rank Fusion**.

Vì sao RRF chứ không cộng điểm
------------------------------
Nhánh vector trả về độ tương đồng cosine trong khoảng [-1, 1]; nhánh từ khoá
trả về `ts_rank_cd`, một đại lượng không chặn trên và phụ thuộc độ dài tài
liệu. Cộng hay lấy trung bình hai thang đó là vô nghĩa, và chuẩn hoá chúng về
cùng thang lại đưa vào một tham số nữa phải hiệu chỉnh.

RRF bỏ qua điểm hoàn toàn và chỉ dùng **thứ hạng**::

    score(d) = Σ  1 / (k + rank(d, nhánh))

Nhờ vậy nó miễn nhiễm với việc `ts_rank_cd` hay hoà điểm — hạn chế đã ghi ở
`docs/decisions/0001`.

Ba cấu hình đầu của bảng ablation US-046 chính là ba cách bật/tắt hai cờ
`RETRIEVAL_VECTOR_ENABLED` và `RETRIEVAL_BM25_ENABLED`, không sửa dòng mã nào.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ports.embedding import EmbeddingProvider
from app.repositories import retrieval as repo
from app.repositories.retrieval import Candidate
from app.settings import settings

__all__ = ["RetrievalResult", "ScoredChunk", "reciprocal_rank_fusion", "retrieve"]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    candidate: Candidate
    rrf_score: float
    ranks: dict[str, int] = field(default_factory=dict)
    """Thứ hạng trong từng nhánh, 1 là cao nhất. Dùng để giải thích vì sao một
    chunk được chọn — cần cho gỡ lỗi và cho phần phân tích ở Chương 5."""

    @property
    def chunk_id(self) -> int:
        return self.candidate.chunk_id


@dataclass
class RetrievalResult:
    chunks: list[ScoredChunk]
    vector_count: int
    fulltext_count: int
    branches: list[str]
    vector_scores: dict[int, float] = field(default_factory=dict)
    """Cosine của nhánh vector theo `chunk_id`. Cổng ngưỡng dùng nó khi rerank
    bị tắt (cấu hình C của ablation) — điểm RRF không so được với τ."""

    def __len__(self) -> int:
        return len(self.chunks)


def reciprocal_rank_fusion(
    rankings: dict[str, list[Candidate]], k: int | None = None
) -> list[ScoredChunk]:
    """Hợp nhất nhiều danh sách đã xếp hạng thành một.

    `k` làm phẳng đóng góp của những vị trí đầu: k càng lớn thì chênh lệch giữa
    hạng 1 và hạng 2 càng nhỏ. Giá trị 60 lấy từ bài báo gốc của Cormack và
    cộng sự (2009) và nằm trong cấu hình để quét thêm nếu còn thời gian.

    Khử trùng lặp theo `chunk_id`: một chunk xuất hiện ở cả hai nhánh **cộng
    dồn** điểm, và đó chính là điều làm RRF hữu ích — đồng thuận giữa hai tín
    hiệu độc lập được thưởng.
    """
    k = k if k is not None else settings.rrf_k

    scores: dict[int, float] = {}
    ranks: dict[int, dict[str, int]] = {}
    seen: dict[int, Candidate] = {}

    for branch, candidates in rankings.items():
        for position, cand in enumerate(candidates, start=1):
            scores[cand.chunk_id] = scores.get(cand.chunk_id, 0.0) + 1.0 / (k + position)
            ranks.setdefault(cand.chunk_id, {})[branch] = position
            seen.setdefault(cand.chunk_id, cand)

    fused = [
        ScoredChunk(candidate=seen[cid], rrf_score=score, ranks=ranks[cid])
        for cid, score in scores.items()
    ]
    # Phá hoà bằng chunk_id để thứ tự đoán trước được — thứ hạng nhấp nháy làm
    # kết quả đánh giá không tái lập được.
    fused.sort(key=lambda s: (-s.rrf_score, s.chunk_id))
    return fused


def retrieve(
    session: Session,
    question: str,
    *,
    notebook_id: uuid.UUID,
    embedder: EmbeddingProvider,
    owner_id: uuid.UUID | None = None,
    source_ids: list[uuid.UUID] | None = None,
    top_n: int | None = None,
) -> RetrievalResult:
    """Chạy các nhánh đang bật rồi hợp nhất.

    Trả về tối đa `top_n` ứng viên (mặc định 50) làm đầu vào cho bước rerank ở
    US-011.
    """
    top_n = top_n or settings.retrieval_top_n_per_branch
    rankings: dict[str, list[Candidate]] = {}

    if settings.retrieval_vector_enabled:
        rankings["vector"] = repo.search_vector(
            session,
            embedder.embed_query(question),
            notebook_id=notebook_id,
            owner_id=owner_id,
            source_ids=source_ids,
            limit=top_n,
        )

    if settings.retrieval_bm25_enabled:
        rankings["fulltext"] = repo.search_fulltext(
            session,
            question,
            notebook_id=notebook_id,
            owner_id=owner_id,
            source_ids=source_ids,
            limit=top_n,
        )

    if not rankings:
        raise RuntimeError(
            "Cả hai nhánh truy xuất đều tắt. Bật ít nhất một trong "
            "RETRIEVAL_VECTOR_ENABLED hoặc RETRIEVAL_BM25_ENABLED."
        )

    fused = reciprocal_rank_fusion(rankings)[:top_n]

    log.info(
        "Truy xuất %r: vector=%d, fulltext=%d, sau RRF=%d",
        question[:60],
        len(rankings.get("vector", [])),
        len(rankings.get("fulltext", [])),
        len(fused),
    )

    return RetrievalResult(
        chunks=fused,
        vector_count=len(rankings.get("vector", [])),
        fulltext_count=len(rankings.get("fulltext", [])),
        branches=sorted(rankings),
        vector_scores={c.chunk_id: c.score for c in rankings.get("vector", [])},
    )
