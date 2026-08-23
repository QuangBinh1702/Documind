"""Câu hỏi về TOÀN BỘ tài liệu — US-069.

Bối cảnh: người dùng tải hai tài liệu lên, hỏi *"tóm tắt 2 tài liệu của tôi"*,
và nhận về *"Không tìm thấy thông tin này trong tài liệu của bạn"*.

Đường truy xuất không sai — nó đi tìm đoạn **giống câu hỏi**, mà câu hỏi ấy
không chứa từ nội dung nào của tài liệu. Sai ở chỗ định tuyến: đây là câu hỏi
toàn cục, không phải câu hỏi tra cứu.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete

from app.models.base import session_scope
from app.models.knowledge import User
from app.services.intent import _by_rules
from app.services.summarize import gom_dau_tai_lieu

pytestmark = pytest.mark.db

OWNER = "tomtat@example.com"


# ═══════════════════════════════════════════════════════
# Định tuyến
# ═══════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "cau",
    [
        "tóm tắt 2 tài liệu của tôi",
        "tóm tắt giúp tôi",
        "tom tat tai lieu",
        "nội dung chính của tài liệu là gì",
        "tài liệu này nói về gì",
        "tổng hợp các ý chính",
        "summarize my documents",
        "give me a summary",
        "what is this about",
        "main points please",
    ],
)
def test_cau_hoi_toan_tai_lieu_di_duong_tom_tat(cau: str) -> None:
    assert _by_rules(cau) == "summarize", cau


@pytest.mark.parametrize(
    "cau",
    [
        "tóm tắt Điều 5",
        "tóm tắt Chương II",
        "tóm tắt khoản 3 điều 8",
        "summarize article 12",
    ],
)
def test_tom_tat_MOT_PHAN_van_di_duong_tra_cuu(cau: str) -> None:
    """Truy xuất tìm "Điều 5" rất tốt — không có lý do bỏ qua nó.

    Chỉ những yêu cầu tóm tắt KHÔNG trỏ vào phần nào mới cần đường toàn cục.
    """
    assert _by_rules(cau) == "rag", cau


@pytest.mark.parametrize(
    "cau",
    ["Điều 15 quy định gì", "mức thu học phí bao nhiêu", "điều kiện tốt nghiệp"],
)
def test_cau_hoi_tra_cuu_khong_bi_keo_sang_tom_tat(cau: str) -> None:
    assert _by_rules(cau) == "rag", cau


# ═══════════════════════════════════════════════════════
# Gom đoạn mở đầu
# ═══════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def clean_db():
    def wipe() -> None:
        with session_scope() as s:
            s.execute(delete(User).where(User.email == OWNER))

    wipe()
    yield
    wipe()


def _nap(s, ten: str, so_doan: int, *, in_scope: bool = True, status: str = "ready"):
    """Một nguồn kèm `so_doan` đoạn, đánh số theo thứ tự tài liệu."""
    from app.models.knowledge import Notebook, Source, SourceChunk
    from app.repositories import knowledge as repo

    user = repo.get_or_create_user(s, OWNER)
    nb = s.scalar(
        __import__("sqlalchemy").select(Notebook).where(Notebook.user_id == user.id)
    ) or repo.get_or_create_notebook(s, user, "sổ tay")

    src = Source(
        notebook_id=nb.id, title=ten, original_name=f"{ten}.txt",
        storage_key=f"test://{ten}", kind="txt", mime_type="text/plain",
        size_bytes=100, status=status, in_scope=in_scope,
    )
    s.add(src)
    s.flush()

    for i in range(so_doan):
        s.add(
            SourceChunk(
                source_id=src.id, notebook_id=nb.id, chunk_index=i,
                content=f"{ten} — đoạn số {i}", char_start=i * 100,
                char_end=i * 100 + 20, token_count=50,
            )
        )
    s.flush()
    return nb, src


def test_lay_doan_dau_theo_dung_thu_tu_tai_lieu():
    """Phần đầu văn bản hành chính là chỗ đặt phạm vi và đối tượng áp dụng —
    đúng thứ một bản tóm tắt cần."""
    with session_scope() as s:
        nb, _ = _nap(s, "quy-che", 10)
        doan = gom_dau_tai_lieu(s, notebook_id=nb.id)

    assert doan, "phải lấy được đoạn"
    chi_so = [d.candidate.chunk_index if hasattr(d.candidate, "chunk_index") else i
              for i, d in enumerate(doan)]
    assert chi_so == sorted(chi_so), "phải giữ thứ tự trong tài liệu"
    assert "đoạn số 0" in doan[0].candidate.content


def test_moi_tai_lieu_deu_co_mat():
    """Người dùng nói "tóm tắt 2 tài liệu" — cả hai phải có mặt, kể cả khi một
    cái dài hơn hẳn cái kia."""
    with session_scope() as s:
        nb, _ = _nap(s, "dai", 40)
        _nap(s, "ngan", 3)
        doan = gom_dau_tai_lieu(s, notebook_id=nb.id)

    ten = {d.candidate.content.split(" — ")[0] for d in doan}
    assert ten == {"dai", "ngan"}, ten


def test_bo_qua_tai_lieu_ngoai_pham_vi():
    """US-038 — người dùng bỏ chọn tài liệu nào thì tóm tắt cũng không đọc nó."""
    with session_scope() as s:
        nb, _ = _nap(s, "duoc-chon", 3)
        _nap(s, "bi-bo-chon", 3, in_scope=False)
        doan = gom_dau_tai_lieu(s, notebook_id=nb.id)

    ten = {d.candidate.content.split(" — ")[0] for d in doan}
    assert ten == {"duoc-chon"}


def test_bo_qua_tai_lieu_chua_xu_ly_xong():
    with session_scope() as s:
        nb, _ = _nap(s, "xong", 3)
        _nap(s, "dang-cho", 3, status="queued")
        doan = gom_dau_tai_lieu(s, notebook_id=nb.id)

    ten = {d.candidate.content.split(" — ")[0] for d in doan}
    assert ten == {"xong"}


def test_khong_co_tai_lieu_thi_tra_ve_rong():
    """Chỗ gọi phải nói "chưa có tài liệu nào" chứ không đưa ngữ cảnh rỗng cho
    mô hình — ngữ cảnh rỗng là lời mời bịa."""
    with session_scope() as s:
        from app.repositories import knowledge as repo

        user = repo.get_or_create_user(s, OWNER)
        nb = repo.get_or_create_notebook(s, user, "rỗng")
        s.flush()
        assert gom_dau_tai_lieu(s, notebook_id=nb.id) == []


def test_khong_bia_diem_lien_quan():
    """Đường này không chấm điểm, nó lấy theo vị trí.

    Ghi một điểm giả sẽ đi thẳng vào cột `top_rerank_score` và làm hỏng thống kê
    độ trễ lẫn phân bố ở US-041.
    """
    with session_scope() as s:
        nb, _ = _nap(s, "quy-che", 3)
        doan = gom_dau_tai_lieu(s, notebook_id=nb.id)

    assert all(d.rrf_score == 0.0 for d in doan)
    assert all(d.candidate.score == 0.0 for d in doan)


def test_loc_theo_source_ids_duoc_truyen_vao():
    with session_scope() as s:
        nb, src_a = _nap(s, "a", 3)
        _nap(s, "b", 3)
        doan = gom_dau_tai_lieu(s, notebook_id=nb.id, source_ids=[src_a.id])

    ten = {d.candidate.content.split(" — ")[0] for d in doan}
    assert ten == {"a"}


def test_notebook_khac_khong_lot_vao():
    """INV-4 nhìn từ đường tóm tắt."""
    with session_scope() as s:
        _nap(s, "cua-toi", 3)
        assert gom_dau_tai_lieu(s, notebook_id=uuid.uuid4()) == []
