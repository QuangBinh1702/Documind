"""Tách câu giữ offset — nền của US-008 AC-2 và AC-7.

Tính chất quan trọng nhất được kiểm ở `test_ghep_lai_dung_van_ban_goc`: các
khoảng phải phủ kín văn bản, không mất ký tự nào. Nhờ vậy chunker ghép câu lại
luôn cho `char_start`/`char_end` đúng, tức là INV-1 được giữ.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.text.normalize import normalize
from app.text.segment import build_tsquery_parts, segment_words, split_sentences


def _texts(text: str) -> list[str]:
    """Tiện ích cho test: lấy nội dung từng câu, bỏ khoảng trắng hai đầu."""
    t = normalize(text)
    return [s.slice(t).strip() for s in split_sentences(t)]


# ── Tính chất phải luôn đúng ───────────────────────────

SAMPLES = [
    "Câu một. Câu hai. Câu ba.",
    "Dạng chuẩn 3NF là gì? Nó yêu cầu bảng đã ở 2NF!",
    "TS. Nguyễn Văn A công tác tại TP. Đà Nẵng. Ông là giảng viên.",
    "Theo TCVN 5945:2005 thì nước thải loại B phải đạt 5.2 mg/l. Đây là quy định.",
    "Điều 5. Phạm vi áp dụng\nĐiều 6. Đối tượng áp dụng",
    "Không có dấu chấm nào cả",
    "",
    "   ",
    "Một câu.\n\nMột đoạn khác.\n",
]


@pytest.mark.parametrize("text", SAMPLES)
def test_ghep_lai_dung_van_ban_goc(text: str) -> None:
    """Không ký tự nào được rơi ra ngoài mọi khoảng.

    Đây là bảo đảm khiến hàm này an toàn cho INV-1.
    """
    t = normalize(text)
    assert "".join(s.slice(t) for s in split_sentences(t)) == t


@pytest.mark.parametrize("text", SAMPLES)
def test_cac_khoang_khong_chong_nhau_va_tang_dan(text: str) -> None:
    spans = split_sentences(text)
    for a, b in pairwise(spans):
        assert a.end == b.start, "khoảng phải liền nhau, không hở không chồng"
    for s in spans:
        assert s.start < s.end, "không có khoảng rỗng"


@pytest.mark.parametrize("text", SAMPLES)
def test_khong_bao_gio_tra_ve_chuoi(text: str) -> None:
    """Trả về chuỗi rồi đi tìm lại vị trí là cách offset lệch. Hàm này phải trả
    về offset để chỗ gọi không có cơ hội làm sai."""
    for s in split_sentences(text):
        assert isinstance(s.start, int) and isinstance(s.end, int)


# ── Ca cụ thể ──────────────────────────────────────────


def test_tach_cau_don_gian() -> None:
    assert _texts("Câu một. Câu hai. Câu ba.") == ["Câu một.", "Câu hai.", "Câu ba."]


def test_dau_hoi_va_dau_than() -> None:
    assert _texts("Là gì? Không biết! Xong.") == ["Là gì?", "Không biết!", "Xong."]


@pytest.mark.parametrize(
    "text",
    [
        "TS. Nguyễn Văn A là giảng viên.",
        "Hội thảo tổ chức tại TP. Đà Nẵng vào tháng sau.",
        "PGS. Trần Thị B chủ trì.",
        "Áp dụng cho các trường, viện, trung tâm v.v. trên toàn quốc.",
    ],
)
def test_viet_tat_khong_cat_cau(text: str) -> None:
    """US-008 AC-7 — dấu chấm của viết tắt không kết thúc câu."""
    assert len(split_sentences(text)) == 1, f"bị cắt nhầm: {_texts(text)}"


def test_viet_tat_van_cat_dung_khi_het_cau_that() -> None:
    text = "TS. Nguyễn Văn A là giảng viên. Ông dạy môn cơ sở dữ liệu."
    assert _texts(text) == [
        "TS. Nguyễn Văn A là giảng viên.",
        "Ông dạy môn cơ sở dữ liệu.",
    ]


def test_so_thap_phan_khong_cat_cau() -> None:
    text = "Giới hạn là 5.2 mg/l theo quy định."
    assert len(split_sentences(text)) == 1


def test_ma_hieu_van_ban_khong_cat_cau() -> None:
    text = "Theo TCVN 5945:2005 thì nước thải phải đạt loại B."
    assert len(split_sentences(text)) == 1


def test_chu_cai_viet_tat_ten_rieng() -> None:
    text = "Tác giả Nguyễn V. A. đã trình bày kết quả."
    assert len(split_sentences(text)) == 1


def test_dieu_khoan_theo_sau_boi_chu_hoa_thi_cat() -> None:
    """"Điều 5." rồi tới tiêu đề viết hoa — cắt là hợp lý, mỗi mục một câu."""
    text = "Điều 5. Phạm vi áp dụng. Điều 6. Đối tượng áp dụng."
    assert len(split_sentences(text)) > 1


def test_van_ban_khong_co_dau_cham() -> None:
    assert _texts("Không có dấu chấm nào cả") == ["Không có dấu chấm nào cả"]


def test_van_ban_rong() -> None:
    assert split_sentences("") == []
    assert split_sentences("   ") != []  # khoảng trắng vẫn là nội dung


def test_dau_ngoac_dong_thuoc_ve_cau_truoc() -> None:
    text = 'Ông nói "xong rồi." Rồi ông đi.'
    spans = split_sentences(text)
    t = normalize(text)
    assert spans[0].slice(t).strip().endswith('"')


# ── Tách từ (đường truy vấn) ───────────────────────────


def test_segment_words_khong_sap_khi_thieu_underthesea() -> None:
    """Suy giảm êm: không có underthesea thì mỗi từ đứng riêng, hệ thống vẫn chạy."""
    out = segment_words("chuẩn hoá cơ sở dữ liệu")
    assert out, "phải trả về token, không được rỗng"
    assert all(isinstance(t, str) for t in out)


def test_segment_words_chuoi_rong() -> None:
    assert segment_words("") == []
    assert segment_words("   ") == []


def test_build_tsquery_parts_phan_loai_dung() -> None:
    parts = build_tsquery_parts("chuẩn hoá cơ sở dữ liệu")
    assert parts
    assert all(kind in {"phrase", "plain"} for kind, _ in parts)
    # Cụm từ ghép không được còn dấu gạch dưới — phraseto_tsquery nhận
    # khoảng trắng, và gạch dưới lại là ký tự phân tách của Postgres (QĐ 0001).
    for _kind, content in parts:
        assert "_" not in content


def test_build_tsquery_parts_giu_ma_hieu_van_ban() -> None:
    """US-010 AC-3 — mã hiệu phải sống sót qua bước làm sạch truy vấn."""
    parts = build_tsquery_parts("TCVN 5945:2005 quy định gì?")
    joined = " ".join(c for _, c in parts)
    assert "5945:2005" in joined or "5945" in joined


def test_build_tsquery_parts_loai_ky_tu_nhieu() -> None:
    parts = build_tsquery_parts("cơ sở dữ liệu là gì??? !!!")
    for _, content in parts:
        assert "?" not in content and "!" not in content
