"""Cache câu trả lời ngoài và bất biến INV-3 — US-032 → US-035.

`SPEC.md` §J.6 gọi INV-3 là điều thứ hai quyết định thành bại, và nêu đúng lý
do: *cách làm sai lại đơn giản hơn cách làm đúng*. Vì vậy nó được kiểm ở hai
mức — cấu trúc câu SQL, và hành vi thật trên cơ sở dữ liệu.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.adapters.embedding.fake import FakeEmbeddingProvider
from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.rerank.fake import FakeRerankProvider
from app.models.base import session_scope
from app.models.chat import ExternalAnswerCache, ExternalCallLog
from app.models.knowledge import Notebook, SourceChunk, User
from app.repositories import chat as repo
from app.services.answer import answer_question, final_result
from app.services.external import (
    EXTERNAL_WARNING,
    QuotaExceeded,
    answer_externally,
)
from app.services.ingest import ingest_file
from app.settings import settings

pytestmark = pytest.mark.db

OWNER = "external@documind.local"
OTHER = "external-other@documind.local"
NOTEBOOK = "external-test"

DOC = """Điều 1. Thời gian đào tạo
Thời gian đào tạo trình độ đại học từ ba đến năm năm đối với văn bằng thứ nhất.
"""


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        with session_scope() as s:
            s.execute(delete(User).where(User.email.in_([OWNER, OTHER])))

    wipe()
    yield
    wipe()


@pytest.fixture
def emb() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dim=1024)


@pytest.fixture
def llm() -> FakeLLMProvider:
    return FakeLLMProvider(forced_reply="Đây là câu trả lời từ kiến thức chung.")


@pytest.fixture
def users(tmp_path, emb):
    p = tmp_path / "doc.txt"
    p.write_text(DOC, encoding="utf-8")
    out = {}
    with session_scope() as s:
        ingest_file(s, p, notebook_title=NOTEBOOK, embedder=emb, owner_email=OWNER)
        repo_user = s.scalar(select(User).where(User.email == OWNER))
        nb = s.scalar(select(Notebook).where(Notebook.user_id == repo_user.id))
        out[OWNER] = (repo_user.id, nb.id)
        other = User(email=OTHER, password_hash="x")
        s.add(other)
        s.flush()
        out[OTHER] = (other.id, None)
    return out


async def _ask_external(question: str, user_id, emb, llm, **kw) -> list[dict]:
    with session_scope() as s:
        return [
            e
            async for e in answer_externally(
                s, question, user_id=user_id, embedder=emb, llm=llm, **kw
            )
        ]


# ══════════════════════════════════════════════════════
# INV-3 — cache tách khỏi chỉ mục tài liệu
# ══════════════════════════════════════════════════════


async def test_INV3_cau_tra_loi_ngoai_khong_vao_source_chunks(users, emb, llm) -> None:
    """Bất biến quan trọng nhất của tệp này.

    Vi phạm không làm gì đỏ theo cách thông thường: hệ thống vẫn chạy, chỉ là
    dần dần nó trích dẫn chính nội dung nó tự bịa ra.
    """
    user_id, _ = users[OWNER]

    with session_scope() as s:
        before = s.scalar(select(func.count()).select_from(SourceChunk))

    await _ask_external("giá vàng hôm nay bao nhiêu", user_id, emb, llm)

    with session_scope() as s:
        after = s.scalar(select(func.count()).select_from(SourceChunk))
        cached = s.scalar(
            select(func.count())
            .select_from(ExternalAnswerCache)
            .where(ExternalAnswerCache.user_id == user_id)
        )

    assert after == before, "câu trả lời ngoài đã lọt vào chỉ mục tài liệu"
    assert cached == 1, "câu trả lời ngoài phải nằm trong namespace riêng"


async def test_INV3_truy_xuat_tai_lieu_khong_thay_cau_tra_loi_ngoai(
    users, emb, llm
) -> None:
    """Sau khi cache một câu trả lời, truy xuất tài liệu không được trả về nó."""
    user_id, nb_id = users[OWNER]
    unique = "Bạch tuộc khổng lồ sống ở rãnh Mariana sâu mười một nghìn mét"

    with session_scope() as s:
        repo.store_cached_answer(
            s, user_id, "bạch tuộc sống ở đâu", emb.embed_query("bạch tuộc"),
            unique, "fake",
        )

    with session_scope() as s:
        events = [
            e
            async for e in answer_question(
                s, "bạch tuộc khổng lồ rãnh Mariana", notebook_id=nb_id,
                embedder=emb, reranker=FakeRerankProvider(),
                llm=FakeLLMProvider(), owner_id=user_id,
            )
        ]

    result = final_result(events)
    assert unique not in result.answer
    for c in result.citations:
        assert unique not in c.snippet


# ══════════════════════════════════════════════════════
# Nhãn cảnh báo và trích dẫn — US-033
# ══════════════════════════════════════════════════════


async def test_luon_kem_nhan_canh_bao(users, emb, llm) -> None:
    """US-033 AC-2 — nhãn cố định, phát ra trước cả token đầu tiên."""
    user_id, _ = users[OWNER]
    events = await _ask_external("câu hỏi bất kỳ", user_id, emb, llm)

    warnings = [e for e in events if e["type"] == "warning"]
    assert warnings
    assert warnings[0]["text"] == EXTERNAL_WARNING
    assert events.index(warnings[0]) < next(
        i for i, e in enumerate(events) if e["type"] == "token"
    )


async def test_khong_bao_gio_co_trich_dan(users, emb, llm) -> None:
    """US-033 AC-3 — không có nguồn nào để trỏ tới, nên gắn chip là nói dối."""
    user_id, _ = users[OWNER]
    events = await _ask_external("câu hỏi bất kỳ", user_id, emb, llm)
    assert not any(e["type"] == "citation" for e in events)


async def test_danh_dau_la_khong_chay_cuc_bo(users, emb, llm) -> None:
    user_id, _ = users[OWNER]
    events = await _ask_external("câu hỏi", user_id, emb, llm)
    assert events[0]["external"] is True


# ══════════════════════════════════════════════════════
# Cache — US-034
# ══════════════════════════════════════════════════════


async def test_cau_hoi_lap_lai_duoc_phuc_vu_tu_cache(users, emb, llm) -> None:
    user_id, _ = users[OWNER]
    q = "thủ đô của nước Pháp là thành phố nào"

    first = await _ask_external(q, user_id, emb, llm)
    assert not any(e["type"] == "cache_hit" for e in first)

    second = await _ask_external(q, user_id, emb, llm)
    hits = [e for e in second if e["type"] == "cache_hit"]
    assert hits, "câu hỏi y hệt phải trúng cache"
    assert hits[0]["similarity"] == pytest.approx(1.0, abs=1e-4)


async def test_cache_hit_hien_cau_hoi_goc(users, emb, llm) -> None:
    """US-034 AC-3 — để người dùng tự đối chiếu có đúng ý mình không.

    Không có bước này thì một lần khớp gần đúng sẽ âm thầm trả lời sai câu hỏi.
    """
    user_id, _ = users[OWNER]
    q = "thủ đô của nước Pháp là thành phố nào"
    await _ask_external(q, user_id, emb, llm)
    second = await _ask_external(q, user_id, emb, llm)

    hit = next(e for e in second if e["type"] == "cache_hit")
    assert hit["cached_question"] == q
    assert hit["hit_count"] == 1


async def test_cau_hoi_khac_han_khong_trung_cache(users, emb, llm) -> None:
    user_id, _ = users[OWNER]
    await _ask_external("thủ đô của nước Pháp là gì", user_id, emb, llm)
    other = await _ask_external(
        "quy trình đăng ký học phần trực tuyến thế nào", user_id, emb, llm
    )
    assert not any(e["type"] == "cache_hit" for e in other)


async def test_cache_khong_dung_chung_giua_nguoi_dung(users, emb, llm) -> None:
    """US-034 AC-6 — câu đã hỏi ra ngoài là dữ liệu riêng tư."""
    a, _ = users[OWNER]
    b, _ = users[OTHER]
    q = "thủ đô của nước Pháp là thành phố nào"

    await _ask_external(q, a, emb, llm)
    events_b = await _ask_external(q, b, emb, llm)
    assert not any(e["type"] == "cache_hit" for e in events_b)


async def test_ban_ghi_het_han_bi_bo_qua(users, emb, llm) -> None:
    """US-034 AC-5 — tránh trả lời cũ khi thế giới đã đổi."""
    user_id, _ = users[OWNER]
    q = "câu hỏi có bản ghi cũ"

    with session_scope() as s:
        entry = repo.store_cached_answer(
            s, user_id, q, emb.embed_query(q), "câu trả lời cũ", "fake"
        )
        entry.expires_at = datetime.now(UTC) - timedelta(days=1)

    events = await _ask_external(q, user_id, emb, llm)
    assert not any(e["type"] == "cache_hit" for e in events)


def test_nguong_tuong_dong_phan_biet_duoc_cau_gan_giong(emb) -> None:
    """US-034 AC-7 — "Điều 5" và "Điều 15" phải là hai câu hỏi khác nhau.

    Đây là ca kiểm thử mà đặc tả nêu đích danh, vì với `bge-m3` phân bố cosine
    bị nén cao và ngưỡng 0.93 chưa được hiệu chỉnh bằng dữ liệu.
    """
    a = emb.embed_query("Điều 5 quy định gì")
    b = emb.embed_query("Điều 15 quy định gì")
    similarity = sum(x * y for x, y in zip(a, b, strict=True))
    assert similarity < settings.external_cache_similarity, (
        f"tương đồng {similarity:.4f} ≥ ngưỡng {settings.external_cache_similarity} — "
        f"hai câu hỏi khác nhau sẽ dùng chung câu trả lời"
    )


# ══════════════════════════════════════════════════════
# Hạn mức — US-035
# ══════════════════════════════════════════════════════


async def test_vuot_han_muc_bi_tu_choi(users, emb, llm, monkeypatch) -> None:
    monkeypatch.setattr(settings, "external_calls_per_day", 2)
    user_id, _ = users[OWNER]

    for i in range(2):
        await _ask_external(f"câu hỏi số {i} hoàn toàn khác nhau về nội dung", user_id, emb, llm)

    with pytest.raises(QuotaExceeded) as exc:
        await _ask_external("câu hỏi thứ ba khác hẳn hai câu trên", user_id, emb, llm)
    assert exc.value.limit == 2


async def test_luot_tu_cache_khong_tinh_vao_han_muc(users, emb, llm, monkeypatch) -> None:
    """Phục vụ từ cache không tiêu tốn quota nào của nhà cung cấp."""
    monkeypatch.setattr(settings, "external_calls_per_day", 1)
    user_id, _ = users[OWNER]
    q = "câu hỏi sẽ được lặp lại nhiều lần"

    await _ask_external(q, user_id, emb, llm)
    for _ in range(3):
        events = await _ask_external(q, user_id, emb, llm)
        assert any(e["type"] == "cache_hit" for e in events)

    with session_scope() as s:
        assert repo.calls_today(s, user_id) == 1


async def test_xoa_cache(users, emb, llm) -> None:
    """US-035 AC-2 — xoá toàn bộ cache của người dùng."""
    user_id, _ = users[OWNER]
    await _ask_external("câu hỏi một khác biệt hoàn toàn", user_id, emb, llm)
    await _ask_external("nội dung thứ hai chẳng liên quan gì", user_id, emb, llm)

    with session_scope() as s:
        assert repo.clear_cache(s, user_id) == 2
    with session_scope() as s:
        remaining = s.scalar(
            select(func.count())
            .select_from(ExternalAnswerCache)
            .where(ExternalAnswerCache.user_id == user_id)
        )
    assert remaining == 0


async def test_ghi_nhat_ky_moi_luot_goi(users, emb, llm) -> None:
    """Dữ liệu cho thống kê US-041: tỉ lệ cache hit."""
    user_id, _ = users[OWNER]
    q = "câu hỏi được lặp lại"
    await _ask_external(q, user_id, emb, llm)
    await _ask_external(q, user_id, emb, llm)

    with session_scope() as s:
        rows = s.scalars(
            select(ExternalCallLog).where(ExternalCallLog.user_id == user_id)
        ).all()
    assert len(rows) == 2
    assert sorted(r.from_cache for r in rows) == [False, True]
