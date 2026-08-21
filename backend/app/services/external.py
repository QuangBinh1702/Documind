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

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.ports.embedding import EmbeddingProvider
from app.ports.llm import LLMProvider
from app.repositories import chat as repo
from app.settings import settings

__all__ = ["EXTERNAL_WARNING", "ExternalResult", "QuotaExceeded", "answer_externally"]

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
2. Nếu không chắc chắn, hãy nói rõ là không chắc thay vì đoán.
3. KHÔNG tạo ra số trích dẫn dạng [1], [2] — không có tài liệu nào để trỏ tới.
4. Trả lời bằng tiếng Việt."""


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
) -> AsyncIterator[dict[str, Any]]:
    """Hỏi mô hình ngoài, có tra cache trước.

    Chỉ được gọi khi người dùng đã bấm nút — tầng gọi chịu trách nhiệm bảo
    đảm điều đó (US-032 AC-1).
    """
    started = time.perf_counter()

    yield {"type": "meta", "model": llm.name, "is_local": llm.is_local, "external": True}
    yield {"type": "warning", "text": EXTERNAL_WARNING}

    vector = embedder.embed_query(question)

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
            yield {
                "type": "done",
                "result": ExternalResult(
                    answer=entry.answer,
                    from_cache=True,
                    model_used=entry.model_used,
                    latency_ms=elapsed,
                    cached_question=entry.question,
                    similarity=similarity,
                ),
                "answer_kind": "cached_external",
                "latency_ms": elapsed,
            }
            return

    # ── Hạn mức chỉ áp cho lượt gọi THẬT ────────────────
    used = repo.calls_today(session, user_id)
    if used >= settings.external_calls_per_day:
        raise QuotaExceeded(used, settings.external_calls_per_day)

    yield {"type": "status", "stage": "calling_external"}

    pieces: list[str] = []
    async for piece in llm.stream(
        EXTERNAL_SYSTEM_PROMPT,
        [{"role": "user", "content": question}],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    ):
        pieces.append(piece)
        yield {"type": "token", "text": piece}

    answer = "".join(pieces).strip()

    # 🔴 INV-3: ghi vào external_answer_cache, KHÔNG BAO GIỜ vào source_chunks.
    if answer and use_cache:
        repo.store_cached_answer(session, user_id, question, vector, answer, llm.name)
    repo.log_external_call(session, user_id, from_cache=False)
    session.flush()

    elapsed = int((time.perf_counter() - started) * 1000)
    yield {
        "type": "done",
        "result": ExternalResult(
            answer=answer, from_cache=False, model_used=llm.name, latency_ms=elapsed
        ),
        "answer_kind": "external",
        "latency_ms": elapsed,
    }
