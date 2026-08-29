"""API cho hội thoại được chia sẻ — US-039.

Ba nhóm endpoint, và ranh giới giữa chúng là điểm mấu chốt:

* `/api/notebooks/{id}/share` — **chủ sở hữu** tạo và thu hồi liên kết.
* `/api/shared/{token}/…` bằng `GET` — **đọc**. Không đòi đăng nhập: đây là thứ
  làm cho một liên kết chia sẻ có ích.
* `/api/shared/{token}/ask` và các đường lịch sử — **hỏi**. Đòi đăng nhập, và
  hội thoại sinh ra thuộc về người hỏi, không phải chủ notebook.

Vì sao hỏi thì phải đăng nhập
------------------------------
Bản đầu của US-039 cho người lạ hỏi mà không cần tài khoản, và mọi chi phí tính
cho chủ sở hữu. Điều đó biến việc phát một liên kết thành việc phát hạn mức của
mình cho bất kỳ ai chuyển tiếp được đường link. Bắt đăng nhập giải quyết cả ba
chuyện cùng lúc: chi phí tính đúng người, câu hỏi của người xem có chỗ để lưu,
và người xem xem lại được hội thoại của chính mình. Xem quyết định 0004.

Nhóm `shared` cố ý **không** dùng lại router notebook với một dependency quyền
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

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.adapters.embedding import get_embedding_provider
from app.adapters.llm import get_llm_provider
from app.adapters.rerank import get_rerank_provider
from app.adapters.storage import minio_store
from app.api.deps import CurrentUser, DbSession, notebook_cua_toi
from app.models.base import session_scope
from app.models.chat import ChatMessage, ChatSession
from app.models.knowledge import Source, SourceChunk, SourceText
from app.services.chat import ask
from app.services.rate_limit import RateLimited, kiem_tra
from app.services.share import (
    DaMo,
    ShareError,
    lay_lien_ket,
    lay_notebook_chia_se,
    tao_hoac_lay,
    thu_hoi,
)
from app.settings import Mode, settings

router = APIRouter(tags=["share"])
log = logging.getLogger(__name__)


class LienKetChiaSe(BaseModel):
    token: str
    duong_dan: str = Field(description="Đường tương đối để giao diện ghép thành URL đầy đủ")
    con_hieu_luc: bool
    session_id: uuid.UUID | None = None


def _ra(token: str, session_id: uuid.UUID | None) -> LienKetChiaSe:
    return LienKetChiaSe(
        token=token, duong_dan=f"/xem/{token}", con_hieu_luc=True, session_id=session_id
    )


# ══════════════════════════════════════════════════════
# Chủ sở hữu
# ══════════════════════════════════════════════════════


def _phien_de_chia_se(
    session, notebook_id: uuid.UUID, user_id: uuid.UUID, session_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Kiểm rằng phiên sắp chia sẻ đúng là phiên của tôi trong notebook này.

    Thiếu phép kiểm này thì chủ một notebook bất kỳ phát được liên kết đọc
    **mọi** hội thoại trong hệ thống, chỉ cần đoán một `session_id`.
    """
    if session_id is None:
        return None
    phien = session.get(ChatSession, session_id)
    if phien is None or phien.notebook_id != notebook_id or phien.user_id != user_id:
        raise HTTPException(404, "Không tìm thấy phiên hội thoại.")
    return phien.id


class TaoLienKet(BaseModel):
    session_id: uuid.UUID | None = Field(
        default=None,
        description="Phiên hội thoại cần chia sẻ. Bỏ trống để chia sẻ cả notebook.",
    )


@router.post("/notebooks/{notebook_id}/share", response_model=LienKetChiaSe,
             summary="Tạo hoặc lấy liên kết chia sẻ")
def tao_lien_ket(
    notebook_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    req: TaoLienKet | None = None,
) -> LienKetChiaSe:
    nb = notebook_cua_toi(session, user, notebook_id)
    phien_id = _phien_de_chia_se(
        session, nb.id, user.id, req.session_id if req else None
    )
    lien_ket = tao_hoac_lay(session, nb, phien_id)
    return _ra(lien_ket.token, lien_ket.session_id)


@router.get("/notebooks/{notebook_id}/share", response_model=LienKetChiaSe | None,
            summary="Liên kết chia sẻ hiện có")
