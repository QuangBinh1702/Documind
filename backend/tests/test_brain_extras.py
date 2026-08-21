"""Contextual Retrieval, kiểm định câu trả lời và định tuyến ý định.

US-049, US-063, US-066 — ba story cuối của bộ não. Chúng cũng là hai dòng còn
thiếu của bảng ablation US-046: dòng **E** (`CONTEXTUAL_RETRIEVAL_ENABLED`) và
dòng **F** (`VERIFIER_ENABLED`). Ba dòng đầu ở `test_retrieval.py`, dòng **D**
(`RERANK_ENABLED`) ở `test_grounding.py`.

Mỗi tính năng ở đây đều phải **tắt được bằng cấu hình** — nếu không thì không
đo được nó đóng góp bao nhiêu, và phần phân tích ở Chương 5 chỉ còn là phỏng
đoán.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy import text as sql

from app.adapters.embedding.fake import FakeEmbeddingProvider
from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.rerank.fake import FakeRerankProvider
from app.models.base import session_scope
from app.models.knowledge import Notebook, SourceChunk, User
from app.repositories.retrieval import Candidate
from app.services import prompt as P
from app.services.answer import answer_question, final_result
from app.services.contextual import build_prefixes, indexed_text
from app.services.ingest import ingest_file
from app.services.intent import classify
from app.services.retrieval import ScoredChunk
from app.services.verifier import verify_answer
from app.settings import settings
from app.text.chunker import chunk_text

OWNER = "brain@documind.local"
NOTEBOOK = "brain-test"

DOC = """Chương I. Học phí

Điều 1. Mức thu
Mức thu được xác định theo từng năm học và công bố trước kỳ tuyển sinh.

