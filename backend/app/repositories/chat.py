"""Truy cập dữ liệu cho hội thoại và cache câu trả lời ngoài.

🔴 **INV-3** — các hàm cache ở cuối tệp **không bao giờ** được gọi từ đường
truy xuất tài liệu. Chúng chỉ phục vụ nhánh "hỏi ra ngoài tài liệu" ở US-032.
`test_INV3_*` kiểm chứng ranh giới này bằng cách soi câu SQL đã biên dịch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.chat import (
    ChatMessage,
    ChatSession,
    ExternalAnswerCache,
    ExternalCallLog,
    MessageCitation,
)
from app.services.answer import AnswerResult
from app.settings import settings

__all__ = [
    "calls_today",
    "clear_cache",
    "create_session",
    "find_cached_answer",
    "history_messages",
    "log_external_call",
    "recent_turns",
    "save_answer",
    "save_question",
    "store_cached_answer",
]

# Tiêu đề phiên tự sinh từ câu hỏi đầu tiên — US-018 AC-1.
TITLE_CHARS = 60


def create_session(
    session: Session,
    notebook_id: uuid.UUID,
    user_id: uuid.UUID,
    first_question: str,
    scope_source_ids: list[uuid.UUID] | None = None,
) -> ChatSession:
    """Phiên mới trong `notebook_id`, thuộc về `user_id`.

    Hai id này **không** luôn trỏ về cùng một người: ai mở một liên kết chia sẻ
    rồi hỏi sẽ tạo phiên trong notebook của người khác, và phiên ấy thuộc về họ.
    """
    title = " ".join(first_question.split())[:TITLE_CHARS] or "Phiên mới"
    obj = ChatSession(
        notebook_id=notebook_id,
        user_id=user_id,
        title=title,
        scope_source_ids=scope_source_ids,
    )
    session.add(obj)
    session.flush()
    return obj


def save_question(session: Session, chat_session: ChatSession, question: str) -> ChatMessage:
    msg = ChatMessage(session_id=chat_session.id, role="user", content=question)
    session.add(msg)
    session.flush()
    return msg


def save_answer(
    session: Session,
    chat_session: ChatSession,
    result: AnswerResult,
    *,
    condensed_query: str | None = None,
) -> ChatMessage:
    """Lưu câu trả lời cùng trích dẫn của nó.

    `snippet` được chụp lại tại đây chứ không tra ngược qua `chunk_id` lúc
    hiển thị. Nhờ vậy chip trích dẫn còn đọc được sau khi nguồn bị xoá
    (US-020 AC-4), lúc mà `chunk_id` đã thành NULL.
    """
    msg = ChatMessage(
        session_id=chat_session.id,
        role="assistant",
        content=result.answer,
        answer_kind=result.kind,
        model_used=result.model_used or None,
        condensed_query=condensed_query,
        top_rerank_score=result.decision.top_score if result.decision else None,
        latency_ms=result.latency_ms,
    )
    session.add(msg)
    session.flush()

    for c in result.citations:
        session.add(
            MessageCitation(
                message_id=msg.id,
                chunk_id=c.chunk_id,
                marker=c.marker,
                snippet=c.snippet,
                page_no=c.page_no,
            )
        )

    chat_session.updated_at = func.now()
    session.flush()
    return msg


def history_messages(session: Session, session_id: uuid.UUID) -> list[ChatMessage]:
    return list(
        session.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq)
        )
    )


def recent_turns(
    session: Session, session_id: uuid.UUID, turns: int | None = None
) -> list[dict[str, str]]:
    """N lượt gần nhất, dạng sẵn sàng đưa vào bước condense (US-019 AC-1).

    Một "lượt" là một cặp hỏi–đáp, nên lấy `turns * 2` thông điệp.
    """
    turns = turns or settings.condense_history_turns
    rows = list(
        session.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq.desc())
            .limit(turns * 2)
        )
    )
    rows.reverse()
    return [{"role": m.role, "content": m.content} for m in rows]


# ══════════════════════════════════════════════════════
# Cache câu trả lời NGOÀI tài liệu — namespace tách biệt
# ══════════════════════════════════════════════════════


def find_cached_answer(
    session: Session,
    user_id: uuid.UUID,
    question_vector: list[float],
    *,
    threshold: float | None = None,
) -> tuple[ExternalAnswerCache, float] | None:
    """Tìm câu trả lời đã lưu cho một câu hỏi tương tự — US-034 AC-2.

    Ba ràng buộc, mỗi cái vì một lý do khác nhau:

    * lọc theo `user_id` — cache của người này không dùng cho người khác
      (US-034 AC-6), vì câu hỏi đã hỏi ra ngoài là dữ liệu riêng tư;
    * bỏ bản ghi hết hạn — US-034 AC-5, tránh trả lời cũ khi thế giới đã đổi;
    * ngưỡng tương đồng — mặc định 0.93, và **con số này chưa được hiệu chỉnh
      bằng dữ liệu**. Với `bge-m3`, phân bố cosine bị nén cao nên hai câu chỉ
      khác số điều dễ vượt ngưỡng. Xem việc còn lại ở `SPEC-REVIEW.md` §B.7.
    """
    threshold = settings.external_cache_similarity if threshold is None else threshold

    distance = ExternalAnswerCache.question_embedding.cosine_distance(question_vector)
    row = session.execute(
        select(ExternalAnswerCache, (1 - distance).label("similarity"))
        .where(ExternalAnswerCache.user_id == user_id)
        .where(ExternalAnswerCache.expires_at > func.now())
        .order_by(distance)
        .limit(1)
    ).first()

    if row is None:
        return None
    entry, similarity = row[0], float(row[1])
    return (entry, similarity) if similarity >= threshold else None


def store_cached_answer(
    session: Session,
    user_id: uuid.UUID,
    question: str,
    question_vector: list[float],
    answer: str,
    model_used: str,
) -> ExternalAnswerCache:
    entry = ExternalAnswerCache(
        user_id=user_id,
        question=question,
        question_embedding=question_vector,
        answer=answer,
        model_used=model_used,
        expires_at=datetime.now(UTC) + timedelta(days=settings.external_cache_ttl_days),
    )
    session.add(entry)
    session.flush()
    return entry


def log_external_call(session: Session, user_id: uuid.UUID, *, from_cache: bool) -> None:
    session.add(ExternalCallLog(user_id=user_id, from_cache=from_cache))
    session.flush()


def calls_today(session: Session, user_id: uuid.UUID) -> int:
    """Số lượt gọi RA NGOÀI trong 24 giờ qua — US-035 AC-1.

    Lượt phục vụ từ cache không tính, vì chúng không tiêu tốn quota nào.
    """
    since = datetime.now(UTC) - timedelta(days=1)
    return (
        session.scalar(
            select(func.count())
            .select_from(ExternalCallLog)
            .where(ExternalCallLog.user_id == user_id)
            .where(ExternalCallLog.called_at >= since)
            .where(ExternalCallLog.from_cache.is_(False))
        )
        or 0
    )


def clear_cache(session: Session, user_id: uuid.UUID, entry_id: uuid.UUID | None = None) -> int:
    """Xoá toàn bộ cache của một người, hoặc một bản ghi — US-035 AC-2, AC-3."""
    stmt = delete(ExternalAnswerCache).where(ExternalAnswerCache.user_id == user_id)
    if entry_id is not None:
        stmt = stmt.where(ExternalAnswerCache.id == entry_id)
    return session.execute(stmt).rowcount or 0
