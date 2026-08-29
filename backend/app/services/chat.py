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
from app.services.external import answer_externally

__all__ = ["ask", "ask_external"]

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
    asker_id: uuid.UUID | None = None,
    source_ids: list[uuid.UUID] | None = None,
    luu_lich_su: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Chạy một lượt hỏi đáp đầy đủ, phát sự kiện cho giao diện.

    `owner_id` và `asker_id` trả lời hai câu hỏi khác nhau, và đường chia sẻ là
    chỗ chúng tách đôi:

    * `owner_id` — **được đọc tài liệu của ai**. Đây là hàng rào của tầng truy
      xuất (`repositories/retrieval.py`), và nó luôn là chủ sở hữu notebook.
    * `asker_id` — **hội thoại này thuộc về ai**. Người mở một liên kết chia sẻ
      rồi hỏi sẽ đọc tài liệu của chủ notebook, nhưng phiên sinh ra là của họ.

    `luu_lich_su=False` chạy một lượt không để lại dấu vết nào: không phiên,
    không tin nhắn, và cũng không có lượt nào trước đó để gộp nên bước condense
    bị bỏ qua luôn.
    """
    if not luu_lich_su:
        async for event in answer_question(
            session,
            question,
            notebook_id=notebook_id,
            embedder=embedder,
            reranker=reranker,
            llm=llm,
            owner_id=owner_id,
            source_ids=source_ids,
        ):
            yield event
        return

    if chat_session is None:
        if asker_id is None:
            raise ValueError("Lưu lịch sử thì phải biết phiên mới thuộc về ai.")
        chat_session = repo.create_session(
            session, notebook_id, asker_id, question, source_ids
        )
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
        question,
        notebook_id=notebook_id,
        embedder=embedder,
        reranker=reranker,
        llm=llm,
        owner_id=owner_id,
        source_ids=source_ids or chat_session.scope_source_ids,
        # Câu đã gộp chỉ để TÌM; câu gốc mới là thứ đưa cho mô hình.
        search_query=search_query if condensed else None,
        # Mô hình thấy các lượt trước để giữ mạch ("nói rõ hơn ý 2"); marker
        # cũ được lọc và ngân sách ngữ cảnh cắt bớt nếu quá dài (`answer.py`).
        history=history,
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


async def ask_external(
    session: Session,
    question: str,
    *,
    chat_session: ChatSession,
    user_id: uuid.UUID,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
) -> AsyncIterator[dict[str, Any]]:
    """Một lượt hỏi ra ngoài tài liệu, có ngữ cảnh hội thoại — US-032, US-019.

    Cùng hình dạng với `ask`, chỉ khác ở chỗ không truy xuất gì: lấy lịch sử,
    gộp câu hỏi thành dạng đứng một mình, rồi giao cho `answer_externally`.

    Vì sao đường này cũng cần condense: câu người dùng gõ đi thẳng cho mô hình
    (nó đã có lịch sử để hiểu), nhưng **khoá cache** thì không được phép là
    *"viết bằng Python"*. Bản ghi cache sống nhiều ngày và dùng chung cho mọi
    phiên của người đó, nên khoá của nó phải tự nó có nghĩa.
    """
    history = repo.recent_turns(session, chat_session.id)

    standalone, condensed = await condense_question(question, history, llm=llm)
    if condensed:
        yield {"type": "condensed", "query": standalone}

    async for event in answer_externally(
        session,
        question,
        user_id=user_id,
        embedder=embedder,
        llm=llm,
        chat_session=chat_session,
        history=history,
        cache_question=standalone if condensed else None,
    ):
        yield event
