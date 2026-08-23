"""API hội thoại với streaming SSE — `SPEC-v1.md` §7.1.

Router chỉ điều phối, xác thực đầu vào và định dạng sự kiện. Toàn bộ nghiệp vụ
nằm ở tầng service (Definition of Done D4).

Hai điểm về SSE đáng ghi lại:

* Sự kiện `done` mang theo `AnswerResult`, một đối tượng Python không tuần tự
  hoá thẳng thành JSON được. Nó bị lược bỏ trước khi gửi, chỉ giữ những trường
  giao diện thật sự cần.
* Phiên cơ sở dữ liệu phải sống suốt luồng stream. Đóng nó sớm — điều dễ xảy ra
  khi dùng dependency thông thường của FastAPI — làm mọi truy cập lười phía sau
  đổ vỡ giữa chừng.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.adapters.embedding import get_embedding_provider
from app.adapters.llm import get_llm_provider
from app.adapters.rerank import get_rerank_provider
from app.api.deps import CurrentUser, DbSession
from app.models.base import session_scope
from app.models.chat import ChatMessage, ChatSession
from app.models.knowledge import Notebook, Source, SourceChunk
from app.services.chat import ask
from app.services.export import KhongCoFont, xuat
from app.services.external import QuotaExceeded, answer_externally
from app.settings import Mode, settings

router = APIRouter(tags=["chat"])
log = logging.getLogger(__name__)

# Những khoá không tuần tự hoá được hoặc không cần cho giao diện.
_INTERNAL_KEYS = {"result"}


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    notebook_id: uuid.UUID
    session_id: uuid.UUID | None = None
    mode: Mode | None = None
    source_ids: list[uuid.UUID] | None = None


class ExternalRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    notebook_id: uuid.UUID
    confirmed: bool = False
    """US-032 AC-4 — ở Privacy Mode phải xác nhận thêm một lần, vì thao tác này
    gửi câu hỏi ra dịch vụ bên ngoài."""


def _loi_nguoi_doc_duoc(exc: Exception) -> dict[str, Any]:
    """Đổi một ngoại lệ thành thông báo gửi ra ngoài được — US-028 AC-4.

    **Không đưa `str(exc)` ra giao diện.** Với lỗi cơ sở dữ liệu, SQLAlchemy nhét
    cả câu lệnh và toàn bộ tham số vào thông báo, nên nó đổ nguyên văn nội dung
    tin nhắn, khoá chính và cấu trúc bảng lên màn hình người dùng. Đã gặp thật:
    một `CheckViolation` làm cả câu INSERT hiện ra trong khung chat.

    Đó vừa là rò rỉ thông tin — kẻ tấn công đọc được tên bảng, tên cột, ràng
    buộc — vừa là thứ người dùng không làm gì được với nó. Traceback đầy đủ
    thuộc về log máy chủ; ra ngoài chỉ đưa một câu nói được và một mã để đối
    chiếu với log.
    """
    ma = type(exc).__name__
    if isinstance(exc, RuntimeError):
        # Adapter mô hình ném `RuntimeError` với câu đã soạn sẵn cho người dùng
        # — hết hạn mức, sai khoá API, không kết nối được máy chủ cục bộ.
        return {"type": "error", "code": ma, "message": str(exc)}
    return {
        "type": "error",
        "code": ma,
        "message": "Có lỗi khi xử lý câu hỏi. Hãy thử lại; nếu vẫn lỗi thì "
                   "xem log máy chủ để biết chi tiết.",
    }


def _sse(event: dict[str, Any]) -> str:
    payload = {k: v for k, v in event.items() if k not in _INTERNAL_KEYS}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _notebook_cua(session, notebook_id: uuid.UUID, user_id: uuid.UUID) -> Notebook:
    """Lấy notebook của chính người đang đăng nhập, hoặc 404.

    Notebook của người khác trả về **404**, không phải 403 — xem chú thích ở
    `app/api/deps.py`.
    """
    nb = session.get(Notebook, notebook_id)
    if nb is None or nb.user_id != user_id:
        raise HTTPException(404, "Không tìm thấy notebook.")
    return nb


@router.post("/chat/ask", summary="Hỏi đáp có căn cứ, trả về luồng SSE")
async def chat_ask(req: AskRequest, user: CurrentUser) -> StreamingResponse:
    # Chốt `user.id` NGAY tại đây thay vì mang đối tượng `User` vào trong luồng.
    #
    # `CurrentUser` lấy từ một phiên do FastAPI quản lý, và phiên đó đóng khi
    # response kết thúc. Luồng SSE thì sống lâu hơn thế, nên mọi truy cập lười
    # trên đối tượng ORM ở giữa chừng sẽ nổ. Một UUID thì không có vòng đời nào.
    user_id = user.id

    async def stream() -> AsyncIterator[str]:
        with session_scope() as session:
            try:
                nb = _notebook_cua(session, req.notebook_id, user_id)
            except HTTPException as e:
                yield _sse({"type": "error", "code": "NOT_FOUND", "message": e.detail})
                return

            chat_session = None
            if req.session_id:
                chat_session = session.get(ChatSession, req.session_id)
                if chat_session is None or chat_session.notebook_id != nb.id:
                    yield _sse(
                        {"type": "error", "code": "SESSION_NOT_FOUND",
                         "message": "Phiên hội thoại không tồn tại."}
                    )
                    return

            try:
                async for event in ask(
                    session,
                    req.question,
                    notebook_id=nb.id,
                    chat_session=chat_session,
                    embedder=get_embedding_provider(),
                    reranker=get_rerank_provider(),
                    llm=get_llm_provider(req.mode),
                    owner_id=user_id,
                    source_ids=req.source_ids,
                ):
                    yield _sse(event)
            except Exception as exc:
                log.exception("Lỗi khi trả lời câu hỏi")
                yield _sse(_loi_nguoi_doc_duoc(exc))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/ask-external", summary="Hỏi bằng kiến thức ngoài tài liệu")
async def chat_ask_external(req: ExternalRequest, user: CurrentUser) -> StreamingResponse:
    """US-032 — chỉ chạy khi người dùng chủ động bấm nút.

    Không có đường nào tự động gọi tới endpoint này; hệ thống chỉ hiển thị nút
    mời sau khi cổng ngưỡng kết luận tài liệu không đủ căn cứ.
    """
    user_id = user.id

    async def stream() -> AsyncIterator[str]:
        with session_scope() as session:
            try:
                _notebook_cua(session, req.notebook_id, user_id)
            except HTTPException as e:
                yield _sse({"type": "error", "code": "NOT_FOUND", "message": e.detail})
                return

            if settings.default_mode == "privacy" and not req.confirmed:
                yield _sse(
                    {"type": "confirm_required",
                     "message": "Thao tác này sẽ gửi câu hỏi của bạn ra dịch vụ bên ngoài."}
                )
                return

            try:
                async for event in answer_externally(
                    session,
                    req.question,
                    user_id=user_id,
                    embedder=get_embedding_provider(),
                    llm=get_llm_provider("fast"),
                ):
                    yield _sse(event)
            except QuotaExceeded as exc:
                yield _sse({"type": "error", "code": "QUOTA_EXCEEDED", "message": str(exc)})
            except Exception as exc:
                log.exception("Lỗi khi hỏi ra ngoài")
                yield _sse(_loi_nguoi_doc_duoc(exc))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Dữ liệu phụ trợ cho giao diện ──────────────────────


def _phien_cua_toi(session, session_id: uuid.UUID, user_id: uuid.UUID) -> ChatSession:
    """Phiên hội thoại của chính người đăng nhập, hoặc 404.

    Đi qua `notebooks` để về `users`: `chat_sessions` không mang `user_id`, chủ
    sở hữu của nó là chủ sở hữu của notebook chứa nó.
    """
    phien = session.scalar(
        select(ChatSession)
        .join(Notebook, Notebook.id == ChatSession.notebook_id)
        .where(ChatSession.id == session_id, Notebook.user_id == user_id)
    )
    if phien is None:
        raise HTTPException(404, "Không tìm thấy phiên hội thoại.")
    return phien


@router.get("/citations/{chunk_id}", summary="Chi tiết một trích dẫn")
def get_citation(chunk_id: int, user: CurrentUser, session: DbSession) -> dict[str, Any]:
    """US-015 — dữ liệu để mở đúng vị trí và tô sáng."""
    chunk = session.scalar(
        select(SourceChunk)
        .join(Notebook, Notebook.id == SourceChunk.notebook_id)
        .where(SourceChunk.id == chunk_id, Notebook.user_id == user.id)
    )
    # Cùng một câu trả lời cho "không tồn tại" và "của người khác". Đoạn trích
    # dẫn mang nguyên văn nội dung tài liệu, nên phân biệt được hai ca này là đủ
    # để dò nội dung của người khác từng mẩu một.
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
            "id": str(source.id),
            "title": source.title,
            "kind": source.kind,
            "pages": source.page_count,
        },
    }


@router.get("/sessions", summary="Lịch sử hội thoại của một notebook")
def list_sessions(
    notebook_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> list[dict[str, Any]]:
    _notebook_cua(session, notebook_id, user.id)
    sessions = session.scalars(
        select(ChatSession)
        .where(ChatSession.notebook_id == notebook_id)
        .order_by(ChatSession.updated_at.desc())
    ).all()
    return [
        {"id": str(s.id), "title": s.title, "updated_at": s.updated_at.isoformat()}
        for s in sessions
    ]


@router.get("/sessions/{session_id}/export", summary="Xuất hội thoại ra tệp")
def export_session(
    session_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    dinh_dang: Literal["md", "pdf"] = "md",
) -> Response:
    """US-040 — tải về Markdown hoặc PDF."""
    try:
        ket = xuat(session, session_id, user.id, dinh_dang)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except KhongCoFont as exc:
        # Thiếu font là lỗi cấu hình máy chủ, không phải lỗi của người dùng —
        # và thông báo phải nói được điều đó để người vận hành sửa được.
        log.error("Không xuất được PDF: %s", exc)
        raise HTTPException(503, str(exc)) from exc

    return Response(
        content=ket.noi_dung,
        media_type=ket.mime,
        headers={"Content-Disposition": f'attachment; filename="{ket.ten_tep}"'},
    )


@router.get("/sessions/{session_id}/messages", summary="Tin nhắn của một phiên")
def list_messages(
    session_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> list[dict[str, Any]]:
    """US-018 AC-3 — chip trích dẫn phải hiển thị lại đầy đủ và bấm được."""
    _phien_cua_toi(session, session_id, user.id)
    messages = session.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.seq)
    ).all()
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "answer_kind": m.answer_kind,
            "model_used": m.model_used,
            "latency_ms": m.latency_ms,
            "citations": [
                {
                    "marker": c.marker,
                    "chunk_id": c.chunk_id,
                    "snippet": c.snippet,
                    "page": c.page_no,
                    # chunk_id NULL nghĩa là nguồn đã bị xoá — US-020 AC-4.
                    "deleted": c.chunk_id is None,
                }
                for c in m.citations
            ],
        }
        for m in messages
    ]
