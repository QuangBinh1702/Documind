"""Hai nhánh truy xuất — US-010.

Cả hai nhánh nhận **cùng bộ lọc** và trả về **cùng kiểu kết quả**, để tầng
service hợp nhất chúng mà không cần biết chúng khác nhau ở đâu.

Ba ràng buộc bắt buộc, mỗi cái có test bảo vệ:

* **INV-3** — không truy vấn nào ở đây được chạm tới `external_answer_cache`.
  Vi phạm thì hệ thống sẽ dần trích dẫn chính nội dung nó tự bịa ra.
* **INV-4** — lọc theo chủ sở hữu ngay ở **tầng SQL**, không lọc sau khi đã
  lấy ra. Lọc sau nghĩa là dữ liệu người khác đã rời khỏi cơ sở dữ liệu.
* **Quyết định 0001** — nhánh từ khoá dùng `phraseto_tsquery`/`plainto_tsquery`
  trên văn bản gốc, không dùng gạch dưới.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, and_, func, select
from sqlalchemy.orm import Session

from app.models.knowledge import Notebook, SourceChunk
from app.settings import settings
from app.text.segment import build_tsquery_parts

__all__ = ["Candidate", "build_tsquery", "search_fulltext", "search_vector"]


@dataclass(frozen=True, slots=True)
class Candidate:
    """Một ứng viên từ một nhánh truy xuất."""

    chunk_id: int
    source_id: uuid.UUID
    content: str
    page_no: int | None
    heading_path: str | None
    char_start: int
    char_end: int
    score: float
    """Điểm thô của nhánh. **Không so sánh được giữa hai nhánh** — cosine và
    ts_rank_cd khác thang hoàn toàn. Đó chính là lý do hợp nhất bằng RRF, vốn
    chỉ dùng thứ hạng."""


def _base(
    notebook_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    source_ids: list[uuid.UUID] | None,
) -> list[ColumnElement[bool]]:
    """Bộ lọc dùng chung cho cả hai nhánh."""
    conditions: list[ColumnElement[bool]] = [SourceChunk.notebook_id == notebook_id]

    # US-038 AC-2: lọc phạm vi ngay ở tầng SQL, không lọc sau khi đã lấy ra.
    if source_ids:
        conditions.append(SourceChunk.source_id.in_(source_ids))

    return conditions


def _owned(stmt: Select, owner_id: uuid.UUID | None) -> Select:
    """Ràng buộc quyền sở hữu — INV-4.

    Nối qua `notebooks` thay vì tin vào `notebook_id` mà chỗ gọi truyền xuống.
    Nếu chỗ gọi lỡ truyền notebook của người khác thì truy vấn trả về rỗng,
    chứ không trả về dữ liệu của họ.
    """
    if owner_id is None:
        return stmt
    return stmt.join(Notebook, Notebook.id == SourceChunk.notebook_id).where(
        Notebook.user_id == owner_id
    )


def _rows_to_candidates(rows) -> list[Candidate]:
    return [
        Candidate(
            chunk_id=r.id,
            source_id=r.source_id,
            content=r.content,
            page_no=r.page_no,
            heading_path=r.heading_path,
            char_start=r.char_start,
            char_end=r.char_end,
            score=float(r.score),
        )
        for r in rows
    ]


_COLUMNS = (
    SourceChunk.id,
    SourceChunk.source_id,
    SourceChunk.content,
    SourceChunk.page_no,
    SourceChunk.heading_path,
    SourceChunk.char_start,
    SourceChunk.char_end,
)


def search_vector(
    session: Session,
    query_vector: list[float],
    *,
    notebook_id: uuid.UUID,
    owner_id: uuid.UUID | None = None,
    source_ids: list[uuid.UUID] | None = None,
    limit: int | None = None,
) -> list[Candidate]:
    """Nhánh ngữ nghĩa — khoảng cách cosine trên chỉ mục HNSW.

    `<=>` là khoảng cách cosine của pgvector, nên `1 - <=>` là độ tương đồng.
    Cả hai vế đều đã chuẩn hoá L2 (hợp đồng của `EmbeddingProvider`).
    """
    limit = limit or settings.retrieval_top_n_per_branch

    # pgvector lọc SAU khi duyệt đồ thị HNSW, nên với notebook nhỏ trong một
    # bảng lớn, ef_search mặc định (40) có thể trả về thiếu kết quả.
    session.execute(func.set_config("hnsw.ef_search", str(settings.hnsw_ef_search), True))

    distance = SourceChunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(*_COLUMNS, (1 - distance).label("score"))
        .where(and_(*_base(notebook_id, owner_id, source_ids)))
        .where(SourceChunk.embedding.isnot(None))
        .order_by(distance)
        .limit(limit)
    )
    return _rows_to_candidates(session.execute(_owned(stmt, owner_id)).all())


def build_tsquery(question: str):
    """Dựng biểu thức `tsquery` từ câu hỏi, theo quyết định 0001.

    Từ ghép dùng `phraseto_tsquery` để yêu cầu các âm tiết **liền kề**; từ đơn
    dùng `plainto_tsquery`. Các mảnh nối bằng **OR**, không phải AND.

    Vì sao OR: nối bằng AND thì tài liệu phải chứa *mọi* từ trong câu hỏi, và
    một câu hỏi tự nhiên mười hai từ gần như luôn cho ra rỗng. Nhánh này tồn
    tại để **tăng độ bao phủ** cho những thuật ngữ mà vector search bỏ sót;
    việc lọc lại là của rerank ở US-011.

    Trả về `None` khi câu hỏi không còn từ nào tìm được — chỗ gọi bỏ qua nhánh
    từ khoá thay vì chạy một truy vấn khớp mọi thứ.
    """
    parts = build_tsquery_parts(question)
    if not parts:
        return None

    expressions = [
        func.phraseto_tsquery("vi", content)
        if kind == "phrase"
        else func.plainto_tsquery("vi", content)
        for kind, content in parts
    ]

    combined = expressions[0]
    for expr in expressions[1:]:
        combined = combined.op("||")(expr)
    return combined


def search_fulltext(
    session: Session,
    question: str,
    *,
    notebook_id: uuid.UUID,
    owner_id: uuid.UUID | None = None,
    source_ids: list[uuid.UUID] | None = None,
    limit: int | None = None,
) -> list[Candidate]:
    """Nhánh từ khoá — `ts_rank_cd` trên chỉ mục GIN.

    Đây **không phải BM25**: PostgreSQL không có BM25, và `ts_rank_cd` là một
    hàm xếp hạng khác, không có tham số `k1`/`b`. Điều đó không ảnh hưởng tới
    kết quả hợp nhất vì RRF chỉ dùng **thứ hạng**. Trong báo cáo phải gọi đúng
    tên: *"full-text search của PostgreSQL"*.
    """
    limit = limit or settings.retrieval_top_n_per_branch

    tsquery = build_tsquery(question)
    if tsquery is None:
        return []

    rank = func.ts_rank_cd(SourceChunk.tsv, tsquery)
    stmt = (
        select(*_COLUMNS, rank.label("score"))
        .where(and_(*_base(notebook_id, owner_id, source_ids)))
        .where(SourceChunk.tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    return _rows_to_candidates(session.execute(_owned(stmt, owner_id)).all())
