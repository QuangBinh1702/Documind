"""Nạp một tài liệu vào kho tri thức.

Đây là chỗ **nối** những mảnh rời rạc thành một luồng chạy được:

    trích xuất → chuẩn hoá NFC → cổng chất lượng → chunk → nhúng → ghi DB

Cùng một hàm này sẽ được worker Celery gọi ở US-021. CLI gọi nó trực tiếp để
có dữ liệu thật làm việc trước khi có hàng đợi và API.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters.extract import ExtractionError, extract
from app.ports.embedding import EmbeddingProvider
from app.repositories import knowledge as repo
from app.settings import settings
from app.text.chunker import chunk_document
from app.text.quality import TextQuality

__all__ = ["SUFFIX_TO_KIND", "IngestResult", "ingest_file"]

log = logging.getLogger(__name__)

SUFFIX_TO_KIND = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
}

MIME_BY_KIND = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
}


@dataclass
class IngestResult:
    source_id: str
    title: str
    kind: str
    page_count: int
    chunk_count: int
    quality: TextQuality
    method: str
    offsets_ok: int
    offsets_total: int

    @property
    def invariant_holds(self) -> bool:
        return self.offsets_total > 0 and self.offsets_ok == self.offsets_total


def ingest_file(
    session: Session,
    path: Path,
    *,
    notebook_title: str,
    embedder: EmbeddingProvider,
    owner_email: str = "cli@documind.local",
    on_progress: Callable[[str], None] | None = None,
) -> IngestResult:
    """Nạp một tệp. Ném `ExtractionError` nếu tệp không dùng được."""

    def step(message: str) -> None:
        log.info(message)
        if on_progress:
            on_progress(message)

    kind = SUFFIX_TO_KIND.get(path.suffix.lower())
    if kind is None:
        raise ExtractionError(
            "KIND_UNSUPPORTED",
            f"Chưa hỗ trợ định dạng '{path.suffix}'. "
            f"Hỗ trợ: {', '.join(sorted(SUFFIX_TO_KIND))}.",
        )

    user = repo.get_or_create_user(session, owner_email)
    notebook = repo.get_or_create_notebook(session, user, notebook_title)

    source = repo.upsert_source(
        session,
        notebook,
        title=path.stem,
        original_name=path.name,
        # Tệp gốc chưa lên MinIO — việc đó thuộc US-006. Ghi đường dẫn cục bộ
        # kèm tiền tố để sau này phân biệt được nguồn nạp bằng CLI.
        storage_key=f"cli://{path.resolve().as_posix()}",
        kind=kind,
        mime_type=MIME_BY_KIND[kind],
        size_bytes=path.stat().st_size,
    )

    step(f"Trích xuất {path.name} …")
    result = extract(path, kind)
    quality = result.quality

    source.page_count = result.page_count
    source.text_quality = quality.score

    # Cổng chất lượng US-056. Chặn TRƯỚC khi tốn công nhúng — văn bản rác vào
    # chỉ mục thì mọi câu trả lời về sau đều hỏng, và rất khó truy ra nguyên nhân.
    if quality.legacy_encoding is not None:
        source.status = "failed"
        source.error_code = f"LEGACY_ENCODING_{quality.legacy_encoding.upper()}"
        source.error_message = (
            f"Tệp dùng bảng mã cũ ({quality.legacy_encoding.upper()}), "
            f"nội dung trích ra là rác. Cần chuyển mã hoặc xử lý bằng OCR."
        )
        session.flush()
        raise ExtractionError(source.error_code, source.error_message)

    if quality.score < settings.text_quality_min:
        source.status = "failed"
        source.error_code = "LOW_TEXT_QUALITY"
        source.error_message = (
            f"Chất lượng văn bản {quality.score:.2f} dưới ngưỡng "
            f"{settings.text_quality_min:.2f}. " + "; ".join(quality.issues)
        )
        session.flush()
        raise ExtractionError(source.error_code, source.error_message)

    repo.replace_source_text(
        session,
        source,
        result.full_text,
        [{"page": p.page, "start": p.start, "end": p.end} for p in result.pages],
    )

    step(f"Chia đoạn ({len(result.full_text):,} ký tự) …")
    source.status = "chunking"
    session.flush()

    chunks = chunk_document(
        result,
        max_tokens=settings.chunk_tokens,
        overlap_ratio=settings.chunk_overlap_ratio,
        respect_headings=settings.chunk_respect_headings,
    )
    if not chunks:
        source.status = "failed"
        source.error_code = "NO_CHUNKS"
        source.error_message = "Không tạo được đoạn tri thức nào từ tệp này."
        session.flush()
        raise ExtractionError(source.error_code, source.error_message)

    step(f"Nhúng {len(chunks)} đoạn bằng {embedder.name} …")
    source.status = "embedding"
    session.flush()

    vectors = embedder.embed_documents([c.content for c in chunks])

    step("Ghi vào cơ sở dữ liệu …")
    repo.insert_chunks(session, source, chunks, vectors)

    # Kiểm chứng INV-1 trên dữ liệu ĐÃ GHI, không phải trên đối tượng trong bộ
    # nhớ. Bắt được cả lỗi phát sinh ở tầng lưu trữ.
    ok, total = repo.verify_offsets(session, source.id)
    if ok != total:
        source.status = "failed"
        source.error_code = "OFFSET_MISMATCH"
        source.error_message = (
            f"Bất biến INV-1 bị vi phạm: {total - ok}/{total} đoạn không cắt lại "
            f"được đúng nội dung từ văn bản gốc."
        )
        session.flush()
        raise ExtractionError(source.error_code, source.error_message)

    source.status = "ready"
    source.progress = 100
    source.ready_at = datetime.now(UTC)
    session.flush()

    return IngestResult(
        source_id=str(source.id),
        title=source.title,
        kind=kind,
        page_count=result.page_count,
        chunk_count=len(chunks),
        quality=quality,
        method=result.method,
        offsets_ok=ok,
        offsets_total=total,
    )
