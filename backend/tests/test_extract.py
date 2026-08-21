"""Trích xuất tài liệu — US-007.

Test quan trọng nhất là `test_offset_cua_moi_khoi_deu_dung`: nó kiểm chứng
nguyên tắc "offset được dựng lên, không đi tìm". Nếu nguyên tắc này giữ ở tầng
trích xuất thì INV-1 ở tầng chunker gần như được cho không.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.extract import extract, extract_plain
from app.adapters.extract.base import ExtractionError, TextBuilder
from app.adapters.extract.pdf import count_chars_per_page, extract_pdf
from app.adapters.extract.plain import decode_bytes
from app.text.normalize import is_normalized
from tests.conftest import VI_PARAGRAPHS

# ── TextBuilder: nền của mọi trình trích xuất ──────────


def test_offset_cua_moi_khoi_deu_dung() -> None:
    """`full_text[block.char_start:block.char_end]` phải ra đúng nội dung khối.

    Đây là bản thu nhỏ của INV-1 ở tầng trích xuất.
    """
    b = TextBuilder()
    b.start_page(1)
    for para in VI_PARAGRAPHS:
        b.add_block(para)
    b.end_page()
    r = b.build(method="test")

    for blk in r.blocks:
        assert r.full_text[blk.char_start : blk.char_end] in [p.strip() for p in VI_PARAGRAPHS]


def test_khoi_lap_lai_van_co_offset_rieng() -> None:
    """Ca mà cách "đi tìm chuỗi" sẽ làm sai: cùng một đoạn xuất hiện hai lần.

    `find()` luôn trả về vị trí đầu tiên, nên khối thứ hai sẽ nhận offset của
    khối thứ nhất. Dựng offset lúc nối thì không có cơ hội sai.
    """
    b = TextBuilder()
    b.start_page(1)
    b.add_block("Điều 5. Phạm vi áp dụng")
    b.add_block("Nội dung ở giữa.")
    b.add_block("Điều 5. Phạm vi áp dụng")
    b.end_page()
    r = b.build(method="test")

    first, _, third = r.blocks
    assert first.char_start != third.char_start
    assert r.full_text[first.char_start : first.char_end] == "Điều 5. Phạm vi áp dụng"
    assert r.full_text[third.char_start : third.char_end] == "Điều 5. Phạm vi áp dụng"


def test_ban_do_trang_phu_kin_va_khong_chong() -> None:
    b = TextBuilder()
    for page_no in (1, 2, 3):
        b.start_page(page_no)
        b.add_block(f"Nội dung trang {page_no}.")
        b.end_page()
    r = b.build(method="test")

    assert [p.page for p in r.pages] == [1, 2, 3]
    assert r.pages[0].start == 0
    assert r.pages[-1].end == len(r.full_text)
    for a, c in zip(r.pages, r.pages[1:], strict=False):
        assert a.end == c.start


def test_ket_qua_luon_o_dang_chuan() -> None:
    b = TextBuilder()
    b.start_page(1)
    b.add_block("Tiéng Việt dạng NFD")  # đầu vào NFD
    b.end_page()
    r = b.build(method="test")
    assert is_normalized(r.full_text)


def test_khoi_rong_bi_bo_qua() -> None:
    b = TextBuilder()
    b.start_page(1)
    b.add_block("   ")
    b.add_block("\n\n")
    b.add_block("Có nội dung.")
    b.end_page()
    r = b.build(method="test")
    assert len(r.blocks) == 1


def test_page_of_tra_dung_trang() -> None:
    b = TextBuilder()
    for page_no in (1, 2):
        b.start_page(page_no)
        b.add_block(f"Trang {page_no}")
        b.end_page()
    r = b.build(method="test")

    assert r.page_of(r.pages[0].start) == 1
    assert r.page_of(r.pages[1].start) == 2


# ── PDF ────────────────────────────────────────────────


def test_trich_pdf_giu_dau_tieng_viet(make_pdf) -> None:
    """US-007 AC-6 — dấu tiếng Việt hiển thị đúng, không có ký tự lỗi mã hoá."""
    path = make_pdf([VI_PARAGRAPHS])
    r = extract_pdf(path)

    assert "Điều 5" in r.full_text
    assert "�" not in r.full_text
    assert r.quality.diacritic_ratio > 0.05


def test_trich_pdf_dung_so_trang(make_pdf) -> None:
    """US-007 AC-1 — mỗi đoạn kèm `page_no` chính xác."""
    path = make_pdf([["Nội dung trang một."], ["Nội dung trang hai."]])
    r = extract_pdf(path)

    assert r.page_count == 2
    pos = r.full_text.index("trang hai")
    assert r.page_of(pos) == 2


def test_trich_pdf_co_bbox(make_pdf) -> None:
    """US-007 AC-2 — mỗi khối text có toạ độ được lưu lại."""
    path = make_pdf([VI_PARAGRAPHS])
    r = extract_pdf(path)

    boxes = [b.bbox for b in r.blocks if b.bbox is not None]
    assert boxes, "không có khối nào mang toạ độ"
    for bb in boxes:
        assert bb.x1 > bb.x0 and bb.y1 > bb.y0
        assert bb.page == 1


def test_bboxes_for_tra_ve_vung_to_sang(make_pdf) -> None:
    """Cầu nối tới US-015: từ khoảng ký tự của chunk ra vùng toạ độ."""
    path = make_pdf([VI_PARAGRAPHS])
    r = extract_pdf(path)

    start = r.full_text.index("TCVN")
    boxes = r.bboxes_for(start, start + 10)
    assert boxes, "không tìm được vùng toạ độ cho đoạn chứa TCVN"


def test_pdf_scan_cho_ket_qua_gan_rong(scanned_pdf: Path) -> None:
    """US-023 — PDF không có lớp text phải lộ ra ngay, để định tuyến sang OCR."""
    r = extract_pdf(scanned_pdf)
    assert len(r.full_text.strip()) < 20
    assert r.page_count == 3


def test_dem_ky_tu_moi_trang(make_pdf, scanned_pdf: Path) -> None:
    """Dữ liệu cho US-023 AC-1."""
    text_pdf = make_pdf([VI_PARAGRAPHS, VI_PARAGRAPHS])
    assert all(c > 100 for c in count_chars_per_page(text_pdf))
    assert all(c < 100 for c in count_chars_per_page(scanned_pdf))


def test_pdf_hong_bao_loi_tieng_viet(tmp_path: Path) -> None:
    """US-007 AC-5 — lỗi có mã ổn định và thông báo tiếng Việt."""
    bad = tmp_path / "hong.pdf"
    bad.write_bytes(b"khong phai PDF")

    with pytest.raises(ExtractionError) as exc:
        extract_pdf(bad)
    assert exc.value.code == "PDF_UNREADABLE"
    assert "PDF" in exc.value.message_vi


# ── TXT / Markdown ─────────────────────────────────────


def test_trich_txt_utf8(tmp_path: Path) -> None:
    """US-007 AC-4 — nạp nguyên vẹn, giữ đúng tiếng Việt có dấu."""
    p = tmp_path / "a.txt"
    p.write_text("Cơ sở dữ liệu quan hệ.\n\nChuẩn hoá dữ liệu.", encoding="utf-8")
    r = extract_plain(p)

    assert "Cơ sở dữ liệu" in r.full_text
    assert "Chuẩn hoá" in r.full_text
    assert len(r.blocks) == 2


@pytest.mark.parametrize("eol", ["\n", "\r\n", "\r"])
def test_tach_doan_dung_voi_moi_kieu_xuong_dong(tmp_path: Path, eol: str) -> None:
    """Tệp soạn trên Windows dùng CRLF, trên Unix dùng LF, Mac cũ dùng CR.

    Tách đoạn phải cho kết quả như nhau. Trước đây hàm này tách trước khi chuẩn
    hoá nên với CRLF cả tệp gộp thành một khối — hỏng im lặng.
    """
    body = f"Đoạn một.{eol}{eol}Đoạn hai.{eol}{eol}Đoạn ba."
    p = tmp_path / "eol.txt"
    p.write_bytes(body.encode("utf-8"))

    r = extract_plain(p)
    assert len(r.blocks) == 3, f"với {eol!r} ra {len(r.blocks)} khối"


def test_trich_txt_co_bom(tmp_path: Path) -> None:
    p = tmp_path / "bom.txt"
    p.write_bytes("﻿Cơ sở dữ liệu".encode())
    r = extract_plain(p)
    assert r.full_text.startswith("Cơ sở")


def test_txt_rong_bao_loi(tmp_path: Path) -> None:
    p = tmp_path / "rong.txt"
    p.write_text("   \n\n  ", encoding="utf-8")
    with pytest.raises(ExtractionError) as exc:
        extract_plain(p)
    assert exc.value.code == "TEXT_EMPTY"


def test_decode_bytes_uu_tien_utf8() -> None:
    text, enc = decode_bytes("Cơ sở dữ liệu".encode())
    assert text == "Cơ sở dữ liệu"
    assert enc.startswith("utf-8")


def test_decode_bytes_khong_bao_gio_tra_ve_rong() -> None:
    """latin-1 giải mã được mọi chuỗi byte, nên hàm này không bao giờ bí."""
    text, enc = decode_bytes(bytes(range(128, 256)))
    assert text
    assert enc


# ── Điều phối ──────────────────────────────────────────


def test_extract_dieu_phoi_theo_kind(tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("# Tiêu đề\n\nNội dung.", encoding="utf-8")
    r = extract(p, "md")
    assert "Tiêu đề" in r.full_text


def test_kind_khong_ho_tro_bao_loi(tmp_path: Path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"x")
    with pytest.raises(ExtractionError) as exc:
        extract(p, "image")
    assert exc.value.code == "KIND_UNSUPPORTED"
