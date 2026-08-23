"""Quản lý notebook và nguồn tài liệu — US-005, US-006.

Mọi endpoint ở đây đi qua `notebook_cua_toi`, nên INV-4 được giữ ở một chỗ duy
nhất thay vì rải điều kiện `user_id` khắp nơi và quên mất một chỗ.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from app.adapters.storage import minio_store
from app.api.deps import CurrentUser, DbSession, notebook_cua_toi
from app.models.chat import ChatSession
from app.models.knowledge import Notebook, Source
from app.services.upload import UploadError, nhan_tep
from app.settings import settings
from app.workers.tasks import xu_ly_nguon

router = APIRouter(tags=["notebooks"])
log = logging.getLogger(__name__)

# FastAPI đọc tham số tải tệp qua giá trị mặc định. Gọi `File()` ngay trong chữ
# ký hàm là mẫu chuẩn của FastAPI nhưng vi phạm quy tắc "không gọi hàm ở giá trị
# mặc định", nên đưa ra một hằng ở cấp module.
_FILE = File(...)


class TaoNotebook(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class DoiTenNotebook(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class NguonResponse(BaseModel):
    id: uuid.UUID
    title: str
    original_name: str
    kind: str
    size_bytes: int
    page_count: int | None
    status: str
    progress: int
    text_quality: float | None
    error_code: str | None
    error_message: str | None
    in_scope: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotebookResponse(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    source_count: int
    ready_count: int


def _tom_tat(session, nb: Notebook) -> NotebookResponse:
    tong = session.scalar(
        select(func.count()).select_from(Source).where(Source.notebook_id == nb.id)
    )
    xong = session.scalar(
        select(func.count()).select_from(Source)
        .where(Source.notebook_id == nb.id, Source.status == "ready")
    )
    return NotebookResponse(
        id=nb.id, title=nb.title, created_at=nb.created_at, updated_at=nb.updated_at,
        source_count=tong or 0, ready_count=xong or 0,
    )


# ══════════════════════════════════════════════════════
# Notebook — US-005
# ══════════════════════════════════════════════════════


@router.get("/notebooks", response_model=list[NotebookResponse],
            summary="Danh sách notebook của tôi")
def list_notebooks(user: CurrentUser, session: DbSession) -> list[NotebookResponse]:
    rows = session.scalars(
        select(Notebook).where(Notebook.user_id == user.id)
        .order_by(Notebook.updated_at.desc())
    ).all()
    return [_tom_tat(session, nb) for nb in rows]


@router.post("/notebooks", response_model=NotebookResponse, status_code=201,
             summary="Tạo notebook")
def create_notebook(
    req: TaoNotebook, user: CurrentUser, session: DbSession
) -> NotebookResponse:
    nb = Notebook(user_id=user.id, title=req.title.strip())
    session.add(nb)
    session.flush()
    return _tom_tat(session, nb)


@router.get("/notebooks/{notebook_id}", response_model=NotebookResponse,
            summary="Một notebook")
def get_notebook(
    notebook_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> NotebookResponse:
    return _tom_tat(session, notebook_cua_toi(session, user, notebook_id))


@router.patch("/notebooks/{notebook_id}", response_model=NotebookResponse,
              summary="Đổi tên notebook")
def rename_notebook(
    notebook_id: uuid.UUID, req: DoiTenNotebook, user: CurrentUser, session: DbSession
) -> NotebookResponse:
    nb = notebook_cua_toi(session, user, notebook_id)
    nb.title = req.title.strip()
    nb.updated_at = datetime.now(nb.updated_at.tzinfo) if nb.updated_at else None
    session.flush()
    return _tom_tat(session, nb)


@router.delete("/notebooks/{notebook_id}", status_code=204,
               summary="Xoá notebook và toàn bộ dữ liệu của nó")
def delete_notebook(
    notebook_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> None:
    """US-005 AC-4 — xoá cả source, chunk, vector, phiên chat và tệp trên MinIO.

    Tệp trên kho xoá TRƯỚC khi xoá bản ghi. Ngược lại thì một lỗi ở bước xoá tệp
    sẽ để lại tệp mồ côi mà không còn gì trong cơ sở dữ liệu trỏ tới nó — không
    ai biết chúng tồn tại để dọn.
    """
    nb = notebook_cua_toi(session, user, notebook_id)
    da_xoa = minio_store.xoa_theo_tien_to(f"{user.id}/{nb.id}/")

    # Chunk, source_text và message_citations đi theo ON DELETE CASCADE của
    # lược đồ; phiên chat phải xoá tường minh vì nó không treo dưới sources.
    session.execute(delete(ChatSession).where(ChatSession.notebook_id == nb.id))
    session.delete(nb)
    session.flush()
    log.info("Đã xoá notebook %s và %d tệp trên kho", nb.id, da_xoa)


# ══════════════════════════════════════════════════════
# Nguồn tài liệu — US-006
# ══════════════════════════════════════════════════════


@router.get("/notebooks/{notebook_id}/sources", response_model=list[NguonResponse],
            summary="Danh sách nguồn trong notebook")
def list_sources(
    notebook_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> list[NguonResponse]:
    nb = notebook_cua_toi(session, user, notebook_id)
    rows = session.scalars(
        select(Source).where(Source.notebook_id == nb.id)
        .order_by(Source.created_at.desc())
    ).all()
    return [NguonResponse.model_validate(s) for s in rows]


@router.post("/notebooks/{notebook_id}/sources", response_model=NguonResponse,
             status_code=202, summary="Tải tài liệu lên")
async def upload_source(
    notebook_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    background: BackgroundTasks,
    file: UploadFile = _FILE,
) -> NguonResponse:
    """Nhận tệp, trả `202` ngay, xử lý ở worker.

    Trích xuất và nhúng một tài liệu dài mất hàng chục giây. Giữ kết nối HTTP
    mở suốt chừng ấy là cách chắc chắn để trình duyệt hoặc proxy cắt ngang giữa
    chừng, và người dùng không biết việc đã xong hay chưa. Trả `202` cùng một
    bản ghi `queued` để giao diện có thứ để theo dõi tiến trình.
    """
    nb = notebook_cua_toi(session, user, notebook_id)

    # Đọc trước phần đầu để chặn tệp quá lớn mà không nuốt hết dữ liệu (AC-3).
    gioi_han = settings.max_file_mb * 1024 * 1024
    data = await file.read(gioi_han + 1)
    if len(data) > gioi_han:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Tệp vượt giới hạn {settings.max_file_mb} MB.",
        )

    try:
        ket_qua = nhan_tep(
            session, nb, filename=file.filename or "khong-ten", data=data
        )
    except UploadError as exc:
        ma = {
            "TOO_MANY_SOURCES": status.HTTP_409_CONFLICT,
            "FILE_TOO_LARGE": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        }.get(exc.code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        raise HTTPException(status_code=ma, detail=exc.message) from exc

    source = session.get(Source, ket_qua.source_id)
    phan_hoi = NguonResponse.model_validate(source)

    # Commit NGAY, không đợi phiên của request tự đóng.
    #
    # Worker mở phiên riêng và đọc lại chính bản ghi này. Thứ tự giữa lúc dọn
    # dependency và lúc chạy background task không được bảo đảm, nên dựa vào nó
    # là dựa vào may rủi — và khi hụt thì worker chỉ ghi "không tìm thấy nguồn"
    # rồi im lặng, tài liệu kẹt ở `queued` mãi mãi.
    session.commit()

    background.add_task(xu_ly_nguon, str(ket_qua.source_id))
    return phan_hoi


@router.delete("/notebooks/{notebook_id}/sources/{source_id}", status_code=204,
               summary="Xoá một nguồn")
def delete_source(
    notebook_id: uuid.UUID, source_id: uuid.UUID,
    user: CurrentUser, session: DbSession,
) -> None:
    nb = notebook_cua_toi(session, user, notebook_id)
    src = session.get(Source, source_id)
    if src is None or src.notebook_id != nb.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy nguồn.")

    minio_store.xoa_tep(src.storage_key)
    session.delete(src)
    session.flush()


@router.patch("/notebooks/{notebook_id}/sources/{source_id}",
              response_model=NguonResponse, summary="Bật/tắt nguồn khỏi phạm vi hỏi")
def toggle_source(
    notebook_id: uuid.UUID, source_id: uuid.UUID, in_scope: bool,
    user: CurrentUser, session: DbSession,
) -> NguonResponse:
    """US-038 — chọn hỏi trong tài liệu nào."""
    nb = notebook_cua_toi(session, user, notebook_id)
    src = session.get(Source, source_id)
    if src is None or src.notebook_id != nb.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy nguồn.")
    src.in_scope = in_scope
    session.flush()
    return NguonResponse.model_validate(src)


def _unused() -> Any:  # pragma: no cover
    return None
