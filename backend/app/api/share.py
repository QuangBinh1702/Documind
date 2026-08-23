"""API cho notebook được chia sẻ — US-039.

Hai nhóm endpoint, và ranh giới giữa chúng là điểm mấu chốt:

* `/api/notebooks/{id}/share` — **chủ sở hữu** tạo và thu hồi liên kết. Đòi đăng
  nhập như mọi endpoint khác.
* `/api/shared/{token}/…` — **người xem** đọc và hỏi. Không đòi đăng nhập, và
  không có động từ nào ngoài `GET` và một lượt `POST` để hỏi.

Nhóm thứ hai cố ý **không** dùng lại router notebook với một dependency quyền
khác. Dùng lại thì mọi endpoint mới thêm vào đó về sau sẽ tự động mở cho người
xem — kể cả endpoint xoá. Chép ra một router riêng, hẹp, khiến việc mở thêm
quyền phải là một hành động có chủ ý.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.adapters.embedding import get_embedding_provider
from app.adapters.llm import get_llm_provider
from app.adapters.rerank import get_rerank_provider
from app.api.deps import CurrentUser, DbSession, notebook_cua_toi
from app.models.base import session_scope
from app.models.knowledge import Source, SourceChunk
from app.services.chat import ask
from app.services.share import ShareError, lay_notebook_chia_se, tao_hoac_lay, thu_hoi
from app.settings import Mode

router = APIRouter(tags=["share"])
log = logging.getLogger(__name__)


class LienKetChiaSe(BaseModel):
    token: str
    duong_dan: str = Field(description="Đường tương đối để giao diện ghép thành URL đầy đủ")
    con_hieu_luc: bool


def _ra(token: str) -> LienKetChiaSe:
    return LienKetChiaSe(token=token, duong_dan=f"/xem/{token}", con_hieu_luc=True)


# ══════════════════════════════════════════════════════
# Chủ sở hữu
# ══════════════════════════════════════════════════════


@router.post("/notebooks/{notebook_id}/share", response_model=LienKetChiaSe,
             summary="Tạo hoặc lấy liên kết chia sẻ")
def tao_lien_ket(
    notebook_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> LienKetChiaSe:
    nb = notebook_cua_toi(session, user, notebook_id)
    return _ra(tao_hoac_lay(session, nb).token)


@router.get("/notebooks/{notebook_id}/share", response_model=LienKetChiaSe | None,
            summary="Liên kết chia sẻ hiện có")
def xem_lien_ket(
    notebook_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> LienKetChiaSe | None:
    from app.models.knowledge import ShareLink

    nb = notebook_cua_toi(session, user, notebook_id)
    lien_ket = session.get(ShareLink, nb.id)
    if lien_ket is None or not lien_ket.con_hieu_luc:
        return None
    return _ra(lien_ket.token)


@router.delete("/notebooks/{notebook_id}/share", status_code=204,
               summary="Thu hồi liên kết chia sẻ")
def thu_hoi_lien_ket(
    notebook_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> None:
    nb = notebook_cua_toi(session, user, notebook_id)
    thu_hoi(session, nb)


# ══════════════════════════════════════════════════════
# Người xem — không đăng nhập
# ══════════════════════════════════════════════════════


def _mo(session, token: str):
    try:
        return lay_notebook_chia_se(session, token)
    except ShareError as exc:
        # 404 cho mọi lý do — xem chú thích ở `app/services/share.py`.
        raise HTTPException(404, str(exc)) from exc


class NguonChiaSe(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    page_count: int | None
    status: str


class NotebookChiaSe(BaseModel):
    title: str
    nguon: list[NguonChiaSe]


@router.get("/shared/{token}", response_model=NotebookChiaSe,
            summary="Xem một notebook được chia sẻ")
def xem_notebook(token: str, session: DbSession) -> NotebookChiaSe:
    """AC-2 — xem được nguồn, không sửa được gì.

    Không trả `storage_key`, `error_message` hay chủ sở hữu: người xem cần biết
    tài liệu nào có mặt để hỏi, chứ không cần biết chúng nằm ở đâu trên máy chủ
    hay ai đã tải lên.
    """
    nb, _ = _mo(session, token)
    rows = session.scalars(
        select(Source)
        .where(Source.notebook_id == nb.id, Source.status == "ready")
        .order_by(Source.created_at.desc())
    ).all()
    return NotebookChiaSe(
        title=nb.title,
        nguon=[
            NguonChiaSe(
                id=s.id, title=s.title, kind=s.kind,
                page_count=s.page_count, status=s.status,
            )
            for s in rows
        ],
    )


class HoiChiaSe(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: Mode | None = None


@router.post("/shared/{token}/ask", summary="Hỏi trong một notebook được chia sẻ")
async def hoi_chia_se(token: str, req: HoiChiaSe) -> StreamingResponse:
    """AC-2 và AC-4 — hỏi được, và mọi chi phí tính cho chủ sở hữu.

    Không truyền `session_id`: hội thoại của người xem **không** được ghi vào
    lịch sử của chủ sở hữu. Người chia sẻ tài liệu không đồng nghĩa với việc
    đồng ý cho câu hỏi của người khác nằm lẫn trong lịch sử của mình.
    """

    async def stream() -> AsyncIterator[str]:
        with session_scope() as session:
            try:
                nb, owner_id = lay_notebook_chia_se(session, token)
            except ShareError as exc:
                yield _sse({"type": "error", "code": "NOT_FOUND", "message": str(exc)})
                return

            try:
                async for event in ask(
                    session,
                    req.question,
                    notebook_id=nb.id,
                    chat_session=None,
                    embedder=get_embedding_provider(),
                    reranker=get_rerank_provider(),
                    llm=get_llm_provider(req.mode),
                    owner_id=owner_id,
                    source_ids=None,
                    luu_lich_su=False,
                ):
                    yield _sse(event)
            except Exception:
                log.exception("Lỗi khi trả lời qua liên kết chia sẻ")
                yield _sse(
                    {"type": "error", "code": "INTERNAL",
                     "message": "Có lỗi khi xử lý câu hỏi. Thử lại sau."}
                )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/shared/{token}/citations/{chunk_id}", summary="Đoạn trích dẫn")
def trich_dan_chia_se(token: str, chunk_id: int, session: DbSession) -> dict[str, Any]:
    """Cùng dữ liệu với `/api/citations/{id}`, nhưng chỉ trong notebook đã chia sẻ.

    Kiểm `notebook_id` chứ không chỉ kiểm token: thiếu điều kiện ấy thì một
    liên kết chia sẻ hợp lệ trở thành cửa đọc **mọi** đoạn tri thức trong hệ
    thống, chỉ cần đoán số.
    """
    nb, _ = _mo(session, token)
    chunk = session.scalar(
        select(SourceChunk).where(
            SourceChunk.id == chunk_id, SourceChunk.notebook_id == nb.id
        )
    )
    if chunk is None:
        raise HTTPException(404, "Đoạn trích dẫn không còn tồn tại.")

    source = session.get(Source, chunk.source_id)
    return {
        "chunk_id": chunk.id,
        "content": chunk.content,
        "page_no": chunk.page_no,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "bbox": chunk.bbox,
        "heading_path": chunk.heading_path,
        "source": {
            "id": str(source.id), "title": source.title,
            "kind": source.kind, "pages": source.page_count,
        },
    }


def _sse(event: dict[str, Any]) -> str:
    goi = {k: v for k, v in event.items() if k != "result"}
    return f"data: {json.dumps(goi, ensure_ascii=False, default=str)}\n\n"
