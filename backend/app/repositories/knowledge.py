"""Truy cập dữ liệu cho kho tri thức.

Nơi **duy nhất** viết SQL. Tầng service gọi các hàm ở đây và không tự dựng
truy vấn — quy tắc phân lớp ở Definition of Done D4 (`SPEC.md` §A.4).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.knowledge import Notebook, Source, SourceChunk, SourceText, User
from app.text.chunker import Chunk

__all__ = [
    "count_chunks",
    "get_or_create_notebook",
    "get_or_create_user",
    "insert_chunks",
    "replace_source_text",
    "upsert_source",
    "verify_offsets",
]


def get_or_create_user(session: Session, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        # Mật khẩu giả cho tài khoản do CLI tạo. Xác thực thật thuộc US-002;
        # tài khoản này không đăng nhập được qua API.
        user = User(email=email, password_hash="!cli-seeded-no-login")
        session.add(user)
        session.flush()
    return user


def get_or_create_notebook(session: Session, user: User, title: str) -> Notebook:
    nb = session.scalar(
        select(Notebook).where(Notebook.user_id == user.id, Notebook.title == title)
    )
    if nb is None:
        nb = Notebook(user_id=user.id, title=title)
        session.add(nb)
        session.flush()
    return nb


def upsert_source(
    session: Session,
    notebook: Notebook,
    *,
    title: str,
    original_name: str,
    storage_key: str,
    kind: str,
    mime_type: str,
    size_bytes: int,
) -> Source:
    """Lấy nguồn theo tên gốc trong notebook, hoặc tạo mới.

    Tìm theo `original_name` để nạp lại cùng một tệp **cập nhật** bản ghi cũ
    thay vì sinh bản trùng — điều kiện để US-008 AC-8 (xử lý lại cho kết quả
    giống nhau) đúng ở mức toàn hệ thống, không chỉ ở mức hàm chunking.
    """
    src = session.scalar(
        select(Source).where(
            Source.notebook_id == notebook.id, Source.original_name == original_name
        )
    )
    if src is None:
        src = Source(notebook_id=notebook.id, original_name=original_name)
        session.add(src)

    src.title = title
    src.storage_key = storage_key
    src.kind = kind
    src.mime_type = mime_type
    src.size_bytes = size_bytes
    src.status = "parsing"
    src.progress = 0
    src.error_code = None
    src.error_message = None
    session.flush()
    return src


def replace_source_text(
    session: Session, source: Source, full_text: str, page_map: list[dict]
) -> None:
    existing = session.get(SourceText, source.id)
    if existing is None:
        session.add(SourceText(source_id=source.id, full_text=full_text, page_map=page_map))
    else:
        existing.full_text = full_text
        existing.page_map = page_map
        existing.updated_at = func.now()
    session.flush()


def insert_chunks(
    session: Session,
    source: Source,
    chunks: Sequence[Chunk],
    embeddings: Sequence[Sequence[float]],
    context_prefixes: Sequence[str] | None = None,
) -> int:
    """Ghi chunk, xoá sạch chunk cũ của nguồn trước.

    Xoá trước là điều kiện để nạp lại cùng một tệp không sinh chunk trùng
    (US-008 AC-8) và không để lại chunk mồ côi khi tài liệu ngắn đi.

    `context_prefixes` (US-049) chỉ tham gia vào `tsv`; nó **không** ghi đè
    `content`, nên bất biến INV-1 giữ nguyên và trích dẫn vẫn hiện đúng nguyên
    văn tài liệu.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Số chunk ({len(chunks)}) khác số vector ({len(embeddings)})"
        )
    if context_prefixes is not None and len(context_prefixes) != len(chunks):
        raise ValueError(
            f"Số chunk ({len(chunks)}) khác số bối cảnh ({len(context_prefixes)})"
        )

    session.execute(delete(SourceChunk).where(SourceChunk.source_id == source.id))
    session.flush()

    prefixes = list(context_prefixes) if context_prefixes else [None] * len(chunks)

    for chunk, vector, prefix in zip(chunks, embeddings, prefixes, strict=True):
        session.add(
            SourceChunk(
                source_id=source.id,
                notebook_id=source.notebook_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                context_prefix=prefix or None,
                heading_path=chunk.heading_path,
                page_no=chunk.page_no,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                bbox=[b.as_dict() for b in chunk.bbox] if chunk.bbox else None,
                token_count=chunk.token_count,
                embedding=list(vector),
            )
        )
    session.flush()

    # tsv sinh ở tầng SQL bằng to_tsvector('vi', …) trên văn bản GỐC. Không
    # tách từ, không nối bằng gạch dưới — xem quyết định 0001: bộ phân tích của
    # Postgres coi '_' là ký tự phân tách nên cách cũ hỏng im lặng.
    #
    # Khi có bối cảnh, nó được ghép vào đây — đây chính là "Contextual BM25"
    # của US-049 AC-2. Bỏ nửa này là bỏ một nửa lợi ích của cả kỹ thuật.
    columns = SourceChunk.__table__.c
    indexed = func.coalesce(columns.context_prefix + " ", "") + columns.content

    session.execute(
        SourceChunk.__table__.update()
        .where(columns.source_id == source.id)
        .values(tsv=func.to_tsvector("vi", indexed))
    )
    session.flush()
    return len(chunks)


def count_chunks(session: Session, source_id: uuid.UUID) -> int:
    return session.scalar(
        select(func.count()).select_from(SourceChunk).where(SourceChunk.source_id == source_id)
    ) or 0


def verify_offsets(session: Session, source_id: uuid.UUID) -> tuple[int, int]:
    """Kiểm chứng INV-1 **trên dữ liệu đã ghi vào cơ sở dữ liệu**.

    Trả về ``(số chunk khớp, tổng số chunk)``.

    Test trong `test_chunker.py` kiểm bất biến ở mức hàm. Hàm này kiểm ở mức
    lưu trữ — nó bắt được cả những lỗi phát sinh sau bước chunking: cắt cụt khi
    ghi, đối chiếu sai bản ghi văn bản, hoặc một tầng nào đó lỡ chuẩn hoá lại.

    Lưu ý: `substring` của SQL đánh chỉ số từ **1**, slicing của Python từ
    **0** — thiếu ``+ 1`` thì lệch một ký tự mà kết quả vẫn "gần đúng".
    """
    row = session.execute(
        select(
            func.count().label("total"),
            func.count()
            .filter(
                func.substring(
                    SourceText.__table__.c.full_text,
                    SourceChunk.__table__.c.char_start + 1,
                    SourceChunk.__table__.c.char_end - SourceChunk.__table__.c.char_start,
                )
                == SourceChunk.__table__.c.content
            )
            .label("matching"),
        )
        .select_from(SourceChunk)
        .join(SourceText, SourceText.source_id == SourceChunk.source_id)
        .where(SourceChunk.source_id == source_id)
    ).one()
    return int(row.matching), int(row.total)
