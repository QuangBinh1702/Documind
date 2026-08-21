"""Điều phối một lượt hội thoại — US-018, US-019.

Ghép các mảnh thành một lượt hoàn chỉnh::

    câu hỏi
      ↓  lấy N lượt gần nhất
      ↓  condense thành câu hỏi độc lập        (US-019)
      ↓  trả lời có căn cứ                     (US-012 → US-014)
      ↓  lưu câu hỏi, câu trả lời và trích dẫn (US-018)

Điểm đáng chú ý: **câu hỏi đã gộp chỉ dùng để truy xuất**, còn thứ lưu vào
lịch sử và hiển thị lại cho người dùng là **câu hỏi gốc**. Lưu câu đã gộp sẽ
làm lịch sử đọc không giống thứ người dùng thực sự đã gõ, và lượt condense
tiếp theo sẽ gộp trên một bản đã bị viết lại — sai số cộng dồn qua từng lượt.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat import ChatSession
from app.ports.embedding import EmbeddingProvider
from app.ports.llm import LLMProvider
from app.ports.rerank import RerankProvider
from app.repositories import chat as repo
from app.services.answer import AnswerResult, answer_question
from app.services.condense import condense_question

__all__ = ["ask"]

log = logging.getLogger(__name__)


async def ask(
    session: Session,
    question: str,
    *,
    notebook_id: uuid.UUID,
    chat_session: ChatSession | None,
    embedder: EmbeddingProvider,
    reranker: RerankProvider,
    llm: LLMProvider,
    owner_id: uuid.UUID | None = None,
    source_ids: list[uuid.UUID] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Chạy một lượt hỏi đáp đầy đủ, phát sự kiện cho giao diện."""
    if chat_session is None:
        chat_session = repo.create_session(session, notebook_id, question, source_ids)
        yield {
            "type": "session",
            "session_id": str(chat_session.id),
            "title": chat_session.title,
        }

    history = repo.recent_turns(session, chat_session.id)
    repo.save_question(session, chat_session, question)

    # ── Gộp câu hỏi nếu nó phụ thuộc ngữ cảnh ───────────
    search_query, condensed = await condense_question(question, history, llm=llm)
    if condensed:
        yield {"type": "condensed", "query": search_query}

    # ── Trả lời ─────────────────────────────────────────
    result: AnswerResult | None = None
    async for event in answer_question(
        session,
        search_query,
        notebook_id=notebook_id,
        embedder=embedder,
        reranker=reranker,
        llm=llm,
        owner_id=owner_id,
        source_ids=source_ids or chat_session.scope_source_ids,
    ):
        if event["type"] == "done":
            result = event["result"]
        yield event

    # ── Lưu lại ─────────────────────────────────────────
    if result is not None:
        message = repo.save_answer(
            session,
            chat_session,
            result,
            condensed_query=search_query if condensed else None,
        )
        yield {
            "type": "saved",
            "message_id": str(message.id),
            "session_id": str(chat_session.id),
        }
