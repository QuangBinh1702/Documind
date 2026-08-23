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
from app.services import progress
from app.services.contextual import build_prefixes, indexed_text
from app.settings import settings
from app.text.chunker import chunk_document
from app.text.quality import TextQuality

__all__ = [
    "KINDS_CAN_OCR",
    "MIME_BY_SUFFIX",
    "SUFFIX_TO_KIND",
    "IngestResult",
    "ingest_file",
    "ingest_file_sync",
    "mime_cho",
]

log = logging.getLogger(__name__)

SUFFIX_TO_KIND = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}

# MIME tra theo **đuôi tệp**, không tra theo `kind`. Bốn đuôi ảnh cùng cho ra
# `kind='image'` nhưng là bốn kiểu MIME khác nhau, và MinIO trả lại đúng kiểu
# nào thì trình duyệt hiển thị được ảnh — sai kiểu thì nó tải về thay vì mở.
MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

# Loại nguồn phải đi qua nhận dạng chữ vì bản thân nó không có lớp văn bản nào.
KINDS_CAN_OCR = {"image"}


def mime_cho(filename: str | Path) -> str:
    """Kiểu MIME của một tệp theo đuôi của nó."""
    return MIME_BY_SUFFIX.get(Path(filename).suffix.lower(), "application/octet-stream")


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

    def step(message: str, *, trang_thai: str | None = None, phan_tram: int | None = None) -> None:
        """Ghi nhật ký, báo cho chỗ gọi, và đẩy tiến độ ra ngoài transaction.

        Ba việc chứ không phải một, vì hàm này chạy trong một transaction dài:
        mọi thứ ghi vào hàng `sources` chỉ hiện ra khi transaction đó commit.
        `progress.dat` đi qua Redis nên giao diện thấy được ngay — xem chú thích
        đầu `app/services/progress.py`.
        """
        log.info(message)
        if on_progress:
            on_progress(message)
        if trang_thai is not None:
            progress.dat(
                source.id,
                status=trang_thai,
                progress=phan_tram if phan_tram is not None else 0,
                message=message,
            )

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
            mime_type=mime_cho(path),
            size_bytes=path.stat().st_size,
        )

    if kind in KINDS_CAN_OCR:
        # ── Ảnh (US-025) ────────────────────────────────
        #
        # Không có lớp văn bản để thử trước, nên đi thẳng OCR. Tắt OCR thì nói
        # rõ điều đó thay vì báo "không trích xuất được" — nguyên nhân và cách
        # sửa nằm ở hai chỗ khác nhau.
        if not settings.ocr_enabled:
            source.status = "failed"
            source.error_code = "OCR_DISABLED"
            source.error_message = (
                "Ảnh chỉ đọc được bằng nhận dạng chữ, mà tính năng này đang tắt "
                "(OCR_ENABLED=false)."
            )
            session.flush()
            raise ExtractionError(source.error_code, source.error_message)

        from app.adapters.extract.image import extract_image
        from app.adapters.ocr import get_ocr_provider

        ocr = get_ocr_provider()
        step("Đang nhận dạng chữ trong ảnh …", trang_thai="ocr", phan_tram=25)
        source.status = "ocr"
        source.ocr_engine = ocr.name
        session.flush()

        result = extract_image(path, ocr)
    else:
        step(f"Đang đọc {path.name} …", trang_thai="parsing", phan_tram=20)
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
        if source.is_scanned and settings.ocr_enabled:
            # ── Nhận dạng chữ (US-024) ──────────────────────
            #
            # Không thay thế kết quả cũ một cách mù quáng: OCR có thể đọc ra rác
            # nếu ảnh mờ hoặc mô hình sai ngôn ngữ, và rác đi qua cổng chất
            # lượng ngay sau đây. Cái được là tài liệu scan từ chỗ **không dùng
            # được gì** thành có nội dung tìm kiếm và trích dẫn được.
            from app.adapters.extract.scanned import extract_scanned_pdf
            from app.adapters.ocr import get_ocr_provider

            ocr = get_ocr_provider()
            tong_trang = result.page_count
            step(
                f"Đang nhận dạng chữ 0/{tong_trang} trang …",
                trang_thai="ocr", phan_tram=25,
            )
            source.status = "ocr"
            source.ocr_engine = ocr.name
            session.flush()

            def bao_trang(da_xong: int, tong: int) -> None:
                # OCR chiếm khoảng 25–70% tổng thời gian của một tài liệu scan.
                step(
                    f"Đang nhận dạng chữ {da_xong}/{tong} trang …",
                    trang_thai="ocr",
                    phan_tram=25 + int(45 * da_xong / max(tong, 1)),
                )

            result = extract_scanned_pdf(path, ocr, on_page=bao_trang)
            quality = result.quality
            source.page_count = result.page_count
            source.text_quality = quality.score

        elif source.is_scanned:
            empty = len(result.scanned_pages(settings.scan_chars_per_page_threshold))
            source.status = "failed"
            source.error_code = "SCAN_NO_TEXT_LAYER"
            source.error_message = (
                f"Tệp là bản scan: {empty}/{result.page_count} trang không có lớp "
                f"văn bản, và nhận dạng chữ đang tắt (OCR_ENABLED=false). "
                f"Bật nó lên để đọc được nội dung tệp này."
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

    step(f"Đang chia đoạn ({len(result.full_text):,} ký tự) …",
         trang_thai="chunking", phan_tram=75)
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
        step(f"Đang sinh bối cảnh cho {len(chunks)} đoạn …",
             trang_thai="chunking", phan_tram=80)
        contextual = await build_prefixes(
            result.full_text, chunks, llm=llm,
            on_progress=(lambda i, n: step(f"  bối cảnh {i}/{n}")) if on_progress else None,
        )
        prefixes = contextual.prefixes
        context_seconds = contextual.seconds

    step(f"Đang lập chỉ mục {len(chunks)} đoạn …",
         trang_thai="embedding", phan_tram=85)
    source.status = "embedding"
    session.flush()

    # Nhúng trên prefix + nội dung khi có bối cảnh; hiển thị vẫn là nội dung
    # gốc. Xem `contextual.indexed_text`.
    vectors = embedder.embed_documents(
        [indexed_text(c.content, prefixes[i] if prefixes else None)
         for i, c in enumerate(chunks)]
    )

    step("Đang ghi vào cơ sở dữ liệu …", trang_thai="embedding", phan_tram=95)
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
