"""Bảo vệ bất biến INV-2 — US-055.

Đây là một trong ba test không bao giờ được cắt (`SPEC.md` §J.2). Làm một mình
thì bộ test là lớp soát duy nhất, và chuẩn hoá sai gây ra một loạt lỗi im lặng.
"""

from __future__ import annotations

import unicodedata

import pytest

from app.text.normalize import is_normalized, normalize, strip_accents

# "Tiếng Việt" ở hai dạng Unicode. Trông giống hệt nhau trên màn hình.
NFC = unicodedata.normalize("NFC", "Tiếng Việt có dấu")
NFD = unicodedata.normalize("NFD", "Tiếng Việt có dấu")


def test_nfd_va_nfc_ban_dau_KHAC_nhau() -> None:
    """Tiền đề của cả module: hai dạng thật sự khác nhau ở mức byte.

    Nếu test này đỏ thì môi trường có gì đó lạ và các test sau vô nghĩa.
    """
    assert NFC != NFD
    assert len(NFD) > len(NFC), "NFD phải dài hơn vì dấu tách thành codepoint riêng"


def test_nfd_duoc_dua_ve_nfc() -> None:
    out = normalize(NFD)
    assert out == NFC
    assert unicodedata.is_normalized("NFC", out)


def test_nfc_giu_nguyen() -> None:
    assert normalize(NFC) == NFC


def test_idempotent() -> None:
    """normalize(normalize(x)) == normalize(x) cho mọi đầu vào.

    Tính chất này cho phép gọi normalize ở bất kỳ đâu mà không sợ hỏng dữ liệu,
    và là lý do đường xử lý chính không cần kiểm tra trước khi gọi.
    """
    for raw in [NFD, NFC, "", "a\r\nb", "x​y", "Đ ề", "5.2\tvà 5945:2005"]:
        once = normalize(raw)
        assert normalize(once) == once, f"không idempotent với {raw!r}"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\r\nb", "a\nb"),
        ("a\rb", "a\nb"),
        ("a\r\n\r\nb", "a\n\nb"),
    ],
)
def test_xuong_dong_duoc_thong_nhat(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "invisible",
    [
        "​",  # zero width space
        "‌",  # zero width non-joiner
        "‍",  # zero width joiner
        "⁠",  # word joiner
        "﻿",  # BOM
        "­",  # soft hyphen
    ],
)
def test_ky_tu_vo_hinh_bi_loai(invisible: str) -> None:
    """Ký tự vô hình không hiển thị nhưng vẫn tính vào len() — chúng làm lệch
    offset và phá so khớp chuỗi snippet mà không báo lỗi."""
    assert normalize(f"Cơ{invisible}sở") == "Cơsở"


@pytest.mark.parametrize(
    "space",
    [" ", " ", " ", " ", "　", " "],
)
def test_khoang_trang_la_thanh_dau_cach_thuong(space: str) -> None:
    assert normalize(f"Cơ{space}sở") == "Cơ sở"


def test_khong_gop_nhieu_dau_cach() -> None:
    """Gộp khoảng trắng thuộc bước làm sạch của trình trích xuất, không phải
    của chuẩn hoá. Chuẩn hoá phải đoán được và tối thiểu."""
    assert normalize("Cơ    sở") == "Cơ    sở"


def test_ky_tu_dieu_khien_bi_loai_nhung_giu_tab_va_xuong_dong() -> None:
    assert normalize("a\x00b\x07c") == "abc"
    assert normalize("a\tb\nc") == "a\tb\nc"


def test_ghep_qua_ky_tu_vo_hinh() -> None:
    """Xoá ký tự vô hình TRƯỚC khi NFC, nên tổ hợp bị chia cắt vẫn ghép lại được.

    Đây là lý do thứ tự thao tác trong normalize() quan trọng.
    """
    # e + ZWSP + dấu sắc  ->  bỏ ZWSP  ->  NFC  ->  é
    assert normalize("e​́") == "é"


def test_chuoi_rong() -> None:
    assert normalize("") == ""


def test_is_normalized() -> None:
    assert is_normalized(NFC)
    assert not is_normalized(NFD)
    assert not is_normalized("a\r\nb")


# ── strip_accents ──────────────────────────────────────


def test_bo_dau_giu_nguyen_do_dai() -> None:
    """Giữ nguyên độ dài để so sánh không dấu vẫn ánh xạ được về offset gốc."""
    for s in ["Tiếng Việt", "Đường lối", "cơ sở dữ liệu", "ỷ ỹ ự ượ"]:
        assert len(strip_accents(s)) == len(normalize(s)), s


def test_bo_dau_dung_ket_qua() -> None:
    assert strip_accents("Cơ sở dữ liệu") == "Co so du lieu"
    assert strip_accents("Đường") == "Duong"
    assert strip_accents("NGHỊ ĐỊNH") == "NGHI DINH"


def test_bo_dau_chi_dung_toi_chu_cai_tieng_viet() -> None:
    """Chỉ bỏ dấu của những chữ cái thuộc bảng chữ tiếng Việt.

    ``é`` **là** chữ tiếng Việt (bé, mé, tré…) nên bị bỏ dấu, kể cả khi nó nằm
    trong một từ mượn như "café". Ngược lại ``ï`` không thuộc bảng chữ tiếng
    Việt nên giữ nguyên. Đây là hành vi đúng cho một bộ bỏ dấu tiếng Việt.
    """
    assert strip_accents("café naïve") == "cafe naïve"
    assert strip_accents("Zürich") == "Zürich"
    assert strip_accents("bé") == "be"
