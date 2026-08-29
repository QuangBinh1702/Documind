"""Xuất hội thoại — US-040.

Cái đáng test không phải "có sinh ra tệp không" mà là **thứ dễ mất trên đường
đi**: dấu tiếng Việt trong PDF, danh mục trích dẫn, và nhãn cảnh báo cho câu trả
lời không có căn cứ trong tài liệu. Cả ba đều hỏng lặng lẽ — tệp vẫn tạo ra
được, chỉ là nội dung sai.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from app.models.base import session_scope
from app.models.chat import ChatMessage, ChatSession, MessageCitation
from app.models.knowledge import User
from app.repositories import knowledge as repo
from app.services.export import (
    KhongCoFont,
    ten_tep,
    tim_font,
    xuat,
    xuat_markdown,
    xuat_pdf,
)

pytestmark = pytest.mark.db

TOI = "export-toi@example.com"
NGUOI_LA = "export-khac@example.com"


@pytest.fixture(autouse=True)
def clean_db():
    def wipe() -> None:
        with session_scope() as s:
            s.execute(delete(User).where(User.email.in_([TOI, NGUOI_LA])))

    wipe()
    yield
    wipe()


def _phien(s, email: str = TOI) -> ChatSession:
    """Một phiên có ba lượt: có căn cứ, hỏi ra ngoài, và từ chối."""
    user = repo.get_or_create_user(s, email)
    nb = repo.get_or_create_notebook(s, user, "Quy chế đào tạo")
    phien = ChatSession(
        notebook_id=nb.id, user_id=user.id, title="Hỏi về điều kiện tốt nghiệp"
    )
    s.add(phien)
    s.flush()

    def cap(hoi: str, dap: str, kind: str) -> ChatMessage:
        s.add(ChatMessage(session_id=phien.id, role="user", content=hoi))
        m = ChatMessage(
            session_id=phien.id, role="assistant", content=dap,
            answer_kind=kind, model_used="local:m", latency_ms=1000,
        )
        s.add(m)
        s.flush()
        return m

    co_can_cu = cap(
        "Điều kiện tốt nghiệp là gì?",
        "Người học được xét tốt nghiệp khi tích luỹ đủ số tín chỉ [1] và đạt "
        "chuẩn đầu ra ngoại ngữ [2].",
        "grounded",
    )
    s.add(
        MessageCitation(
            message_id=co_can_cu.id, chunk_id=None, marker=1,
            snippet="tích luỹ đủ số tín chỉ", page_no=15,
        )
    )
    s.add(
        MessageCitation(
            message_id=co_can_cu.id, chunk_id=None, marker=2,
            snippet="chuẩn đầu ra ngoại ngữ", page_no=16,
        )
    )

    cap("Thủ đô nước Pháp là gì?", "Paris.", "external")
    cap("Học phí năm 2030?", "Không tìm thấy thông tin này trong tài liệu của bạn.",
        "no_answer")
    s.flush()
    return phien


# ══════════════════════════════════════════════════════
# Tên tệp
# ══════════════════════════════════════════════════════


def test_ten_tep_co_ten_notebook_va_ngay():
    ten = ten_tep("Quy chế đào tạo", "md", datetime(2026, 8, 23, tzinfo=UTC))
    assert ten == "documind-quy-che-dao-tao-20260823.md"


def test_ten_tep_chi_dung_ascii():
    """Tên tệp đi qua header HTTP, nên có dấu là rủi ro không cần thiết."""
    ten = ten_tep("Đề tài — Nhận dạng ảnh (bản 2)", "pdf")
    assert ten.isascii(), ten
    assert " " not in ten


def test_ten_notebook_toan_ky_tu_la_van_ra_ten_dung_duoc():
    assert ten_tep("《》【】", "md").startswith("documind-hoi-dap-")


# ══════════════════════════════════════════════════════
# Markdown
# ══════════════════════════════════════════════════════


def test_markdown_co_du_hoi_va_dap():
    with session_scope() as s:
        ket = xuat_markdown(s, _phien(s))

    text = ket.noi_dung.decode("utf-8")
    assert "Điều kiện tốt nghiệp là gì?" in text
    assert "tích luỹ đủ số tín chỉ" in text
    assert "Thủ đô nước Pháp" in text
    assert ket.ten_tep.endswith(".md")


def test_markdown_co_danh_muc_trich_dan():
    """AC-1 — `[1]` trong tệp xuất ra không bấm được, nên phải nói nó là gì."""
    with session_scope() as s:
        text = xuat_markdown(s, _phien(s)).noi_dung.decode("utf-8")

    assert "Nguồn trích dẫn" in text
    assert "`[1]`" in text
    assert "trang 15" in text
    assert "trang 16" in text


def test_markdown_giu_nhan_canh_bao():
    """AC-3 — mất nhãn là biến câu chưa kiểm chứng thành câu trông có căn cứ."""
    with session_scope() as s:
        text = xuat_markdown(s, _phien(s)).noi_dung.decode("utf-8")

    assert "KHÔNG có trong tài liệu" in text
    # Và nhãn đó phải đứng riêng, không lẫn vào nội dung câu trả lời.
    assert "> ⚠" in text


def test_pdf_khong_dung_bieu_tuong_font_khong_co():
    """`⚠` (U+26A0) không có trong Arial và nhiều font khác.

    PDF không báo lỗi khi thiếu glyph — nó in ra một khoảng trống. Nhãn cảnh
    báo mà biến thành khoảng trống thì coi như không có nhãn.
    """
    from app.services.export import NHAN_NGOAI

    assert "⚠" not in NHAN_NGOAI


def test_nguon_da_xoa_van_hien_trong_danh_muc():
    """US-020 AC-4 — xoá tài liệu không được làm câu trả lời cũ mất trích dẫn."""
    with session_scope() as s:
        text = xuat_markdown(s, _phien(s)).noi_dung.decode("utf-8")
    assert "đã bị xoá" in text


# ══════════════════════════════════════════════════════
# PDF
# ══════════════════════════════════════════════════════


def test_pdf_hien_dung_tieng_viet_co_dau():
    """AC-2 — 14 font chuẩn của PDF không có ký tự tiếng Việt.

    Dùng nhầm chúng thì tệp vẫn tạo ra bình thường, chỉ là chữ có dấu in ra
    thành ô vuông. Cách bắt được là đọc ngược văn bản ra khỏi PDF vừa dựng.
    """
    pymupdf = pytest.importorskip("pymupdf")
    try:
        tim_font()
    except KhongCoFont:
        pytest.skip("máy này không có font Unicode nào")

    with session_scope() as s:
        ket = xuat_pdf(s, _phien(s))

    assert ket.noi_dung.startswith(b"%PDF")
    doc = pymupdf.open(stream=ket.noi_dung, filetype="pdf")
    # PyMuPDF trích khoảng trắng của `insert_text` ra thành NBSP. Đó là chi tiết
    # của việc trích xuất, không phải của tệp — đưa về khoảng trắng thường rồi
    # mới so.
    text = "\n".join(t.get_text() for t in doc).replace("\xa0", " ")
    doc.close()

    assert "Điều kiện tốt nghiệp" in text
    assert "tích luỹ đủ số tín chỉ" in text
    assert "Quy chế đào tạo" in text


def test_pdf_giu_nhan_canh_bao():
    pymupdf = pytest.importorskip("pymupdf")
    try:
        tim_font()
    except KhongCoFont:
        pytest.skip("máy này không có font Unicode nào")

    with session_scope() as s:
        ket = xuat_pdf(s, _phien(s))

    doc = pymupdf.open(stream=ket.noi_dung, filetype="pdf")
    # PyMuPDF trích khoảng trắng của `insert_text` ra thành NBSP. Đó là chi tiết
    # của việc trích xuất, không phải của tệp — đưa về khoảng trắng thường rồi
    # mới so.
    text = "\n".join(t.get_text() for t in doc).replace("\xa0", " ")
    doc.close()
    assert "KHÔNG có trong tài liệu" in text
    assert "[1]" in text


def test_thieu_font_bao_loi_ro_rang(tmp_path):
    with pytest.raises(KhongCoFont) as loi:
        tim_font(str(tmp_path / "khong-ton-tai.ttf"))
    assert "PDF_FONT" in str(loi.value)


# ══════════════════════════════════════════════════════
# Phạm vi
# ══════════════════════════════════════════════════════


def test_khong_xuat_duoc_phien_cua_nguoi_khac():
    with session_scope() as s:
        phien = _phien(s, TOI)
        nguoi_la = repo.get_or_create_user(s, NGUOI_LA)
        s.flush()
        with pytest.raises(LookupError):
            xuat(s, phien.id, nguoi_la.id, "md")


def test_phien_khong_ton_tai():
    with session_scope() as s:
        user = repo.get_or_create_user(s, TOI)
        s.flush()
        with pytest.raises(LookupError):
            xuat(s, uuid.uuid4(), user.id, "md")
