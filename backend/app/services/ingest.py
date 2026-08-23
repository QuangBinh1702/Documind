"""Nạp một tài liệu vào kho tri thức.

Đây là chỗ **nối** những mảnh rời rạc thành một luồng chạy được:

    trích xuất → chuẩn hoá NFC → cổng chất lượng → chunk → nhúng → ghi DB

Cùng một hàm này sẽ được worker Celery gọi ở US-021. CLI gọi nó trực tiếp để
có dữ liệu thật làm việc trước khi có hàng đợi và API.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters.extract import ExtractionError, extract
from app.models.knowledge import Source
from app.ports.embedding import EmbeddingProvider
from app.ports.llm import LLMProvider
from app.repositories import knowledge as repo
from app.services.contextual import build_prefixes, indexed_text
from app.settings import settings
from app.text.chunker import chunk_document
from app.text.quality import TextQuality

__all__ = ["SUFFIX_TO_KIND", "IngestResult", "ingest_file", "ingest_file_sync"]

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
    context_seconds: float = 0.0
    """Thời gian sinh bối cảnh khi bật US-049 — chi phí của dòng E ablation."""

    @property
    def invariant_holds(self) -> bool:
        return self.offsets_total > 0 and self.offsets_ok == self.offsets_total


async def ingest_file(
    session: Session,
    path: Path,
    *,
    notebook_title: str,
    embedder: EmbeddingProvider,
    llm: LLMProvider | None = None,
    owner_email: str = "cli@documind.local",
    existing_source_id: uuid.UUID | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> IngestResult:
    """Nạp một tệp. Ném `ExtractionError` nếu tệp không dùng được.

    `llm` chỉ cần khi bật Contextual Retrieval (US-049); các đường khác không
    dùng tới nó.

    `existing_source_id` dành cho đường tải lên qua API: bản ghi `sources` đã
    được tạo lúc nhận tệp, kèm khoá lưu trữ thật trên MinIO và tên gốc do người
    dùng đặt. Không có tham số này thì hàm sẽ tạo thêm một bản ghi thứ hai trỏ
    vào tệp tạm — nguồn bị nhân đôi, và bản ghi mới mất luôn khoá MinIO nên tệp
    gốc thành mồ côi.
    """

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

    if existing_source_id is not None:
        source = session.get(Source, existing_source_id)
        if source is None:
            raise ExtractionError(
                "SOURCE_NOT_FOUND",
                "Không tìm thấy bản ghi nguồn để cập nhật.",
            )
    else:
        user = repo.get_or_create_user(session, owner_email)
        notebook = repo.get_or_create_notebook(session, user, notebook_title)
        source = repo.upsert_source(
            session,
            notebook,
            title=path.stem,
            original_name=path.name,
            # Đường nạp bằng CLI không đi qua MinIO. Ghi đường dẫn cục bộ kèm
            # tiền tố để phân biệt được với nguồn tải lên qua API.
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

    # ── Phát hiện bản scan (US-023) ─────────────────────
    #
    # Xét TRƯỚC cổng chất lượng, vì một bản scan không có ký tự nào cũng rớt
    # cổng chất lượng — nhưng với chẩn đoán sai. "Chỉ 0% ký tự là chữ cái, có
    # thể là bảng biểu" không giúp được người dùng; "tệp này là bản scan, cần
    # OCR" thì có. Mã lỗi cũng là thứ định tuyến sang đường OCR ở US-024.
    #
    # Chỉ áp dụng cho PDF: DOCX và TXT không có khái niệm trang, nên tỉ lệ
    # trang thiếu text ở đó không mang nghĩa gì.
    if kind == "pdf":
        source.is_scanned = result.looks_scanned(
            chars_per_page=settings.scan_chars_per_page_threshold,
            page_ratio=settings.scan_page_ratio_threshold,
        )
        if source.is_scanned:
            empty = len(result.scanned_pages(settings.scan_chars_per_page_threshold))
            source.status = "failed"
            source.error_code = "SCAN_NO_TEXT_LAYER"
            source.error_message = (
                f"Tệp là bản scan: {empty}/{result.page_count} trang không có lớp "
                f"văn bản. Cần nhận dạng ký tự (OCR) mới đọc được nội dung."
            )
            session.flush()
            raise ExtractionError(source.error_code, source.error_message)

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

    # ── Contextual Retrieval (US-049), nếu bật ──────────
    prefixes: list[str] | None = None
    context_seconds = 0.0
    if settings.contextual_retrieval_enabled and llm is not None:
        step(f"Sinh bối cảnh cho {len(chunks)} đoạn …")
        contextual = await build_prefixes(
            result.full_text, chunks, llm=llm,
            on_progress=(lambda i, n: step(f"  bối cảnh {i}/{n}")) if on_progress else None,
        )
        prefixes = contextual.prefixes
        context_seconds = contextual.seconds

    step(f"Nhúng {len(chunks)} đoạn bằng {embedder.name} …")
    source.status = "embedding"
    session.flush()

    # Nhúng trên prefix + nội dung khi có bối cảnh; hiển thị vẫn là nội dung
    # gốc. Xem `contextual.indexed_text`.
    vectors = embedder.embed_documents(
        [indexed_text(c.content, prefixes[i] if prefixes else None)
         for i, c in enumerate(chunks)]
    )

    step("Ghi vào cơ sở dữ liệu …")
    repo.insert_chunks(session, source, chunks, vectors, prefixes)

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
        context_seconds=context_seconds,
    )

def ingest_file_sync(*args, **kwargs) -> IngestResult:
    """Bọc đồng bộ cho `ingest_file`.

    Hàm chính là async vì Contextual Retrieval (US-049) gọi mô hình ngôn ngữ.
    Những chỗ gọi vốn đồng bộ — CLI, fixture của test — dùng bọc này thay vì
    phải chuyển cả chuỗi gọi sang async chỉ vì một tính năng tuỳ chọn.

    Không dùng được bên trong một vòng lặp sự kiện đang chạy; ở đó hãy `await`
    thẳng `ingest_file`.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(ingest_file(*args, **kwargs))

    raise RuntimeError(
        "ingest_file_sync() được gọi bên trong một vòng lặp sự kiện đang chạy. "
        "Ở đó hãy dùng 'await ingest_file(...)' thay vì bọc đồng bộ."
    )
