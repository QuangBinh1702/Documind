"""Trả lời bằng kiến thức ngoài tài liệu — US-032, US-033, US-034, US-035.

🔴 **Bất biến INV-3 sống ở đây.** Câu trả lời sinh ra trên đường này **không
bao giờ** được ghi vào `source_chunks`. Nó vào `external_answer_cache`, một
namespace tách biệt mà đường truy xuất tài liệu không đọc.

`SPEC.md` §J.6 gọi đây là điều thứ hai quyết định thành bại, và nêu đúng lý do:
*cách làm sai lại đơn giản hơn cách làm đúng*. Nhét câu trả lời của mô hình vào
cùng chỉ mục với tài liệu là vài dòng mã và trông có vẻ tiện — nhưng rồi hệ
thống sẽ trích dẫn chính nội dung nó tự bịa ra, và toàn bộ giá trị của tính
năng trích dẫn sụp đổ.

Ba ràng buộc khác, mỗi cái vì một lý do riêng:

* **Không tự động gọi ra ngoài** (US-032 AC-1). Người dùng phải bấm nút. Điều
  này giữ ranh giới giữa "có căn cứ" và "tham khảo" luôn là một hành động có ý
  thức, không phải một thứ xảy ra sau lưng họ.
* **Không có trích dẫn** (US-033 AC-3). Không có nguồn nào để trỏ tới, nên gắn
  chip là nói dối.
* **Hạn mức theo ngày** (US-035 AC-1). Lượt phục vụ từ cache không tính.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession
from app.ports.embedding import EmbeddingProvider
from app.ports.llm import LLMProvider, Message
from app.repositories import chat as repo
from app.services.answer import lam_sach_lich_su
from app.settings import settings

__all__ = [
    "EXTERNAL_SYSTEM_PROMPT",
    "EXTERNAL_WARNING",
    "ExternalResult",
    "QuotaExceeded",
    "answer_externally",
]

log = logging.getLogger(__name__)

# Nhãn cảnh báo cố định — US-033 AC-2. Đi kèm câu trả lời ở mọi nơi nó xuất
# hiện, kể cả trong tệp xuất ra (US-033 AC-4).
EXTERNAL_WARNING = (
    "⚠ Câu trả lời này KHÔNG dựa trên tài liệu của bạn. "
    "Nguồn: mô hình ngôn ngữ bên ngoài. Chưa được kiểm chứng."
)

EXTERNAL_SYSTEM_PROMPT = """Bạn trả lời câu hỏi bằng kiến thức chung của mình.

Người dùng đã được thông báo rõ rằng câu trả lời này KHÔNG dựa trên tài liệu \
của họ, nên không cần nhắc lại điều đó.

