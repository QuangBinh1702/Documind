"""Chunking và bất biến INV-1 — US-008.

`SPEC.md` §J.6 gọi đây là điều thứ nhất trong ba điều quyết định thành bại:
nếu `char_start`/`char_end` sai thì toàn bộ tính năng trích dẫn hỏng, và lỗi
chỉ lộ ra ở M2 khi bấm chip và tô sáng nhảy sai chỗ.

`test_INV1_*` là những test **không bao giờ được cắt** (`SPEC.md` §J.2).
"""

from __future__ import annotations

import unicodedata
from itertools import pairwise

import pytest

from app.text.chunker import Chunk, chunk_document, chunk_text, estimate_tokens
from app.text.normalize import normalize
from tests.conftest import VI_PARAGRAPHS

LEGAL_DOC = """Chương I. Quy định chung

Điều 1. Phạm vi điều chỉnh
Quy chế này quy định về tổ chức và quản lý đào tạo trình độ đại học. Quy chế
áp dụng cho các đơn vị trực thuộc và người học tại cơ sở giáo dục.

Điều 2. Đối tượng áp dụng
Quy chế áp dụng đối với người học, giảng viên và cán bộ quản lý. Các đơn vị có
trách nhiệm phổ biến nội dung quy chế đến toàn thể người học.

Chương II. Tổ chức đào tạo

Điều 3. Chương trình đào tạo
Chương trình đào tạo được xây dựng theo chuẩn đầu ra đã công bố. Việc điều
chỉnh chương trình phải được hội đồng khoa học thông qua.
"""

MARKDOWN_DOC = """# Cơ sở dữ liệu

Nội dung mở đầu về cơ sở dữ liệu quan hệ.

## Chuẩn hoá dữ liệu

Dạng chuẩn thứ ba yêu cầu bảng đã ở dạng chuẩn thứ hai. Không tồn tại phụ
thuộc hàm bắc cầu giữa các thuộc tính không khoá.

### Dạng chuẩn 3NF

Nội dung chi tiết về dạng chuẩn thứ ba và cách áp dụng trong thực tế.
"""

SAMPLES = [
    LEGAL_DOC,
    MARKDOWN_DOC,
    "Một câu ngắn.",
    " ".join(VI_PARAGRAPHS),
    "Không có dấu chấm nào cả trong toàn bộ văn bản này",
    "A" * 5000,  # một "câu" dài hơn mọi hạn mức
    unicodedata.normalize("NFD", "Tiếng Việt dạng NFD có dấu đầy đủ. Câu thứ hai."),
]


# ══════════════════════════════════════════════════════
# INV-1 — không bao giờ được cắt
# ══════════════════════════════════════════════════════


@pytest.mark.parametrize("raw", SAMPLES)
def test_INV1_cat_lai_bang_offset_ra_dung_noi_dung(raw: str) -> None:
    """`full_text[char_start:char_end] == content` với MỌI chunk.

    Đây chính là bài kiểm tra mà US-008 AC-5 yêu cầu.
    """
    full = normalize(raw)
    for c in chunk_text(full, max_tokens=120):
        assert full[c.char_start : c.char_end] == c.content, (
            f"chunk {c.chunk_index} lệch offset: "
            f"kỳ vọng {c.content[:40]!r}, thực tế {full[c.char_start:c.char_end][:40]!r}"
        )


@pytest.mark.parametrize("raw", SAMPLES)
def test_INV1_van_dung_voi_dau_vao_NFD(raw: str) -> None:
    """US-008 AC-6 — ca đầu vào NFD.

    Văn bản từ macOS và một phần đầu ra OCR ở dạng NFD. Nếu chuẩn hoá không xảy
    ra trước khi tính offset thì mọi chunk lệch, và không có lỗi nào được báo.
    """
    full = normalize(unicodedata.normalize("NFD", raw))
    for c in chunk_text(full, max_tokens=120):
        assert full[c.char_start : c.char_end] == c.content


