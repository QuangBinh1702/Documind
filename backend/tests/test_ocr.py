"""Nhận dạng chữ — US-024.

Không test engine thật ở đây. Engine thật cần vài trăm MB mô hình, mất hàng
chục giây mỗi trang trên CPU, và kết quả của nó phụ thuộc phiên bản mô hình —
ba tính chất khiến nó không thuộc về một bộ test chạy sau mỗi lần sửa mã. Chất
lượng của engine được đo riêng ở US-048 và ghi ở `docs/evidence/`.

Cái test ở đây là **đường ống quanh engine**: thứ tự đọc, quy đổi toạ độ, cách
gộp dòng, và việc tài liệu scan sau khi OCR vẫn giữ được bất biến INV-1 như
tài liệu có lớp text. Đó là phần mã của đồ án, và là phần hỏng âm thầm.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.extract import ExtractionError
from app.adapters.extract.scanned import extract_scanned_pdf
from app.ports.ocr import OcrLine, OcrPage, OcrProvider
from app.settings import settings


class FakeOcr:
    """Engine giả trả về đúng những dòng được dựng sẵn cho từng trang.

    Ghi lại `scale` nhận được, vì quy đổi toạ độ sai là loại lỗi không làm test
    nào đỏ nhưng làm vùng tô sáng lệch đúng bằng tỉ lệ dpi.
    """

    name = "fake-ocr"

    def __init__(self, theo_trang: dict[int, list[OcrLine]], seconds: float = 0.5) -> None:
        self._theo_trang = theo_trang
        self._seconds = seconds
        self.scales: list[float] = []
        self.pages_seen: list[int] = []

    def read_page(self, image_png: bytes, page: int, scale: float) -> OcrPage:
        assert image_png[:8] == b"\x89PNG\r\n\x1a\n", "phải nhận được PNG"
        self.scales.append(scale)
        self.pages_seen.append(page)
        return OcrPage(
            page=page,
            lines=self._theo_trang.get(page, []),
            seconds=self._seconds,
        )


def dong(text: str, y: float, x: float = 72.0, conf: float = 0.95) -> OcrLine:
    return OcrLine(text=text, confidence=conf, x0=x, y0=y, x1=x + 200.0, y1=y + 12.0)


# ═══════════════════════════════════════════════════════
# Cổng — hợp đồng của kiểu dữ liệu
# ═══════════════════════════════════════════════════════


def test_fake_thoa_giao_thuc_ocr_provider():
    assert isinstance(FakeOcr({}), OcrProvider)


def test_do_tin_cay_co_trong_so_theo_do_dai():
    """Một mẩu nhiễu hai ký tự không được kéo tụt điểm của cả trang."""
    trang = OcrPage(
        page=1,
        lines=[
            dong("x" * 100, y=100, conf=1.0),
            dong("ab", y=200, conf=0.0),
        ],
        seconds=0.1,
    )
    # Trung bình đơn thuần cho 0.50; có trọng số cho 100/102 ≈ 0.98.
    assert trang.confidence == pytest.approx(100 / 102, abs=1e-3)


def test_do_tin_cay_trang_rong_la_khong():
    assert OcrPage(page=1, lines=[], seconds=0.0).confidence == 0.0


def test_text_ghep_theo_thu_tu_dong_duoc_giao():
    trang = OcrPage(page=1, lines=[dong("a", 10), dong("b", 20)], seconds=0.0)
    assert trang.text == "a\nb"


# ═══════════════════════════════════════════════════════
# Thứ tự đọc
# ═══════════════════════════════════════════════════════


def test_sap_lai_theo_thu_tu_doc(scanned_pdf: Path):
    """OCR trả dòng theo thứ tự nó phát hiện; văn bản phải ra theo thứ tự đọc."""
    ocr = FakeOcr(
        {
            1: [dong("ba", y=300), dong("mot", y=100), dong("hai", y=200)],
            2: [],
            3: [],
        }
    )
    ket = extract_scanned_pdf(scanned_pdf, ocr)
    assert ket.full_text.split() == ["mot", "hai", "ba"]


def test_cung_hang_thi_sap_theo_cot(scanned_pdf: Path):
    """Hai dòng lệch nhau vài điểm y là cùng một hàng chữ, không phải hai hàng.

    Không có dung sai thì trang chụp hơi nghiêng bị xé thành nhiều hàng, và thứ
    tự trái-phải trong hàng biến mất.
    """
    ocr = FakeOcr(
        {
            1: [
                dong("phai", y=101.0, x=400.0),
                dong("trai", y=100.0, x=72.0),
                dong("duoi", y=140.0, x=72.0),
            ],
            2: [],
            3: [],
        }
    )
    ket = extract_scanned_pdf(scanned_pdf, ocr)
    assert ket.full_text.split() == ["trai", "phai", "duoi"]


# ═══════════════════════════════════════════════════════
# Toạ độ
# ═══════════════════════════════════════════════════════


def test_scale_truyen_cho_engine_la_ti_le_dpi(scanned_pdf: Path):
    ocr = FakeOcr({1: [dong("noi dung", 100)], 2: [], 3: []})
    extract_scanned_pdf(scanned_pdf, ocr)
    mong_doi = settings.ocr_dpi / 72.0
    assert ocr.scales == [mong_doi] * 3
    assert ocr.pages_seen == [1, 2, 3]


def test_bbox_giu_nguyen_he_toa_do_trang(scanned_pdf: Path):
    """Toạ độ adapter trả về phải đi thẳng vào `blocks`, không bị đổi lần nữa.

    Adapter đã chia cho `scale` rồi. Chia thêm một lần ở đây là lỗi hai lần quy
    đổi — vùng tô sáng co lại đúng bằng bình phương tỉ lệ dpi.
    """
    ocr = FakeOcr({1: [dong("Dieu 1. Pham vi", y=120.0, x=72.0)], 2: [], 3: []})
    ket = extract_scanned_pdf(scanned_pdf, ocr)

    hop = ket.bboxes_for(0, len(ket.full_text))
    assert len(hop) == 1
    assert (hop[0].page, hop[0].x0, hop[0].y0) == (1, 72.0, 120.0)
    assert (hop[0].x1, hop[0].y1) == (272.0, 132.0)


# ═══════════════════════════════════════════════════════
# Ca biên
# ═══════════════════════════════════════════════════════


def test_khong_doc_duoc_gi_thi_bao_OCR_EMPTY(scanned_pdf: Path):
    with pytest.raises(ExtractionError) as loi:
        extract_scanned_pdf(scanned_pdf, FakeOcr({}))
    assert loi.value.code == "OCR_EMPTY"


def test_dong_toan_khoang_trang_bi_bo_qua(scanned_pdf: Path):
    ocr = FakeOcr({1: [dong("   ", 100), dong("that", 200)], 2: [], 3: []})
    ket = extract_scanned_pdf(scanned_pdf, ocr)
    assert ket.full_text.split() == ["that"]


def test_dong_tin_cay_thap_van_duoc_giu(scanned_pdf: Path):
    """Đếm để cảnh báo, không tự ý bỏ.

    Bỏ dòng dưới ngưỡng sẽ tạo lỗ hổng im lặng giữa tài liệu — người dùng không
    thấy đoạn thiếu, chỉ thấy câu trả lời sai. US-027 cho họ rà lại thay vì
    quyết định hộ.
    """
    ocr = FakeOcr({1: [dong("mo nhung co", y=100, conf=0.01)], 2: [], 3: []})
    ket = extract_scanned_pdf(scanned_pdf, ocr)
    assert "mo nhung co" in ket.full_text


def test_method_ghi_ten_engine(scanned_pdf: Path):
    """Số liệu US-048 so ba engine — không ghi tên thì không truy được ra ai đọc."""
    ket = extract_scanned_pdf(scanned_pdf, FakeOcr({1: [dong("x", 100)], 2: [], 3: []}))
    assert ket.method == "ocr:fake-ocr"


def test_moi_trang_deu_co_trong_ban_do(scanned_pdf: Path):
    """Trang OCR ra rỗng vẫn phải chiếm một chỗ, nếu không số trang trích dẫn lệch."""
    ket = extract_scanned_pdf(scanned_pdf, FakeOcr({2: [dong("chi trang hai", 100)]}))
    assert ket.page_count == 3
    assert [p.page for p in ket.pages] == [1, 2, 3]
    assert ket.page_of(ket.full_text.index("chi trang hai")) == 2


def test_offset_cat_lai_dung_noi_dung(scanned_pdf: Path):
    """INV-1 trên đường OCR — cùng bất biến với đường có lớp text."""
    ocr = FakeOcr(
        {
            1: [dong("Điều 1. Phạm vi điều chỉnh", 100), dong("Quy chế này áp dụng", 130)],
            2: [dong("Điều 2. Đối tượng", 100)],
            3: [dong("Điều 3. Chương trình", 100)],
        }
    )
    ket = extract_scanned_pdf(scanned_pdf, ocr)
    for khoi in ket.blocks:
        cat = ket.full_text[khoi.char_start : khoi.char_end]
        assert cat.strip(), "khối rỗng không nên tồn tại"
        assert cat in ket.full_text
    assert "Điều 2. Đối tượng" in ket.full_text