def xem_lien_ket(
    notebook_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    session_id: uuid.UUID | None = None,
) -> LienKetChiaSe | None:
    nb = notebook_cua_toi(session, user, notebook_id)
    phien_id = _phien_de_chia_se(session, nb.id, user.id, session_id)
    lien_ket = lay_lien_ket(session, nb, phien_id)
    return _ra(lien_ket.token, lien_ket.session_id) if lien_ket else None


@router.delete("/notebooks/{notebook_id}/share", status_code=204,
               summary="Thu hồi liên kết chia sẻ")
def thu_hoi_lien_ket(
    notebook_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    session_id: uuid.UUID | None = None,
) -> None:
    nb = notebook_cua_toi(session, user, notebook_id)
    phien_id = _phien_de_chia_se(session, nb.id, user.id, session_id)
    thu_hoi(session, nb, phien_id)


# ══════════════════════════════════════════════════════
# Người xem — đọc, không cần đăng nhập
# ══════════════════════════════════════════════════════


def _mo(session, token: str) -> DaMo:
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


class TrichDanChiaSe(BaseModel):
    marker: int
    chunk_id: int | None
    snippet: str
    page: int | None
    deleted: bool


class TinNhanChiaSe(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    answer_kind: str | None
    citations: list[TrichDanChiaSe]


class NotebookChiaSe(BaseModel):
    title: str
    nguon: list[NguonChiaSe]
    phien_id: uuid.UUID | None
    phien_tieu_de: str | None
    tin_nhan: list[TinNhanChiaSe]


def _tin_nhan(session, session_id: uuid.UUID) -> list[TinNhanChiaSe]:
    """Hội thoại của một phiên, cùng hình dạng với `/api/sessions/{id}/messages`.

    Không trả `model_used` hay `latency_ms`: người xem cần đọc được câu trả lời
    và kiểm chứng trích dẫn, chứ không cần biết máy chủ của người khác chạy mô
    hình nào và chậm bao nhiêu.
    """
    rows = session.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.seq)
    ).all()
    return [
        TinNhanChiaSe(
            id=m.id,
            role=m.role,
            content=m.content,
            answer_kind=m.answer_kind,
            citations=[
                TrichDanChiaSe(
                    marker=c.marker,
                    chunk_id=c.chunk_id,
                    snippet=c.snippet,
                    page=c.page_no,
                    # chunk_id NULL nghĩa là nguồn đã bị xoá — US-020 AC-4.
                    deleted=c.chunk_id is None,
                )
                for c in m.citations
            ],
        )
        for m in rows
    ]


@router.get("/shared/{token}", response_model=NotebookChiaSe,
            summary="Xem một hội thoại được chia sẻ")
def xem_notebook(token: str, session: DbSession) -> NotebookChiaSe:
    """AC-2 — đọc được hội thoại và nguồn, không sửa được gì.

    Không trả `storage_key`, `error_message` hay chủ sở hữu: người xem cần biết
    tài liệu nào có mặt để kiểm chứng trích dẫn, chứ không cần biết chúng nằm ở
    đâu trên máy chủ hay ai đã tải lên.
    """
    da_mo = _mo(session, token)
    rows = session.scalars(
        select(Source)
        .where(Source.notebook_id == da_mo.notebook.id, Source.status == "ready")
        .order_by(Source.created_at.desc())
    ).all()
    return NotebookChiaSe(
        title=da_mo.notebook.title,
        nguon=[
            NguonChiaSe(
                id=s.id, title=s.title, kind=s.kind,
                page_count=s.page_count, status=s.status,
            )
            for s in rows
        ],
        phien_id=da_mo.phien.id if da_mo.phien else None,
        phien_tieu_de=da_mo.phien.title if da_mo.phien else None,
        tin_nhan=_tin_nhan(session, da_mo.phien.id) if da_mo.phien else [],
    )


