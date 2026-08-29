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

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ports.embedding import EmbeddingProvider
from app.ports.llm import LLMProvider, Message
from app.ports.rerank import RerankProvider
from app.services import prompt as P
from app.services.grounding import GroundingDecision, decide
from app.services.intent import chitchat_system_prompt, classify
from app.services.retrieval import ScoredChunk, retrieve
from app.services.summarize import (
    KHONG_CO_TAI_LIEU,
    KHONG_CO_TAI_LIEU_EN,
    gom_dau_tai_lieu,
)
from app.services.translate import dich_de_truy_xuat
from app.services.verifier import STRICTER_HINT, verify_answer
from app.settings import settings
from app.text.language import nhan_dien as nhan_dien_ngon_ngu

__all__ = [
    "AnswerEvent",
    "AnswerResult",
    "Citation",
    "answer_question",
    "lam_sach_lich_su",
]

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


def _ten_nguon(session: Session, chunks: list[ScoredChunk]) -> dict[uuid.UUID, str]:
    """Tên tài liệu của các đoạn sắp đưa vào ngữ cảnh.

    Một câu truy vấn cho cả lượt, không phải một câu cho mỗi đoạn: tám đoạn
    thường chỉ đến từ một hai tài liệu.

    Cần thiết vì mô hình **đọc nhãn ngữ cảnh và chép nó vào câu trả lời**. Không
    có tên thật thì nhãn là một mã băm, và câu trả lời hiện ra
    *"… (nguồn #27905960)"* — thông tin nội bộ, người dùng không dùng được.
    """
    from app.models.knowledge import Source

    ids = {c.candidate.source_id for c in chunks}
    if not ids:
        return {}

    rows = session.execute(
        select(Source.id, Source.title).where(Source.id.in_(ids))
    ).all()
    return {sid: ten for sid, ten in rows}


