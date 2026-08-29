"""Các thực thể của kho tri thức: người dùng, notebook, nguồn, đoạn tri thức.

Ánh xạ vào lược đồ ở migration `0001`. Xem `SPEC-v1.md` §4.2 để biết vì sao
từng cột tồn tại; ở đây chỉ ghi chú những chỗ dễ hiểu nhầm.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.settings import settings

__all__ = [
    "Notebook", "RefreshToken", "ShareLink", "Source", "SourceChunk", "SourceText", "User",
]


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, default="vi")
    role: Mapped[str] = mapped_column(Text, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # `passive_deletes` để ORM KHÔNG tự dọn con trước khi xoá cha.
    #
    # Lược đồ đã khai `ON DELETE CASCADE` (migration 0001). Không có cờ này thì
    # SQLAlchemy nạp hết bản ghi con lên rồi chạy `UPDATE ... SET notebook_id =
    # NULL` để tháo liên kết — mà cột đó `NOT NULL`, nên xoá một notebook có tài
    # liệu sẽ đổ vỡ ngay. Cờ này nói: cơ sở dữ liệu lo phần đó rồi.
    notebooks: Mapped[list[Notebook]] = relationship(
        back_populates="user", cascade="all, delete", passive_deletes=True
    )


class RefreshToken(Base):
    """Refresh token đã cấp — để thu hồi được TRƯỚC khi hết hạn (US-003, US-004).

    Dấu vân tay mật khẩu trong JWT giết mọi token khi đổi mật khẩu, nhưng không
    giúp gì cho hai ca thường gặp hơn: bấm *đăng xuất*, và một refresh token đã
    dùng rồi bị dùng lại (bị đánh cắp). Bảng này ghi `sha256(jti)` của từng
    token còn hiệu lực; `/auth/refresh` thu hồi token cũ và cấp token mới —
    xoay vòng — nên một token chỉ đổi được đúng một lần.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notebook(Base):
    __tablename__ = "notebooks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="notebooks")
    sources: Mapped[list[Source]] = relationship(
        back_populates="notebook", cascade="all, delete", passive_deletes=True
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    notebook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notebooks.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="queued")
    progress: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_scanned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ocr_engine: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    in_scope: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notebook: Mapped[Notebook] = relationship(back_populates="sources")
    text: Mapped[SourceText | None] = relationship(
        back_populates="source", uselist=False,
        cascade="all, delete", passive_deletes=True,
    )
    chunks: Mapped[list[SourceChunk]] = relationship(
        back_populates="source", cascade="all, delete", passive_deletes=True
    )


class SourceText(Base):
    """Văn bản chuẩn của một nguồn.

    Đây là chuỗi mà `char_start`/`char_end` của **mọi** chunk tham chiếu tới.
    Bảng này tồn tại chính vì bất biến INV-1: không lưu `full_text` thì không có
    cách nào kiểm chứng `full_text[start:end] == content`.
    """

    __tablename__ = "source_texts"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    full_text: Mapped[str] = mapped_column(Text)
    page_map: Mapped[list[dict]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[Source] = relationship(back_populates="text")


class SourceChunk(Base):
    __tablename__ = "source_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE")
    )
    # Phi chuẩn hoá có chủ ý: nhánh vector search phải lọc theo notebook ngay
    # trong truy vấn HNSW. JOIN sang sources sẽ mất khả năng dùng chỉ mục.
    notebook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notebooks.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    context_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    heading_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    # Mảng hộp, không phải một hộp: một chunk thường trải nhiều dòng.
    bbox: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dim), nullable=True
    )
    # Sinh bằng to_tsvector('vi', content) ở tầng SQL — xem quyết định 0001.
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[Source] = relationship(back_populates="chunks")


class ShareLink(Base):
    """Liên kết chia sẻ chỉ đọc — US-039.

    Một liên kết chia sẻ **một phiên hội thoại** (`session_id`), vì đó là thứ
    người dùng thực sự muốn gửi đi: một đoạn hỏi đáp cụ thể, kèm các nguồn đứng
    sau nó. `session_id` để trống nghĩa là chia sẻ cả notebook mà không kèm hội
    thoại nào — hình thái duy nhất tồn tại trước migration 0004, vẫn giữ được
    cho những liên kết đã phát đi.

    Ràng buộc duy nhất nằm ở hai chỉ mục từng phần chứ không ở khoá chính: tối
    đa một liên kết cho mỗi phiên, và tối đa một liên kết mức notebook cho mỗi
    notebook. Xem migration 0004 về lý do không gộp chúng thành một ràng buộc.

    Thu hồi bằng cách đặt `revoked_at` chứ không xoá hàng: giữ lại thì còn trả
    lời được câu "liên kết này đã từng tồn tại và bị thu hồi lúc nào".
    """

    __tablename__ = "share_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    notebook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notebooks.id", ondelete="CASCADE")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=True,
    )
    token: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def con_hieu_luc(self) -> bool:
        return self.revoked_at is None