@router.get("/shared/{token}/citations/{chunk_id}", summary="Đoạn trích dẫn")
def trich_dan_chia_se(token: str, chunk_id: int, session: DbSession) -> dict[str, Any]:
    """Cùng dữ liệu với `/api/citations/{id}`, nhưng chỉ trong notebook đã chia sẻ.

    Kiểm `notebook_id` chứ không chỉ kiểm token: thiếu điều kiện ấy thì một
    liên kết chia sẻ hợp lệ trở thành cửa đọc **mọi** đoạn tri thức trong hệ
    thống, chỉ cần đoán số.
    """
    da_mo = _mo(session, token)
    chunk = session.scalar(
        select(SourceChunk).where(
            SourceChunk.id == chunk_id,
            SourceChunk.notebook_id == da_mo.notebook.id,
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


def _nguon_trong(session, da_mo: DaMo, source_id: uuid.UUID) -> Source:
    src = session.get(Source, source_id)
    if src is None or src.notebook_id != da_mo.notebook.id:
        raise HTTPException(404, "Không tìm thấy nguồn.")
    return src


@router.get("/shared/{token}/sources/{source_id}/file",
            summary="Tệp gốc của một nguồn được chia sẻ")
def tep_chia_se(token: str, source_id: uuid.UUID, session: DbSession) -> Response:
    """US-015 AC-1 → AC-3 cho người xem: mở đúng trang và tô sáng đúng chỗ.

    Đây là chỗ liên kết chia sẻ đi xa nhất, nên nó đáng được nói thẳng: người
    cầm liên kết đọc được **toàn văn** tài liệu, không chỉ những đoạn đã được
    trích dẫn. Đó là điều kiện để trích dẫn kiểm chứng được — một đoạn văn tách
    khỏi ngữ cảnh quanh nó thì không kiểm chứng được gì — và nó không mở rộng
    phạm vi trên thực tế, vì người xem vốn đã hỏi được câu bất kỳ và nhận về
    nguyên văn các đoạn khớp.

    Mỗi lượt xem vẫn là một lượt giải mã token, nên thu hồi liên kết là chặn
    được ngay. Xem thêm chú thích ở endpoint tương ứng trong `notebooks.py` về
    lý do không ký URL tạm cho MinIO.
    """
    da_mo = _mo(session, token)
    src = _nguon_trong(session, da_mo, source_id)

    if src.storage_key.startswith("cli://"):
        raise HTTPException(404, "Nguồn này nạp bằng CLI, không có bản lưu trên máy chủ.")

    try:
        data = minio_store.lay_tep(src.storage_key)
    except Exception as exc:
        log.warning("Không đọc được tệp %s: %s", src.storage_key, exc)
        raise HTTPException(404, "Không tìm thấy tệp gốc của nguồn này.") from exc

    return Response(
        content=data,
        media_type=src.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{src.id}"',
            # `private` dù không có phiên đăng nhập: URL mang token chia sẻ, và
            # một proxy dùng chung không được phép phục vụ lại nó cho người khác
            # sau khi liên kết đã bị thu hồi.
            "Cache-Control": "private, max-age=3600",
        },
    )


class VanBanChiaSe(BaseModel):
    source_id: uuid.UUID
    title: str
    kind: str
    page_count: int | None
    full_text: str
    page_map: list[dict]


@router.get("/shared/{token}/sources/{source_id}/text", response_model=VanBanChiaSe,
            summary="Toàn văn của một nguồn được chia sẻ")
def van_ban_chia_se(
    token: str, source_id: uuid.UUID, session: DbSession
) -> VanBanChiaSe:
    """Chính chuỗi mà offset của chunk trỏ vào (INV-1), để tô sáng cắt được."""
    da_mo = _mo(session, token)
    src = _nguon_trong(session, da_mo, source_id)

    van_ban = session.get(SourceText, src.id)
    if van_ban is None:
        raise HTTPException(404, "Nguồn này chưa được xử lý xong.")

    return VanBanChiaSe(
        source_id=src.id,
        title=src.title,
        kind=src.kind,
        page_count=src.page_count,
        full_text=van_ban.full_text,
        page_map=van_ban.page_map,
    )


# ══════════════════════════════════════════════════════
# Người xem — hỏi, phải đăng nhập
# ══════════════════════════════════════════════════════


class HoiChiaSe(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: Mode | None = None
    session_id: uuid.UUID | None = Field(
        default=None,
        description="Phiên của chính người hỏi để nói tiếp. Bỏ trống thì mở phiên mới.",
    )


class PhienCuaToi(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: str


@router.get("/shared/{token}/my-sessions", response_model=list[PhienCuaToi],
            summary="Hội thoại của chính tôi trong notebook được chia sẻ")
def phien_cua_toi(token: str, user: CurrentUser, session: DbSession) -> list[PhienCuaToi]:
    """Những gì tôi đã hỏi qua liên kết này, để mở lại lần sau.

    Lọc theo `user_id` **và** `notebook_id`: liên kết mở ra một notebook, nên nó
    không được là đường đọc hội thoại của tôi ở những notebook khác.
    """
    da_mo = _mo(session, token)
    rows = session.scalars(
        select(ChatSession)
        .where(
            ChatSession.notebook_id == da_mo.notebook.id,
            ChatSession.user_id == user.id,
        )
        .order_by(ChatSession.updated_at.desc())
    ).all()
    return [
        PhienCuaToi(id=s.id, title=s.title, updated_at=s.updated_at.isoformat())
        for s in rows
    ]


@router.get("/shared/{token}/my-sessions/{session_id}/messages",
            response_model=list[TinNhanChiaSe],
            summary="Tin nhắn trong một hội thoại của chính tôi")
def tin_nhan_cua_toi(
    token: str, session_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> list[TinNhanChiaSe]:
    da_mo = _mo(session, token)
    phien = session.get(ChatSession, session_id)
    if (
        phien is None
        or phien.notebook_id != da_mo.notebook.id
        or phien.user_id != user.id
    ):
        raise HTTPException(404, "Không tìm thấy phiên hội thoại.")
    return _tin_nhan(session, phien.id)


@router.post("/shared/{token}/ask", summary="Hỏi trong một notebook được chia sẻ")
async def hoi_chia_se(
    token: str, req: HoiChiaSe, user: CurrentUser, request: Request
) -> StreamingResponse:
    """AC-2 — người xem hỏi đáp được, sau khi đăng nhập.

    Hai id đi hai đường khác nhau, và đó là toàn bộ ý nghĩa của endpoint này:

    * `owner_id` là **chủ notebook** — hàng rào của tầng truy xuất, để câu hỏi
      chỉ chạm tới tài liệu nằm trong notebook được chia sẻ;
    * `asker_id` là **người đang hỏi** — phiên hội thoại sinh ra thuộc về họ và
      hiện trong lịch sử của họ, không lẫn vào lịch sử của chủ notebook.

    Trần số câu hỏi mỗi giờ vẫn giữ theo liên kết và theo IP. Đăng nhập làm cho
    việc lạm dụng có danh tính, nhưng không làm nó tốn công hơn, mà mỗi lượt vẫn
    tốn một lần nhúng, một lần xếp hạng lại và một lượt gọi mô hình trên máy chủ
    của chủ notebook.
    """
    # Chốt id ngay tại đây: phiên ORM của `CurrentUser` đóng khi response kết
    # thúc, còn luồng SSE sống lâu hơn thế — xem chú thích ở `api/chat.py`.
    user_id = user.id
    ip = request.client.host if request.client else "?"
    try:
        kiem_tra("share-ask", token, limit=settings.share_asks_per_hour, window_seconds=3600)
        kiem_tra("share-ask-ip", ip, limit=settings.share_asks_per_hour * 3,
                 window_seconds=3600)
    except RateLimited as exc:
        raise HTTPException(
            429, str(exc), headers={"Retry-After": str(exc.retry_after)}
        ) from exc

    async def stream() -> AsyncIterator[str]:
        with session_scope() as session:
            try:
                da_mo = lay_notebook_chia_se(session, token)
            except ShareError as exc:
                yield _sse({"type": "error", "code": "NOT_FOUND", "message": str(exc)})
                return

            chat_session = None
            if req.session_id:
                chat_session = session.get(ChatSession, req.session_id)
                if (
                    chat_session is None
                    or chat_session.notebook_id != da_mo.notebook.id
                    or chat_session.user_id != user_id
                ):
                    yield _sse(
                        {"type": "error", "code": "SESSION_NOT_FOUND",
                         "message": "Phiên hội thoại không tồn tại."}
                    )
                    return

            try:
                async for event in ask(
                    session,
                    req.question,
                    notebook_id=da_mo.notebook.id,
                    chat_session=chat_session,
                    embedder=get_embedding_provider(),
                    reranker=get_rerank_provider(),
                    llm=get_llm_provider(req.mode),
                    owner_id=da_mo.owner_id,
                    asker_id=user_id,
                    source_ids=None,
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


def _sse(event: dict[str, Any]) -> str:
    goi = {k: v for k, v in event.items() if k != "result"}
    return f"data: {json.dumps(goi, ensure_ascii=False, default=str)}\n\n"
