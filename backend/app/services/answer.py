"""Sinh câu trả lời có trích dẫn — US-012, US-013, US-014.

Toàn bộ bộ não hội tụ ở đây::

    câu hỏi
      ↓  truy xuất lai + RRF                    (US-010)
      ↓  xếp hạng lại + cổng ngưỡng τ           (US-011, US-031)
      ├─ đủ căn cứ  → dựng prompt có đánh số → sinh → tách marker → trích dẫn
      └─ không đủ   → câu từ chối cố định, KHÔNG gọi mô hình

Nhánh từ chối **không gọi mô hình ngôn ngữ**. Đó là một quyết định có chủ ý:
đã biết tài liệu không chứa câu trả lời thì để mô hình tự diễn đạt lời từ chối
chỉ tạo cơ hội cho nó nói thêm điều gì đó nghe hợp lý mà không có căn cứ. Câu
từ chối là hằng số, và bộ đánh giá ở US-013 AC-3 đếm nó bằng so khớp chuỗi.

Streaming là hợp đồng, không phải tối ưu: hàm này là một async generator phát
ra sự kiện theo đúng thứ tự giao diện cần (`SPEC-v1.md` §7.1).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.ports.embedding import EmbeddingProvider
from app.ports.llm import LLMProvider, Message
from app.ports.rerank import RerankProvider
from app.services import prompt as P
from app.services.grounding import GroundingDecision, decide
from app.services.intent import CHITCHAT_SYSTEM_PROMPT, classify
from app.services.retrieval import ScoredChunk, retrieve
from app.services.verifier import STRICTER_HINT, verify_answer
from app.settings import settings

__all__ = ["AnswerEvent", "AnswerResult", "Citation", "answer_question"]

log = logging.getLogger(__name__)

AnswerKind = Literal[
    "grounded", "no_answer", "external", "cached_external", "chitchat"
]


@dataclass(frozen=True, slots=True)
class Citation:
    """Một trích dẫn đã xác định — cầu nối tới toạ độ trên trang."""

    marker: int
    chunk_id: int
    source_id: uuid.UUID
    page_no: int | None
    char_start: int
    char_end: int
    snippet: str
    heading_path: str | None = None

    def as_event(self) -> dict[str, Any]:
        """Payload sự kiện SSE `citation` theo `SPEC-v1.md` §7.1."""
        return {
            "type": "citation",
            "marker": self.marker,
            "chunk_id": self.chunk_id,
            "source_id": str(self.source_id),
            "page": self.page_no,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "snippet": self.snippet,
            "heading_path": self.heading_path,
        }


@dataclass
class AnswerResult:
    answer: str
    kind: AnswerKind
    citations: list[Citation]
    decision: GroundingDecision | None
    model_used: str
    latency_ms: int
    dropped_markers: list[int] = field(default_factory=list)
    """Marker mô hình bịa ra và đã bị loại — US-014 AC-5. Ghi log để theo dõi
    tần suất; nó là một chỉ báo sớm cho chất lượng prompt."""

    verified: bool | None = None
    """Kết quả kiểm định (US-063). `None` khi bộ kiểm bị tắt."""

    retries: int = 0
    """Số lần sinh lại vì kiểm định không đạt — chi phí của dòng F ablation."""


AnswerEvent = dict[str, Any]

# Độ dài đoạn trích lưu kèm mỗi trích dẫn. Bản chụp này là thứ giữ cho chip
# trích dẫn còn hiển thị được sau khi nguồn bị xoá (US-020 AC-4).
SNIPPET_CHARS = 400


def _citations_for(blocks: list[P.ContextBlock], markers: list[int]) -> list[Citation]:
    by_marker = {b.marker: b for b in blocks}
    out: list[Citation] = []
    for m in markers:
        block = by_marker.get(m)
        if block is None:  # pragma: no cover — đã lọc ở strip_invalid_markers
            continue
        c = block.chunk.candidate
        out.append(
            Citation(
                marker=m,
                chunk_id=c.chunk_id,
                source_id=c.source_id,
                page_no=c.page_no,
                char_start=c.char_start,
                char_end=c.char_end,
                snippet=c.content[:SNIPPET_CHARS],
                heading_path=c.heading_path,
            )
        )
    return out


async def answer_question(
    session: Session,
    question: str,
    *,
    notebook_id: uuid.UUID,
    embedder: EmbeddingProvider,
    reranker: RerankProvider,
    llm: LLMProvider,
    owner_id: uuid.UUID | None = None,
    source_ids: list[uuid.UUID] | None = None,
    history: list[Message] | None = None,
) -> AsyncIterator[AnswerEvent]:
    """Trả lời một câu hỏi, phát sự kiện theo thứ tự giao diện cần.

    Sự kiện cuối cùng luôn là `done`, và nó mang theo `result` để chỗ gọi lấy
    được toàn bộ kết quả mà không phải tự ghép lại từ các mẩu.
    """
    started = time.perf_counter()

    yield {"type": "meta", "model": llm.name, "is_local": llm.is_local}

    # ── Định tuyến ý định (US-066), nếu bật ─────────────
    if settings.intent_routing_enabled:
        intent, how = await classify(
            question, llm=llm, use_llm_fallback=settings.intent_use_llm_fallback
        )
        yield {"type": "intent", "intent": intent, "decided_by": how}

        if intent == "chitchat":
            # Không chạy truy xuất — đó là toàn bộ lý do bước này tồn tại.
            pieces: list[str] = []
            async for piece in llm.stream(
                CHITCHAT_SYSTEM_PROMPT,
                [*(history or []), {"role": "user", "content": question}],
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            ):
                pieces.append(piece)
                yield {"type": "token", "text": piece}

            elapsed = int((time.perf_counter() - started) * 1000)
            result = AnswerResult(
                answer="".join(pieces).strip(),
                kind="chitchat",
                citations=[],
                decision=None,
                model_used=llm.name,
                latency_ms=elapsed,
            )
            yield {"type": "done", "result": result, "answer_kind": "chitchat",
                   "latency_ms": elapsed}
            return

    # ── Truy xuất ───────────────────────────────────────
    yield {"type": "status", "stage": "retrieving"}
    retrieval = retrieve(
        session,
        question,
        notebook_id=notebook_id,
        embedder=embedder,
        owner_id=owner_id,
        source_ids=source_ids,
    )

    # ── Xếp hạng lại và cổng ngưỡng ─────────────────────
    yield {"type": "status", "stage": "reranking"}
    decision = decide(question, retrieval, reranker=reranker)

    if not decision.grounded:
        elapsed = int((time.perf_counter() - started) * 1000)
        yield {
            "type": "no_answer",
            "top_score": decision.top_score,
            "threshold": decision.threshold,
            "reason": decision.reason,
        }
        # Câu từ chối vẫn phát ra dưới dạng token để giao diện chỉ có một
        # đường hiển thị duy nhất.
        yield {"type": "token", "text": P.NO_ANSWER_TEXT}
        result = AnswerResult(
            answer=P.NO_ANSWER_TEXT,
            kind="no_answer",
            citations=[],
            decision=decision,
            model_used="",  # không gọi mô hình nào
            latency_ms=elapsed,
        )
        yield {"type": "done", "result": result, "answer_kind": "no_answer",
               "latency_ms": elapsed}
        return

    # ── Sinh câu trả lời ────────────────────────────────
    blocks = P.build_context(decision.chunks)
    system = P.build_grounded_system_prompt()
    user = P.build_user_prompt(question, blocks)
    messages: list[Message] = [*(history or []), {"role": "user", "content": user}]

    yield {"type": "status", "stage": "generating"}

    pieces: list[str] = []
    async for piece in llm.stream(
        system,
        messages,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    ):
        pieces.append(piece)
        yield {"type": "token", "text": piece}

    raw = "".join(pieces).strip()

    # ── Kiểm định (US-063), nếu bật ─────────────────────
    verification = None
    retries = 0
    if settings.verifier_enabled:
        yield {"type": "status", "stage": "verifying"}
        verification = await verify_answer(raw, blocks, llm=llm)
        yield {
            "type": "verification",
            "passed": verification.passed,
            "issue": verification.issue,
        }

        while verification.needs_retry and retries < settings.verifier_max_retry:
            retries += 1
            retry_messages: list[Message] = [
                *messages,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": STRICTER_HINT.format(
                        issue=verification.issue or "có khẳng định không được chứng thực"
                    ),
                },
            ]
            yield {"type": "status", "stage": "regenerating"}

            again: list[str] = []
            async for piece in llm.stream(
                system, retry_messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            ):
                again.append(piece)

            raw = "".join(again).strip()
            # Giao diện không rút lại được thứ đã hiện, nên gửi bản thay thế
            # thay vì gửi thêm token.
            yield {"type": "replace", "text": raw, "attempt": retries + 1}
            verification = await verify_answer(raw, blocks, llm=llm)
            yield {
                "type": "verification",
                "passed": verification.passed,
                "issue": verification.issue,
                "attempt": retries + 1,
            }

    # ── Hậu xử lý trích dẫn ─────────────────────────────
    valid = {b.marker for b in blocks}
    cleaned, dropped = P.strip_invalid_markers(raw, valid)
    if dropped:
        log.warning("Mô hình bịa ra marker không tồn tại: %s", dropped)

    citations = _citations_for(blocks, P.used_markers(cleaned))
    for c in citations:
        yield c.as_event()

    elapsed = int((time.perf_counter() - started) * 1000)
    # Mô hình có thể tự trả lời câu từ chối dù cổng ngưỡng đã cho qua — khi đó
    # phải ghi đúng `answer_kind` để thống kê ở US-041 không bị lệch.
    kind: AnswerKind = "no_answer" if cleaned.startswith(P.NO_ANSWER_TEXT) else "grounded"

    result = AnswerResult(
        answer=cleaned,
        kind=kind,
        citations=citations,
        decision=decision,
        model_used=llm.name,
        latency_ms=elapsed,
        dropped_markers=dropped,
        verified=verification.passed if verification else None,
        retries=retries,
    )
    yield {
        "type": "done",
        "result": result,
        "answer_kind": kind,
        "latency_ms": elapsed,
        "dropped_markers": dropped,
        "verified": result.verified,
        "retries": retries,
    }


def collect_text(events: list[AnswerEvent]) -> str:
    """Ghép các mẩu token — tiện ích cho test và cho CLI."""
    return "".join(e["text"] for e in events if e["type"] == "token")


def final_result(events: list[AnswerEvent]) -> AnswerResult:
    """Lấy `AnswerResult` từ sự kiện `done`."""
    for e in reversed(events):
        if e["type"] == "done":
            return e["result"]
    raise ValueError("Luồng sự kiện không có sự kiện 'done'")


def chunks_of(decision: GroundingDecision) -> list[ScoredChunk]:
    return decision.chunks
