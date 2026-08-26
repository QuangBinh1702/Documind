"""Xử lý một nguồn tài liệu sau khi đã tải lên — US-006, US-021.

    tải từ MinIO → trích xuất → cổng chất lượng → chunk → nhúng → ghi DB

Hàm này **chạy đồng bộ** trong tiến trình gọi nó. Hiện API gọi nó qua
`BackgroundTasks` của FastAPI: phản hồi `202` trả về ngay, việc nặng chạy sau
khi phiên cơ sở dữ liệu của request đã commit — thứ tự đó quan trọng, vì worker
đọc lại chính bản ghi mà request vừa tạo.

Cùng hàm này sẽ là thân của một task Celery ở US-021 khi cần chạy trên nhiều
tiến trình. Tách sẵn ra đây để lúc đó không phải viết lại logic, chỉ thêm lớp
điều phối.

Vì sao ghi tệp ra đĩa tạm thay vì xử lý thẳng trong bộ nhớ
-----------------------------------------------------------
`extract()` nhận một `Path`. PyMuPDF và python-docx đều đọc theo kiểu truy cập
ngẫu nhiên, nên đưa cho chúng một tệp thật rẻ hơn là dựng một lớp giả lập tệp
trên bộ nhớ. Tệp tạm bị xoá trong `finally`, kể cả khi trích xuất ném lỗi.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.adapters.embedding import get_embedding_provider
from app.adapters.extract import ExtractionError
from app.adapters.llm import get_llm_provider
from app.adapters.storage import minio_store
from app.models.base import session_scope
from app.models.knowledge import Source
from app.services import progress
from app.services.ingest import ingest_file
from app.settings import settings

__all__ = ["xu_ly_nguon"]

log = logging.getLogger(__name__)


def _dat_trang_thai(source_id: uuid.UUID, **truong) -> None:
    """Cập nhật trạng thái trong một phiên NGẮN của riêng nó.

    Nếu dùng chung phiên với cả quá trình xử lý thì tiến trình chỉ hiện ra khi
    mọi thứ đã xong — tức là thanh tiến trình vô dụng. Mỗi lần cập nhật là một
    transaction riêng để giao diện thấy được ngay.
    """
    with session_scope() as s:
        src = s.get(Source, source_id)
        if src is None:
            return
        for k, v in truong.items():
            setattr(src, k, v)


def xu_ly_nguon(source_id: str | uuid.UUID) -> None:
    """Xử lý một nguồn. Không ném lỗi — mọi hỏng hóc ghi vào chính bản ghi đó."""
    sid = uuid.UUID(str(source_id))

    with session_scope() as s:
        src = s.get(Source, sid)
        if src is None:
            log.warning("Không tìm thấy nguồn %s để xử lý", sid)
            return
        storage_key = src.storage_key
        original_name = src.original_name
        notebook_id = src.notebook_id
        suffix = Path(original_name).suffix or f".{src.kind}"

    # Bộ trạng thái là một CHECK constraint trong lược đồ (`SPEC-v1.md` §4.2):
    # queued · parsing · ocr · chunking · embedding · ready · failed. Đặt một
    # giá trị ngoài danh sách đó thì Postgres từ chối cả câu UPDATE — nên tải
    # tệp về và trích xuất đều nằm dưới `parsing`, và `ingest_file` chuyển tiếp
    # sang `chunking` rồi `embedding`.
    _dat_trang_thai(sid, status="parsing", progress=5)

    tmp: Path | None = None
    try:
        data = minio_store.lay_tep(storage_key)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(data)
            tmp = Path(fh.name)

        _dat_trang_thai(sid, progress=15)

        # ── Nạp mô hình, và NÓI RA là đang nạp ──────────
        #
        # Lần chạy đầu tiên phải tải khoảng 4,3 GB trọng số về. Trước đây bước
        # này im lặng: giao diện đứng ở "đang đọc 15%" suốt một phút rưỡi, và
        # mọi tài liệu xếp sau đứng ở "đang chờ 0%" mà không có lời giải thích
        # nào. Người dùng chỉ thấy một hệ thống bị treo.
        #
        # Nạp ở đây, tường minh, thay vì để nó xảy ra lặng lẽ bên trong bước
        # nhúng — nơi thanh tiến trình đã nhảy tới 85% và đứng im ở đó.
        embedder = get_embedding_provider()
        if not embedder.da_san_sang:
            progress.dat(
                sid, status="parsing", progress=15,
                message="Đang chuẩn bị mô hình (lần đầu tải khoảng 4 GB) …",
            )
            log.info("Nạp mô hình lần đầu — bước này có thể mất vài phút")
        embedder.warm()

        llm = get_llm_provider() if settings.contextual_retrieval_enabled else None

        with session_scope() as s:
            nb = s.get(Source, sid).notebook
            ket_qua = asyncio.run(
                ingest_file(
                    s, tmp,
                    notebook_title=nb.title,
                    embedder=embedder,
                    llm=llm,
                    owner_email=nb.user.email,
                    existing_source_id=sid,
                    on_progress=lambda m: log.info("[%s] %s", original_name, m),
                )
            )

        log.info(
            "Xong %s: %d đoạn, %d trang, chất lượng %.2f",
            original_name, ket_qua.chunk_count, ket_qua.page_count,
            ket_qua.quality.score,
        )

    except ExtractionError as exc:
        # `ingest_file` đã ghi mã lỗi và thông báo vào bản ghi rồi; ở đây chỉ
        # bảo đảm trạng thái không kẹt ở giữa chừng.
        log.warning("Nguồn %s hỏng: %s", original_name, exc.code)
        _dat_trang_thai(sid, status="failed", progress=100)

    except Exception as exc:
        log.exception("Lỗi không lường trước khi xử lý %s", original_name)
        _dat_trang_thai(
            sid, status="failed", progress=100,
            # Không đưa `str(exc)` ra giao diện: lỗi kho tệp hay cơ sở dữ liệu
            # mang theo địa chỉ máy chủ, tên bucket, câu SQL. Chi tiết nằm ở
            # log (dòng `log.exception` bên trên); người dùng chỉ cần biết là
            # hệ thống hỏng chứ không phải tài liệu của họ hỏng.
            error_code=type(exc).__name__,
            error_message=(
                "Lỗi hệ thống khi xử lý tài liệu. Hãy thử tải lên lại; nếu vẫn "
                f"lỗi, báo cho người vận hành kèm mã {type(exc).__name__}."
            ),
        )

    else:
        _dat_trang_thai(
            sid, status="ready", progress=100, ready_at=datetime.now(UTC)
        )

    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        log.debug("Đã dọn tệp tạm của %s (notebook %s)", original_name, notebook_id)
