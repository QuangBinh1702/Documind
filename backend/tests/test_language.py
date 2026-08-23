"""Nhận diện ngôn ngữ câu hỏi — US-037."""

from __future__ import annotations

import pytest

from app.services import prompt as P
from app.services.intent import chitchat_system_prompt
from app.text.language import nhan_dien


@pytest.mark.parametrize(
    "cau",
    [
        "Điều kiện tốt nghiệp là gì?",
        "Mức thu học phí năm 2024 bao nhiêu?",
        "chào bạn",
        "Quy chế này áp dụng cho ai?",
    ],
)
def test_co_dau_thi_chac_chan_tieng_viet(cau: str):
    assert nhan_dien(cau) == "vi"


@pytest.mark.parametrize(
    "cau",
    [
        "dieu kien tot nghiep la gi",
        "muc thu hoc phi nam 2024 bao nhieu",
        "quy che nay ap dung cho ai vay",
        "lam sao de dang ky hoc phan",
        "toi muon biet ve hoc bong",
    ],
)
def test_khong_dau_van_nhan_ra_tieng_viet(cau: str):
    """Ca quan trọng nhất của US-037.

    Người Việt gõ không dấu rất thường xuyên. Nhận nhầm thành tiếng Anh thì họ
    gõ tiếng Việt mà nhận về câu trả lời tiếng Anh — một lỗi lộ ngay lập tức.
    """
    assert nhan_dien(cau) == "vi"


@pytest.mark.parametrize(
    "cau",
    [
        "What are the graduation requirements?",
        "How much is the tuition fee for 2024?",
        "Please explain the scholarship policy",
        "Which articles talk about credit transfer?",
        "Can you tell me about the admission process",
    ],
)
def test_nhan_ra_tieng_anh(cau: str):
    assert nhan_dien(cau) == "en"


def test_the_nao_khong_bi_nham_la_mao_tu_tieng_anh():
    """"thế nào" bỏ dấu thành "the nao" — trùng đúng từ tiếng Anh mạnh nhất."""
    assert nhan_dien("dieu kien the nao") == "vi"
    assert nhan_dien("the nao la sinh vien chinh quy") == "vi"


def test_rong_thi_mac_dinh_tieng_viet():
    for x in ("", "   ", "\n"):
        assert nhan_dien(x) == "vi"


def test_so_va_ky_hieu_khong_du_de_ket_luan():
    """Không có bằng chứng nào thì rơi về mặc định, không đoán bừa."""
    assert nhan_dien("2024?") == "vi"
    assert nhan_dien("08/2021/TT-BGDĐT") == "vi"


# ═══════════════════════════════════════════════════════
# Prompt đi theo ngôn ngữ
# ═══════════════════════════════════════════════════════


def test_cau_tu_choi_co_hai_ban():
    assert P.no_answer_text("vi") == P.NO_ANSWER_TEXT
    assert P.no_answer_text("en") == P.NO_ANSWER_TEXT_EN
    assert P.NO_ANSWER_TEXT != P.NO_ANSWER_TEXT_EN


def test_nhan_ra_tu_choi_o_ca_hai_ngon_ngu():
    """Bỏ sót bản tiếng Anh sẽ ghi nhầm `answer_kind` và làm lệch thống kê."""
    assert P.is_no_answer(P.NO_ANSWER_TEXT)
    assert P.is_no_answer(P.NO_ANSWER_TEXT_EN)
    assert P.is_no_answer(f"  {P.NO_ANSWER_TEXT_EN} Thêm chút giải thích.")
    assert not P.is_no_answer("Theo Điều 5 thì điều kiện là [1].")


def test_system_prompt_tieng_anh_nhac_cau_tu_choi_tieng_anh():
    """Prompt tiếng Anh mà kèm câu từ chối tiếng Việt thì mô hình trả lời lẫn lộn."""
    en = P.build_grounded_system_prompt("en")
    assert P.NO_ANSWER_TEXT_EN in en
    assert P.NO_ANSWER_TEXT not in en

    vi = P.build_grounded_system_prompt("vi")
    assert P.NO_ANSWER_TEXT in vi


def test_prompt_tro_chuyen_cung_doi_theo_ngon_ngu():
    assert "in English" in chitchat_system_prompt("en")
    assert "tiếng Việt" in chitchat_system_prompt("vi")