QUY TẮC
1. Trả lời ngắn gọn, đi thẳng vào câu hỏi.
2. Bám vào mạch hội thoại phía trên. Câu hỏi nối tiếp như "viết bằng Python đi" \
hay "ngắn hơn được không" nói về đúng việc vừa bàn ở lượt trước — KHÔNG hỏi lại \
người dùng xem họ muốn gì khi lịch sử đã trả lời điều đó.
3. Nếu không chắc chắn, hãy nói rõ là không chắc thay vì đoán.
4. KHÔNG tạo ra số trích dẫn dạng [1], [2] — không có tài liệu nào để trỏ tới.
5. Trả lời bằng ngôn ngữ của câu hỏi cuối; mặc định là tiếng Việt."""


class QuotaExceeded(RuntimeError):
    """Vượt hạn mức gọi ra ngoài trong ngày — US-035 AC-1."""

    def __init__(self, used: int, limit: int) -> None:
        super().__init__(
            f"Đã dùng hết {used}/{limit} lượt hỏi ra ngoài trong 24 giờ qua. "
            f"Hạn mức sẽ được đặt lại sau khi các lượt cũ quá 24 giờ."
        )
        self.used = used
        self.limit = limit


@dataclass
class ExternalResult:
    answer: str
    from_cache: bool
    model_used: str
    latency_ms: int
    cached_question: str | None = None
    """Câu hỏi gốc đã sinh ra bản ghi cache. Hiển thị cho người dùng tự đối
    chiếu xem có đúng ý mình không — US-034 AC-3. Không có bước này thì một
    lần khớp gần đúng sẽ âm thầm trả lời sai câu hỏi."""

    similarity: float | None = None


async def answer_externally(
    session: Session,
    question: str,
    *,
    user_id: uuid.UUID,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    use_cache: bool = True,
    chat_session: ChatSession | None = None,
    history: list[Message] | None = None,
    cache_question: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Hỏi mô hình ngoài, có tra cache trước.

    Chỉ được gọi khi người dùng đã bấm nút — tầng gọi chịu trách nhiệm bảo
    đảm điều đó (US-032 AC-1).

    Có `chat_session` thì câu hỏi và câu trả lời được ghi vào lịch sử phiên với
    `answer_kind` là `external`/`cached_external` — để tải lại trang vẫn thấy,
    và để thống kê US-041 đếm được. Không trích dẫn nào được ghi, vì không có.

    `history` là các lượt trước của phiên, đưa cho mô hình để câu hỏi nối tiếp
    còn hiểu được (US-019). Không có nó thì *"viết bằng Python"* sau một lượt
    hỏi về C++ là một câu vô nghĩa, và mô hình đáp lại bằng cách hỏi ngược người
    dùng xem họ muốn viết chương trình gì — đúng lỗi đã gặp thật.

    `cache_question` là dạng **đứng một mình** của câu hỏi, dùng cho việc nhúng
    và cho khoá cache. Nhúng nguyên văn *"viết bằng Python"* cho ra một vector
    chẳng đại diện cho điều gì, nên bản ghi cache vừa vô dụng vừa nguy hiểm: một
    câu hỏi nối tiếp khác của ngày mai sẽ khớp vào đúng nó.
    """
    started = time.perf_counter()
    cau_doc_lap = cache_question or question

    yield {"type": "meta", "model": llm.name, "is_local": llm.is_local, "external": True}
    yield {"type": "warning", "text": EXTERNAL_WARNING}

    if chat_session is not None:
        repo.save_question(session, chat_session, question)

    # Nhúng là việc chặn (CPU hoặc HTTP đồng bộ) — đẩy ra luồng khác để không
    # treo event loop của mọi request khác trong lúc chờ.
    vector = await asyncio.to_thread(embedder.embed_query, cau_doc_lap)

    # ── Tra cache trước khi tiêu một lượt quota ─────────
    if use_cache:
        hit = repo.find_cached_answer(session, user_id, vector)
        if hit is not None:
            entry, similarity = hit
            entry.hit_count += 1
            repo.log_external_call(session, user_id, from_cache=True)
            session.flush()

            elapsed = int((time.perf_counter() - started) * 1000)
            yield {
                "type": "cache_hit",
                "cached_question": entry.question,
                "similarity": round(similarity, 4),
                "hit_count": entry.hit_count,
            }
            yield {"type": "token", "text": entry.answer}
            ket = ExternalResult(
                answer=entry.answer,
                from_cache=True,
                model_used=entry.model_used,
                latency_ms=elapsed,
                cached_question=entry.question,
                similarity=similarity,
            )
            _luu(session, chat_session, ket, "cached_external")
            yield {
                "type": "done",
                "result": ket,
                "answer_kind": "cached_external",
                "latency_ms": elapsed,
            }
            return

    # ── Hạn mức chỉ áp cho lượt gọi THẬT ────────────────
    used = repo.calls_today(session, user_id)
    if used >= settings.external_calls_per_day:
        raise QuotaExceeded(used, settings.external_calls_per_day)

    yield {"type": "status", "stage": "calling_external"}

    # Marker `[n]` của các lượt grounded trước bị bóc khỏi lịch sử: ở lượt hỏi
    # ngoài không có trích dẫn nào để chúng trỏ tới, nên để nguyên chỉ dạy mô
    # hình chép lại một con số dẫn đi đâu không ai biết (US-033 AC-3).
    messages: list[Message] = [
        *(lam_sach_lich_su(history) or []),
        {"role": "user", "content": question},
    ]

    pieces: list[str] = []
    async for piece in llm.stream(
        EXTERNAL_SYSTEM_PROMPT,
        messages,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    ):
        pieces.append(piece)
        yield {"type": "token", "text": piece}

    answer = "".join(pieces).strip()

    # 🔴 INV-3: ghi vào external_answer_cache, KHÔNG BAO GIỜ vào source_chunks.
    if answer and use_cache:
        repo.store_cached_answer(
            session, user_id, cau_doc_lap, vector, answer, llm.name
        )
    repo.log_external_call(session, user_id, from_cache=False)
    session.flush()

    elapsed = int((time.perf_counter() - started) * 1000)
    ket = ExternalResult(
        answer=answer, from_cache=False, model_used=llm.name, latency_ms=elapsed
    )
    _luu(session, chat_session, ket, "external")
    yield {
        "type": "done",
        "result": ket,
        "answer_kind": "external",
        "latency_ms": elapsed,
    }


def _luu(
    session: Session,
    chat_session: ChatSession | None,
    ket: ExternalResult,
    kind: str,
) -> None:
    if chat_session is None or not ket.answer:
        return
    session.add(
        ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=ket.answer,
            answer_kind=kind,
            model_used=ket.model_used,
            latency_ms=ket.latency_ms,
        )
    )
    chat_session.updated_at = func.now()
    session.flush()