@pytest.mark.parametrize("raw", SAMPLES)
def test_INV1_offset_luon_hop_le(raw: str) -> None:
    full = normalize(raw)
    for c in chunk_text(full, max_tokens=120):
        assert 0 <= c.char_start < c.char_end <= len(full)
        assert c.content  # không có chunk rỗng


def test_INV1_khong_hong_khi_noi_dung_lap_lai() -> None:
    """Ca mà cách "đi tìm chuỗi" sẽ sai: cùng một đoạn xuất hiện nhiều lần."""
    repeated = "Điều 5. Phạm vi áp dụng. " * 40
    full = normalize(repeated)
    chunks = chunk_text(full, max_tokens=60)

    assert len(chunks) > 1
    starts = [c.char_start for c in chunks]
    assert len(set(starts)) == len(starts), "hai chunk trùng vị trí bắt đầu"
    for c in chunks:
        assert full[c.char_start : c.char_end] == c.content


# ══════════════════════════════════════════════════════
# Ranh giới và kích thước
# ══════════════════════════════════════════════════════


def test_chunk_khong_vuot_qua_han_muc_dang_ke() -> None:
    """US-008 AC-1 — độ dài chunk nằm trong hạn mức.

    Cho phép vượt nhẹ vì chunk luôn kết thúc ở ranh giới câu, không cắt giữa câu.
    """
    full = normalize(LEGAL_DOC)
    max_tokens = 100
    for c in chunk_text(full, max_tokens=max_tokens):
        assert c.token_count <= max_tokens * 1.6, f"chunk {c.chunk_index} quá dài"


def test_ranh_gioi_chunk_roi_vao_ranh_gioi_cau() -> None:
    """US-008 AC-2 — không cắt giữa câu."""
    full = normalize(LEGAL_DOC)
    for c in chunk_text(full, max_tokens=100):
        tail = c.content.rstrip()
        # Kết thúc bằng dấu câu, hoặc là chunk cuối của một phần (tiêu đề).
        assert tail[-1] in ".!?:" or c.content == c.content.strip()


def test_chunk_dai_hon_han_muc_van_duoc_cat() -> None:
    """Một "câu" dài 5000 ký tự không được làm chunk phình vô hạn."""
    full = normalize("A" * 5000)
    chunks = chunk_text(full, max_tokens=100)
    assert len(chunks) > 1
    for c in chunks:
        assert full[c.char_start : c.char_end] == c.content


def test_van_ban_rong_khong_sinh_chunk() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_van_ban_ngan_hon_mot_chunk() -> None:
    """US-008 AC-6 — ca văn bản ngắn hơn một chunk."""
    full = normalize("Một câu ngắn.")
    chunks = chunk_text(full, max_tokens=768)
    assert len(chunks) == 1
    assert chunks[0].content == "Một câu ngắn."


def test_chunk_index_lien_tuc_tu_khong() -> None:
    chunks = chunk_text(normalize(LEGAL_DOC), max_tokens=100)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chong_lap_giup_chunk_ke_nhau_giao_nhau() -> None:
    """Chồng lặp tránh mất ngữ cảnh ở chỗ cắt (US-008 AC-1)."""
    full = normalize(LEGAL_DOC)
    chunks = chunk_text(full, max_tokens=80, overlap_ratio=0.3, respect_headings=False)
    assert len(chunks) > 2
    overlaps = sum(1 for a, b in pairwise(chunks) if b.char_start < a.char_end)
    assert overlaps > 0, "không có cặp chunk nào chồng lặp"


# ══════════════════════════════════════════════════════
# Tiêu đề
# ══════════════════════════════════════════════════════


def test_heading_path_theo_cau_truc_markdown() -> None:
    """US-008 AC-3 — ưu tiên cắt tại ranh giới tiêu đề."""
    chunks = chunk_text(normalize(MARKDOWN_DOC), max_tokens=200)
    paths = [c.heading_path for c in chunks if c.heading_path]

    assert paths, "không chunk nào có heading_path"
    assert any("Chuẩn hoá dữ liệu" in p for p in paths)
    # Tiêu đề lồng nhau tạo thành đường dẫn phân cấp.
    assert any(">" in p for p in paths)