def _citations_for(
    blocks: list[P.ContextBlock], anh_xa: dict[int, int]
) -> list[Citation]:
    """Trích dẫn cho các marker đã dùng, mang **số hiển thị** mới.

    `anh_xa` là ánh xạ *số của đoạn trong ngữ cảnh* → *số trong câu trả lời*, do
    `P.renumber_markers` dựng. Đây là chỗ duy nhất hai hệ đánh số gặp nhau, và
    cũng là lý do việc đánh số lại không làm hỏng gì: `Citation.marker` là con
    số người đọc thấy, còn `chunk_id` bên trong vẫn trỏ về đúng đoạn của số cũ.

    Danh sách trả về xếp theo số mới, tức là theo thứ tự xuất hiện trong câu
    trả lời — cũng là thứ tự các sự kiện `citation` đi ra.
    """
    by_marker = {b.marker: b for b in blocks}
    out: list[Citation] = []
    for cu, moi in sorted(anh_xa.items(), key=lambda kv: kv[1]):
        block = by_marker.get(cu)
        if block is None:  # pragma: no cover — đã lọc ở strip_invalid_markers
            continue
        c = block.chunk.candidate
        out.append(
            Citation(
                marker=moi,
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
    search_query: str | None = None,
) -> AsyncIterator[AnswerEvent]:
    """Trả lời một câu hỏi, phát sự kiện theo thứ tự giao diện cần.

    Sự kiện cuối cùng luôn là `done`, và nó mang theo `result` để chỗ gọi lấy
    được toàn bộ kết quả mà không phải tự ghép lại từ các mẩu.

    `search_query` là câu **dùng để tìm** (đã gộp ngữ cảnh ở US-019); `question`
    vẫn là câu người dùng gõ và là thứ đưa vào prompt cùng nhận diện ngôn ngữ.
    Trước đây câu đã gộp thay thế cả hai, nên một câu hỏi tiếng Anh nối tiếp bị
    viết lại thành tiếng Việt và được trả lời bằng tiếng Việt.
    """
    started = time.perf_counter()
    history = lam_sach_lich_su(history)

    # US-037 — ngôn ngữ trả lời đi theo ngôn ngữ CÂU HỎI, không theo ngôn ngữ
    # tài liệu. Người hỏi bằng tiếng Anh về một quy chế tiếng Việt vẫn phải nhận
    # được câu trả lời đọc được, kèm số liệu trích nguyên văn.
    #
    # Nhận diện trước cả bước định tuyến ý định, vì lời chào cũng cần trả lời
    # đúng ngôn ngữ — "hello" mà đáp "Chào bạn!" thì hỏng ngay câu đầu tiên.
    ngon_ngu = nhan_dien_ngon_ngu(question)

    yield {"type": "meta", "model": llm.name, "is_local": llm.is_local,
           "language": ngon_ngu}

    # ── Định tuyến ý định (US-066), nếu bật ─────────────
    if settings.intent_routing_enabled:
        intent, how = await classify(
            question, llm=llm, use_llm_fallback=settings.intent_use_llm_fallback
        )
        yield {"type": "intent", "intent": intent, "decided_by": how}

        if intent == "chitchat":
            # Không chạy truy xuất — đó là toàn bộ lý do bước này tồn tại.
            # Và vì không truy xuất nên **không có đoạn tài liệu nào** được gửi
            # đi, chỉ có câu chào. Cảnh báo phải nói đúng mức đó.
            if not llm.is_local:
                yield {
                    "type": "external_call",
                    "model": llm.name,
                    "includes_documents": False,
                }

            pieces: list[str] = []
            async for piece in llm.stream(
                chitchat_system_prompt(ngon_ngu),
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

        if intent == "summarize":
            # ── Câu hỏi về TOÀN BỘ tài liệu (US-069) ────────
            #
            # Không truy xuất, và cố ý không đi qua cổng ngưỡng τ. Lý do đầy đủ
            # ở `app/services/summarize.py`; tóm lại: "tóm tắt tài liệu của tôi"
            # không chứa từ nội dung nào của tài liệu, nên đi đường truy xuất là
            # bảo đảm nhận về "không tìm thấy thông tin này".
            yield {"type": "status", "stage": "reading"}
            doan = await asyncio.to_thread(
                gom_dau_tai_lieu,
                session,
                notebook_id=notebook_id,
                source_ids=source_ids,
            )

            if not doan:
                # Không có tài liệu thì nói thẳng, chứ không để mô hình tự nghĩ
                # ra một bản tóm tắt.
                trong = (
                    KHONG_CO_TAI_LIEU_EN if ngon_ngu == "en" else KHONG_CO_TAI_LIEU
                )
                yield {"type": "token", "text": trong}
                elapsed = int((time.perf_counter() - started) * 1000)
                result = AnswerResult(
                    answer=trong, kind="no_answer", citations=[],
                    decision=None, model_used="", latency_ms=elapsed,
                )
                yield {"type": "done", "result": result,
                       "answer_kind": "no_answer", "latency_ms": elapsed}
                return

            blocks = P.build_context(doan, _ten_nguon(session, doan))
            system = P.build_summarize_system_prompt(ngon_ngu)
            user = P.build_user_prompt(question, blocks)

            if not llm.is_local:
                yield {"type": "external_call", "model": llm.name,
                       "includes_documents": True}

            yield {"type": "status", "stage": "generating"}
            pieces = []
            async for piece in llm.stream(
                system,
                [{"role": "user", "content": user}],
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            ):
                pieces.append(piece)
                yield {"type": "token", "text": piece}

            raw = "".join(pieces).strip()
            valid = {b.marker for b in blocks}
            cleaned, dropped = P.strip_invalid_markers(raw, valid)
            cleaned, so_moi = P.renumber_markers(cleaned)
            citations = _citations_for(blocks, so_moi)
            if cleaned != raw:
                yield {"type": "replace", "text": cleaned}
            for c in citations:
                yield c.as_event()

            elapsed = int((time.perf_counter() - started) * 1000)
            result = AnswerResult(
                answer=cleaned,
                # `grounded` chứ không phải một loại riêng: bản tóm tắt DỰA
                # TRÊN tài liệu và có trích dẫn kiểm chứng được, đúng nghĩa của
                # nhãn này. Thêm một giá trị mới còn phải nới ràng buộc CHECK
                # dưới cơ sở dữ liệu — loại lỗi đã cắn hai lần trong đồ án.
                kind="grounded",
                citations=citations,
                decision=None,
                model_used=llm.name,
                latency_ms=elapsed,
                dropped_markers=dropped,
            )
            yield {"type": "done", "result": result, "answer_kind": "grounded",
                   "latency_ms": elapsed}
            return

    # ── Truy xuất ───────────────────────────────────────
    #
    # `retrieve` và `decide` là mã ĐỒNG BỘ và tốn CPU: nhúng câu hỏi, rồi
    # cross-encoder chấm hàng chục cặp. Gọi thẳng trong một async generator thì
    # chúng khoá vòng lặp sự kiện, và hậu quả nặng hơn vẻ ngoài của nó:
    #
    # * Mọi sự kiện đã `yield` trước đó nằm kẹt trong bộ đệm cho tới khi khối
    #   chặn chạy xong — đo được: cả tám sự kiện của một lượt hỏi cùng đến ở
    #   giây thứ 22, tức là streaming không hề chảy và nhãn "đang tìm trong tài
    #   liệu" không bao giờ kịp hiện.
    # * Cả tiến trình ngừng phục vụ mọi request khác trong ngần ấy giây.
    #
    # `to_thread` đẩy phần chặn sang luồng riêng. Phiên SQLAlchemy đi theo, và
    # điều đó an toàn ở đây vì mỗi lượt hỏi có phiên riêng và không luồng nào
    # dùng chung nó cùng lúc — thứ SQLAlchemy cấm là dùng ĐỒNG THỜI, không phải
    # dùng lần lượt từ hai luồng.
    # Câu hỏi khác ngôn ngữ tài liệu thì dịch TRƯỚC KHI truy xuất — US-037.
    #
    # Không có bước này thì tính năng song ngữ chỉ đúng một nửa: đo thật cho
    # thấy "What are the graduation requirements?" chỉ được 0.1428 trên đúng tài
    # liệu chứa câu trả lời, nên cổng ngưỡng chặn lại và người dùng luôn nhận
    # "không tìm thấy". Xem `app/services/translate.py`.
    #
    # Chỉ đổi câu dùng để TÌM. Câu gốc vẫn là thứ đưa cho mô hình sinh câu trả
    # lời, nên câu trả lời vẫn bằng tiếng của người hỏi.
    cau_tim = search_query or question
    if settings.translate_query_enabled:
        cau_tim, da_dich = await dich_de_truy_xuat(question, llm=llm, ngon_ngu=ngon_ngu)
        if da_dich:
            yield {"type": "condensed", "query": cau_tim}

    yield {"type": "status", "stage": "retrieving"}
    retrieval = await asyncio.to_thread(
        retrieve,
        session,
        cau_tim,
        notebook_id=notebook_id,
        embedder=embedder,
        owner_id=owner_id,
        source_ids=source_ids,
    )

    # ── Xếp hạng lại và cổng ngưỡng ─────────────────────
    yield {"type": "status", "stage": "reranking"}
    decision = await asyncio.to_thread(decide, cau_tim, retrieval, reranker=reranker)

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
        tu_choi = P.no_answer_text(ngon_ngu)
        yield {"type": "token", "text": tu_choi}
        result = AnswerResult(
            answer=tu_choi,
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
    system = P.build_grounded_system_prompt(ngon_ngu)
    chunks_dung, bi_bo = _vua_ngan_sach(decision.chunks, system, question, history)
    if bi_bo:
        log.info(
            "Bỏ %d đoạn xếp hạng thấp cho vừa cửa sổ %d token", bi_bo,
            settings.llm_context_tokens,
        )
        yield {"type": "context_trimmed", "dropped": bi_bo, "kept": len(chunks_dung)}
    blocks = P.build_context(chunks_dung, _ten_nguon(session, chunks_dung))
    user = P.build_user_prompt(question, blocks)
    messages: list[Message] = [*(history or []), {"role": "user", "content": user}]

    # Báo dữ liệu rời khỏi máy NGAY TRƯỚC lượt gọi thật sự gửi nó đi.
    #
    # Không gắn vào `meta` ở đầu luồng: lúc đó chưa biết có gọi mô hình hay
    # không, và đường từ chối thì **không gọi**. Gắn sớm là nói với người dùng
    # rằng tài liệu của họ đã đi ra ngoài trong khi thật ra không có gì đi cả —
    # một cảnh báo sai về quyền riêng tư còn tệ hơn không cảnh báo, vì nó dạy
    # người ta bỏ qua những cảnh báo đúng.
    if not llm.is_local:
        yield {"type": "external_call", "model": llm.name, "includes_documents": True}

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

    # Đánh số lại về 1, 2, 3… theo thứ tự đọc. Số của mô hình là vị trí đoạn
    # trong ngữ cảnh, và nó nhảy cóc theo thứ hạng rerank.
    cleaned, so_moi = P.renumber_markers(cleaned)
    citations = _citations_for(blocks, so_moi)

    # Giao diện đang hiện `raw` — bản mô hình vừa gõ ra, còn nguyên marker bịa
    # và còn đánh số theo ngữ cảnh. Không gửi bản thay thế thì thứ người dùng
    # đọc trên màn hình khác với thứ được lưu, và sau khi tải lại trang câu trả
    # lời tự đổi số dưới chân họ.
    if cleaned != raw:
        yield {"type": "replace", "text": cleaned}

    for c in citations:
        yield c.as_event()

    elapsed = int((time.perf_counter() - started) * 1000)
    # Mô hình có thể tự trả lời câu từ chối dù cổng ngưỡng đã cho qua — khi đó
    # phải ghi đúng `answer_kind` để thống kê ở US-041 không bị lệch.
    kind: AnswerKind = "no_answer" if P.is_no_answer(cleaned) else "grounded"

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


def _uoc_token(text: str) -> int:
    return int(len(text) / settings.llm_chars_per_token) + 1


def _vua_ngan_sach(
    chunks: list[ScoredChunk],
    system: str,
    question: str,
    history: list[Message] | None,
) -> tuple[list[ScoredChunk], int]:
    """Bỏ bớt đoạn xếp hạng thấp nhất cho tới khi prompt vừa cửa sổ ngữ cảnh.

    Luôn giữ ít nhất một đoạn: cổng ngưỡng đã kết luận là có căn cứ, nên thà
    trả lời từ đoạn tốt nhất còn hơn im lặng vì ngân sách. Đoạn được sắp theo
    điểm rerank giảm dần (hợp đồng của `decide`), nên cắt đuôi là cắt đúng
    phần ít liên quan nhất.
    """
    ngan_sach = settings.llm_context_tokens - settings.llm_max_tokens
    co_dinh = _uoc_token(system) + _uoc_token(question) + 64
    co_dinh += sum(_uoc_token(m["content"]) for m in history or [])

    giu: list[ScoredChunk] = []
    dung = co_dinh
    for c in chunks:
        gia = _uoc_token(c.candidate.content) + 32
        if giu and dung + gia > ngan_sach:
            break
        giu.append(c)
        dung += gia
    return giu, len(chunks) - len(giu)


def lam_sach_lich_su(history: list[Message] | None) -> list[Message] | None:
    """Xoá marker `[n]` khỏi các câu trả lời cũ trong lịch sử.

    Số marker chỉ có nghĩa trong lượt đã sinh ra nó. Để nguyên thì mô hình
    chép lại `[2]` của lượt trước, và ở lượt này `[2]` là một đoạn khác —
    marker "hợp lệ" mà trỏ sai, `strip_invalid_markers` không bắt được.

    Công khai vì đường hỏi ra ngoài (`app/services/external.py`) cũng đưa lịch
    sử cho mô hình, và ở đó marker cũ còn vô nghĩa hơn: lượt hỏi ngoài không có
    trích dẫn nào để `[2]` trỏ tới.
    """
    if not history:
        return history
    return [
        {**m, "content": P.strip_all_markers(m["content"])}
        if m["role"] == "assistant" else m
        for m in history
    ]


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
