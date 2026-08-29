"""Thực thể hội thoại và cache câu trả lời ngoài.

`ExternalAnswerCache` cố ý nằm **cùng tệp** với các thực thể hội thoại chứ
không nằm cùng `knowledge.py`. Đó là một tín hiệu về ranh giới: cache thuộc
đường hội thoại, và bất biến **INV-3** cấm đường truy vấn tài liệu chạm tới nó.
Đặt nó cạnh `SourceChunk` sẽ mời gọi đúng cái join mà bất biến cấm.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    FetchedValue,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.settings import settings

__all__ = ["ChatMessage", "ChatSession", "ExternalAnswerCache", "ExternalCallLog", "MessageCitation"]


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    notebook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notebooks.id", ondelete="CASCADE")
    )
    # Chủ phiên KHÔNG suy ra được từ notebook — xem migration 0004. Người mở một
    # liên kết chia sẻ hỏi trong notebook của người khác, và hội thoại ấy thuộc
    # về họ. Mọi phép lọc "hội thoại của tôi" phải đi qua cột này.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text)
    # US-038 AC-4 — lựa chọn phạm vi được giữ theo từng phiên.
    scope_source_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", order_by="ChatMessage.seq"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    answer_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    condensed_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Dữ liệu để hiệu chỉnh τ ở US-047 — không có nó thì việc quét ngưỡng
    # phải chạy lại toàn bộ truy xuất cho từng giá trị.
    top_rerank_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Thứ tự tin nhắn trong một phiên BẢN CHẤT là thứ tự chèn. Timestamp không
    # biểu diễn được điều đó: `now()` giống nhau trong cùng transaction, và
    # `clock_timestamp()` vẫn có thể hoà ở độ phân giải micro giây. Xem
    # migration 0002.
    #
    # `FetchedValue` là bắt buộc: nó nói với SQLAlchemy rằng giá trị do máy chủ
    # sinh, nên cột bị loại khỏi câu INSERT và đọc lại sau. Thiếu nó thì ORM
    # chèn NULL và BIGSERIAL từ chối.
    seq: Mapped[int] = mapped_column(BigInteger, FetchedValue(), nullable=False)

    session: Mapped[ChatSession] = relationship(back_populates="messages")
    citations: Mapped[list[MessageCitation]] = relationship(
        back_populates="message", order_by="MessageCitation.marker"
    )


class MessageCitation(Base):
    __tablename__ = "message_citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE")
    )
    # ON DELETE SET NULL: nguồn bị xoá thì chip vẫn hiện được `snippet` đã chụp
    # kèm trạng thái "Nguồn đã bị xoá" (US-020 AC-4).
    chunk_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("source_chunks.id", ondelete="SET NULL"), nullable=True
    )
    marker: Mapped[int] = mapped_column(Integer)
    snippet: Mapped[str] = mapped_column(Text)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)

    message: Mapped[ChatMessage] = relationship(back_populates="citations")


class ExternalAnswerCache(Base):
    """Cache câu trả lời từ mô hình NGOÀI tài liệu.

    🔴 **INV-3** — đường truy vấn tài liệu không bao giờ được đọc bảng này.
    Không JOIN, không UNION, không subquery. Vi phạm thì hệ thống sẽ dần trích
    dẫn chính nội dung nó tự bịa ra, và toàn bộ giá trị của tính năng trích dẫn
    sụp đổ (`SPEC.md` §J.6).
    """

    __tablename__ = "external_answer_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    question: Mapped[str] = mapped_column(Text)
    question_embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))
    answer: Mapped[str] = mapped_column(Text)
    model_used: Mapped[str] = mapped_column(Text)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExternalCallLog(Base):
    """Nhật ký gọi ra ngoài — dữ liệu cho hạn mức US-035 và thống kê US-041."""

    __tablename__ = "external_call_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    from_cache: Mapped[bool] = mapped_column(Boolean)