def test_heading_path_theo_cau_truc_van_ban_phap_quy() -> None:
    """Chương / Điều / Mục — cấu trúc của miền tài liệu chính trong đồ án."""
    chunks = chunk_text(normalize(LEGAL_DOC), max_tokens=120)
    paths = [c.heading_path for c in chunks if c.heading_path]

    assert any("Chương I" in p for p in paths)
    assert any("Điều 1" in p for p in paths)
    # Điều nằm dưới Chương trong phân cấp.
    nested = [p for p in paths if "Chương" in p and "Điều" in p]
    assert nested, f"không có đường dẫn lồng nhau: {paths}"


def test_tat_respect_headings_thi_khong_cat_theo_tieu_de() -> None:
    with_h = chunk_text(normalize(LEGAL_DOC), max_tokens=400, respect_headings=True)
    without_h = chunk_text(normalize(LEGAL_DOC), max_tokens=400, respect_headings=False)
    assert len(with_h) >= len(without_h)


# ══════════════════════════════════════════════════════
# Nối với tài liệu đã trích xuất
# ══════════════════════════════════════════════════════


def test_chunk_document_gan_so_trang(make_pdf) -> None:
    """US-008 AC-4 — mỗi chunk có `page_no`."""
    from app.adapters.extract import extract_pdf

    path = make_pdf([VI_PARAGRAPHS, VI_PARAGRAPHS])
    result = extract_pdf(path)
    chunks = chunk_document(result, max_tokens=60)

    assert chunks
    assert all(c.page_no in (1, 2) for c in chunks)
    assert {c.page_no for c in chunks} == {1, 2}, "phải có chunk ở cả hai trang"


def test_chunk_document_gan_bbox(make_pdf) -> None:
    """US-008 AC-4 — `bbox` là cầu nối tới tô sáng trích dẫn (US-015)."""
    from app.adapters.extract import extract_pdf

    path = make_pdf([VI_PARAGRAPHS])
    result = extract_pdf(path)
    chunks = chunk_document(result, max_tokens=60)

    with_box = [c for c in chunks if c.bbox]
    assert with_box, "không chunk nào có toạ độ"
    for c in with_box:
        for b in c.bbox:
            assert b.x1 > b.x0 and b.y1 > b.y0
            assert b.page == c.page_no


def test_chunk_document_van_giu_INV1(make_pdf) -> None:
    """INV-1 phải đúng trên đường đi thật: PDF → trích xuất → chunk."""
    from app.adapters.extract import extract_pdf

    path = make_pdf([VI_PARAGRAPHS, VI_PARAGRAPHS, VI_PARAGRAPHS])
    result = extract_pdf(path)

    for c in chunk_document(result, max_tokens=80):
        assert result.full_text[c.char_start : c.char_end] == c.content


# ══════════════════════════════════════════════════════
# Đếm token
# ══════════════════════════════════════════════════════


def test_estimate_tokens_tang_theo_do_dai() -> None:
    assert estimate_tokens("ngắn") < estimate_tokens("một câu dài hơn nhiều lần")


def test_estimate_tokens_khong_bao_gio_bang_khong() -> None:
    assert estimate_tokens("") >= 1
    assert estimate_tokens("a") >= 1


def test_co_the_thay_bo_dem_token() -> None:
    """Tham số `count_tokens` tồn tại để M2 truyền tokenizer thật của bge-m3."""
    calls: list[str] = []

    def counting(text: str) -> int:
        calls.append(text)
        return len(text.split())

    chunk_text(normalize(LEGAL_DOC), max_tokens=30, count_tokens=counting)
    assert calls, "bộ đếm truyền vào không được gọi"


def test_chunk_la_kieu_bat_bien() -> None:
    c = Chunk(chunk_index=0, content="x", char_start=0, char_end=1, token_count=1)
    with pytest.raises((AttributeError, TypeError)):
        c.content = "y"  # type: ignore[misc]