Điều 2. Thời hạn nộp
Người học nộp trong ba mươi ngày kể từ ngày bắt đầu học kỳ.
"""


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        with session_scope() as s:
            s.execute(delete(User).where(User.email == OWNER))

    wipe()
    yield
    wipe()


class BrokenLLM(FakeLLMProvider):
    """Mô hình sập ngay ở lượt gọi đầu — dùng để kiểm chứng suy giảm êm."""

    async def stream(self, *args, **kwargs):
        raise RuntimeError("mô hình sập")
        yield  # pragma: no cover — làm cho hàm này là async generator


def _block(marker: int, content: str) -> P.ContextBlock:
    return P.ContextBlock(
        marker=marker,
        chunk=ScoredChunk(
            candidate=Candidate(
                chunk_id=marker,
                source_id=uuid.uuid4(),
                content=content,
                page_no=1,
                heading_path=None,
                char_start=0,
                char_end=len(content),
                score=0.0,
            ),
            rrf_score=1.0,
        ),
    )


def _seed(session, tmp_path, **kw):
    p = tmp_path / "hoc-phi.txt"
    p.write_text(DOC, encoding="utf-8")
    return ingest_file(
        session,
        p,
        notebook_title=NOTEBOOK,
        embedder=FakeEmbeddingProvider(dim=1024),
        owner_email=OWNER,
        **kw,
    )


def _ids(session) -> tuple[uuid.UUID, uuid.UUID]:
    user = session.scalar(select(User).where(User.email == OWNER))
    nb = session.scalar(select(Notebook).where(Notebook.user_id == user.id))
    return user.id, nb.id


# ══════════════════════════════════════════════════════
# US-049 — Contextual Retrieval
# ══════════════════════════════════════════════════════


def test_van_ban_lap_chi_muc_ghep_boi_canh() -> None:
    assert indexed_text("nội dung", "bối cảnh") == "bối cảnh\n\nnội dung"
    assert indexed_text("nội dung", None) == "nội dung"
    assert indexed_text("nội dung", "") == "nội dung"


async def test_sinh_boi_canh_cho_moi_doan() -> None:
    llm = FakeLLMProvider(forced_reply="Đoạn này thuộc quy chế học phí của trường.")
    chunks = chunk_text(DOC, max_tokens=60)
    out = await build_prefixes(DOC, chunks, llm=llm)

    assert len(out.prefixes) == len(chunks)
    assert all(p for p in out.prefixes)
    assert out.failed == 0
    assert len(llm.calls) == len(chunks), "mỗi đoạn một lượt gọi — đó là chi phí dòng E"


async def test_mo_hinh_hong_khong_chan_ca_tai_lieu() -> None:
    """Suy giảm êm: đoạn không có bối cảnh vẫn lập chỉ mục bình thường.

    Bối cảnh là phần *thêm*. Để một lượt gọi hỏng làm chết cả tài liệu là đánh
    đổi sai chiều hoàn toàn.
    """
    chunks = chunk_text(DOC, max_tokens=60)
    out = await build_prefixes(DOC, chunks, llm=BrokenLLM())

    assert len(out.prefixes) == len(chunks)
    assert out.failed == len(chunks)
    assert all(p == "" for p in out.prefixes)


@pytest.mark.db
async def test_boi_canh_khong_pha_INV1(tmp_path, monkeypatch) -> None:
    """Bối cảnh vào `tsv` và vector, KHÔNG vào `content`.

    Đây là điều làm US-049 an toàn: trích dẫn vẫn trỏ đúng vị trí trên trang,
    và người dùng vẫn đọc nguyên văn tài liệu chứ không đọc phần mô tả do mô
    hình sinh ra.
    """
    monkeypatch.setattr(settings, "contextual_retrieval_enabled", True)
    llm = FakeLLMProvider(forced_reply="Đoạn này thuộc quy chế học phí.")

    with session_scope() as s:
        result = await _seed(s, tmp_path, llm=llm)

    assert result.invariant_holds, "sinh bối cảnh không được làm lệch offset"
    assert result.context_seconds > 0, "US-049 AC-4 — phải đo được chi phí"

    with session_scope() as s:
        chunks = s.scalars(
            select(SourceChunk)
            .join(Notebook, Notebook.id == SourceChunk.notebook_id)
            .join(User, User.id == Notebook.user_id)
            .where(User.email == OWNER)
        ).all()
        assert chunks
        for c in chunks:
            assert c.context_prefix, "chưa lưu bối cảnh"
            assert c.context_prefix not in c.content, "bối cảnh lọt vào nội dung hiển thị"


@pytest.mark.db
async def test_boi_canh_vao_ca_nhanh_tu_khoa(tmp_path, monkeypatch) -> None:
    """US-049 AC-2 — Contextual BM25, không chỉ Contextual Embedding.

    Số liệu gốc của Anthropic: chỉ contextual embedding giảm 35% tỉ lệ trượt,
    thêm contextual BM25 nâng lên 49%. Bỏ nửa này là bỏ một nửa lợi ích, và
    không có test thì rất dễ bỏ mà không ai nhận ra.
    """
    monkeypatch.setattr(settings, "contextual_retrieval_enabled", True)
    # Cụm từ này chỉ có trong bối cảnh, tuyệt đối không có trong tài liệu.
    llm = FakeLLMProvider(forced_reply="Đoạn này nói về khoản đóng góp bắt buộc.")

    with session_scope() as s:
        await _seed(s, tmp_path, llm=llm)

    with session_scope() as s:
        hits = s.execute(
            sql("""
                SELECT count(*) FROM source_chunks c
                JOIN notebooks n ON n.id = c.notebook_id
                JOIN users u ON u.id = n.user_id
                WHERE u.email = :owner
                  AND c.tsv @@ phraseto_tsquery('vi', 'đóng góp bắt buộc')
            """),
            {"owner": OWNER},
        ).scalar()

    assert hits > 0, "cụm từ trong bối cảnh không tìm được ở nhánh từ khoá"


@pytest.mark.db
async def test_tat_boi_canh_thi_khong_goi_mo_hinh(tmp_path, monkeypatch) -> None:
    """Dòng E của bảng ablation — tắt được bằng cấu hình, không sửa mã."""
    monkeypatch.setattr(settings, "contextual_retrieval_enabled", False)
    llm = FakeLLMProvider(forced_reply="Bối cảnh nào đó.")

    with session_scope() as s:
        result = await _seed(s, tmp_path, llm=llm)

    assert llm.calls == [], "đã tắt mà vẫn tốn lượt gọi mô hình"
    assert result.context_seconds == 0.0

    with session_scope() as s:
        prefixes = s.scalars(
            select(SourceChunk.context_prefix)
            .join(Notebook, Notebook.id == SourceChunk.notebook_id)
            .join(User, User.id == Notebook.user_id)
            .where(User.email == OWNER)
        ).all()
    assert prefixes and all(p is None for p in prefixes)


# ══════════════════════════════════════════════════════
# US-063 — Tác tử kiểm định
# ══════════════════════════════════════════════════════


async def test_kiem_dinh_dat() -> None:
    llm = FakeLLMProvider(forced_reply="KẾT LUẬN: ĐẠT")
    v = await verify_answer("Câu trả lời [1].", [_block(1, "nội dung")], llm=llm)
    assert v.passed
    assert not v.needs_retry


async def test_kiem_dinh_khong_dat_kem_ly_do() -> None:
    llm = FakeLLMProvider(
        forced_reply=(
            "KẾT LUẬN: KHÔNG ĐẠT\n"
            "VẤN ĐỀ: Khẳng định về mức học phí không có trong đoạn nào."
        )
    )
    v = await verify_answer("Học phí là 0 đồng.", [_block(1, "nội dung")], llm=llm)
    assert not v.passed
    assert v.needs_retry
    assert "học phí" in (v.issue or "").lower(), "lý do phải đi kèm để lượt sinh lại dùng được"


async def test_bo_kiem_hong_thi_coi_nhu_dat() -> None:
    """Bộ kiểm không đáng tin không được phép chặn câu trả lời vốn có thể đúng.

    Nó là lớp bảo vệ thêm, không phải cổng chặn.
    """
    v = await verify_answer("Câu trả lời.", [_block(1, "x")], llm=BrokenLLM())
    assert v.passed


async def test_khuon_dang_la_thi_coi_nhu_dat() -> None:
    llm = FakeLLMProvider(forced_reply="Tôi nghĩ là ổn đấy bạn ạ")
    v = await verify_answer("Câu trả lời.", [_block(1, "x")], llm=llm)
    assert v.passed
    assert v.raw, "vẫn phải giữ đầu ra thô để gỡ lỗi"


async def test_khong_co_ngu_canh_thi_bo_qua() -> None:
    llm = FakeLLMProvider(forced_reply="KẾT LUẬN: KHÔNG ĐẠT")
    v = await verify_answer("Câu trả lời.", [], llm=llm)
    assert v.passed
    assert llm.calls == [], "không có ngữ cảnh thì đừng tốn một lượt gọi"


class VerifierAlwaysFails(FakeLLMProvider):
    """Sinh câu trả lời bình thường, nhưng lượt kiểm nào cũng trả KHÔNG ĐẠT."""

    async def stream(self, system, messages, **kwargs):
        self.calls.append((system, list(messages)))
        if "KẾT LUẬN" in system:
            yield "KẾT LUẬN: KHÔNG ĐẠT\nVẤN ĐỀ: có khẳng định không được chứng thực"
        else:
            yield "Theo tài liệu [1], mức thu được công bố trước kỳ tuyển sinh."


@pytest.mark.db
async def test_sinh_lai_khi_kiem_dinh_khong_dat(tmp_path, monkeypatch) -> None:
    """US-063 AC-2 — sinh lại đúng một lần với chỉ dẫn siết chặt hơn.

    Giao diện không rút lại được thứ đã hiện, nên bản sửa phải đi bằng sự kiện
    `replace` chứ không phải bằng token gửi thêm (`SPEC-v1.md` §7.1).
    """
    monkeypatch.setattr(settings, "verifier_enabled", True)
    monkeypatch.setattr(settings, "verifier_max_retry", 1)
    monkeypatch.setattr(settings, "intent_routing_enabled", False)

    emb = FakeEmbeddingProvider(dim=1024)
    llm = VerifierAlwaysFails()

    with session_scope() as s:
        await _seed(s, tmp_path)
        user_id, nb_id = _ids(s)
        events = [
            e
            async for e in answer_question(
                s,
                "mức thu học phí được công bố khi nào",
                notebook_id=nb_id,
                embedder=emb,
                reranker=FakeRerankProvider(),
                llm=llm,
                owner_id=user_id,
            )
        ]

    kinds = [e["type"] for e in events]
    assert "verification" in kinds
    assert "replace" in kinds, "phải gửi bản thay thế, không gửi thêm token"

    result = final_result(events)
    assert result.retries == 1, "chỉ được sinh lại đúng số lần cấu hình cho phép"
    assert result.verified is False, "phải ghi lại là vẫn chưa đạt sau khi sinh lại"

    # Lượt sinh lại phải nêu đúng vấn đề, không phải một lời nhắc chung chung.
    retry_prompt = llm.calls[2][1][-1]["content"]
    assert "không được chứng thực" in retry_prompt


@pytest.mark.db
async def test_tat_kiem_dinh_thi_khong_goi_them(tmp_path, monkeypatch) -> None:
    """Dòng F của bảng ablation — US-063 AC-4."""
    monkeypatch.setattr(settings, "verifier_enabled", False)
    monkeypatch.setattr(settings, "intent_routing_enabled", False)

    emb = FakeEmbeddingProvider(dim=1024)
    llm = FakeLLMProvider()

    with session_scope() as s:
        await _seed(s, tmp_path)
        user_id, nb_id = _ids(s)
        events = [
            e
            async for e in answer_question(
                s,
                "mức thu học phí",
                notebook_id=nb_id,
                embedder=emb,
                reranker=FakeRerankProvider(),
                llm=llm,
                owner_id=user_id,
            )
        ]

    assert not any(e["type"] == "verification" for e in events)
    assert final_result(events).verified is None
    assert len(llm.calls) == 1, "chỉ được gọi mô hình đúng một lần khi bộ kiểm tắt"


# ══════════════════════════════════════════════════════
# US-066 — Định tuyến ý định
# ══════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "question",
    ["chào bạn", "hi", "xin chào", "cảm ơn nhé", "ok", "bạn là ai", "bạn làm được gì"],
)
async def test_nhan_ra_tro_chuyen_thong_thuong(question: str) -> None:
    intent, how = await classify(question, llm=None, use_llm_fallback=False)
    assert intent == "chitchat", question
    assert how == "rule", "ca rõ ràng phải quyết bằng luật, không tốn lượt gọi mô hình"


@pytest.mark.parametrize(
    "question",
    [
        "Điều 5 quy định gì",
        "quy chế đào tạo nói gì về học phí",
        "theo thông tư thì thời hạn là bao lâu",
        "thời gian đào tạo trình độ đại học là bao nhiêu năm",
        "TCVN 5945 áp dụng cho đối tượng nào",
    ],
)
async def test_nhan_ra_cau_hoi_tra_cuu(question: str) -> None:
    intent, _ = await classify(question, llm=None, use_llm_fallback=False)
    assert intent == "rag", question


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("mục 3 nói gì", "rag"),      # "mục" — dấu hiệu tài liệu thật
        ("mức thu", "rag"),           # "mức" — cùng chuỗi sau khi bỏ dấu
        ("chào mọi người", "chitchat"),
    ],
)
async def test_khong_nham_tu_dong_am_sau_khi_bo_dau(question: str, expected: str) -> None:
    """Bỏ dấu làm "mức" và "mục" thành cùng một chuỗi.

    Nếu so khớp dấu hiệu tài liệu trên bản bỏ dấu thì "mức thu" bị coi là câu
    tra cứu chắc chắn, và luật kết luận sai ngay ở tầng rẻ nhất — chỗ khó phát
    hiện nhất vì nó không bao giờ hỏi tới mô hình.
    """
    intent, _ = await classify(question, llm=None, use_llm_fallback=False)
    assert intent == expected, question


async def test_phan_van_thi_thien_ve_rag() -> None:
    """Định tuyến nhầm câu hỏi thật sang trò chuyện làm mất câu trả lời có căn
    cứ; nhầm chiều ngược lại chỉ tốn vài trăm mili giây."""
    intent, how = await classify("mức thu", llm=None, use_llm_fallback=False)
    assert intent == "rag"
    assert how == "default"


async def test_mo_hinh_quyet_khi_luat_khong_ket_luan_duoc() -> None:
    llm = FakeLLMProvider(forced_reply="CHITCHAT")
    intent, how = await classify("ừ nhỉ", llm=llm)
    assert (intent, how) == ("chitchat", "llm")
    assert len(llm.calls) == 1


async def test_mo_hinh_hong_thi_mac_dinh_rag() -> None:
    intent, how = await classify("ừ nhỉ", llm=BrokenLLM())
    assert intent == "rag", "phân loại hỏng không được chặn câu hỏi"
    assert how == "error"


@pytest.mark.db
async def test_tro_chuyen_khong_chay_truy_xuat(tmp_path, monkeypatch) -> None:
    """US-066 AC-2 — đó là toàn bộ lý do bước này tồn tại."""
    monkeypatch.setattr(settings, "intent_routing_enabled", True)
    emb = FakeEmbeddingProvider(dim=1024)

    with session_scope() as s:
        await _seed(s, tmp_path)
        user_id, nb_id = _ids(s)
        events = [
            e
            async for e in answer_question(
                s,
                "chào bạn",
                notebook_id=nb_id,
                embedder=emb,
                reranker=FakeRerankProvider(),
                llm=FakeLLMProvider(),
                owner_id=user_id,
            )
        ]

    assert any(e["type"] == "intent" and e["intent"] == "chitchat" for e in events)
    assert not any(e["type"] == "status" for e in events), (
        "không có bước truy xuất nào được phép chạy cho một lời chào"
    )

    result = final_result(events)
    assert result.kind == "chitchat"
    assert result.citations == []
    assert result.decision is None


@pytest.mark.db
async def test_tat_dinh_tuyen_thi_moi_cau_deu_qua_rag(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "intent_routing_enabled", False)
    emb = FakeEmbeddingProvider(dim=1024)

    with session_scope() as s:
        await _seed(s, tmp_path)
        user_id, nb_id = _ids(s)
        events = [
            e
            async for e in answer_question(
                s,
                "chào bạn",
                notebook_id=nb_id,
                embedder=emb,
                reranker=FakeRerankProvider(),
                llm=FakeLLMProvider(),
                owner_id=user_id,
            )
        ]

    assert not any(e["type"] == "intent" for e in events)
    assert any(e["type"] == "status" for e in events)
    assert final_result(events).kind in {"grounded", "no_answer"}
