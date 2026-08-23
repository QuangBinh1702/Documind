"""Nạp ảnh — US-025, US-026.

Cùng nguyên tắc với `test_ocr.py`: engine là giả, đường ống là thật. Phần đáng
test ở đây là **tiền xử lý** — nó chạy trước OCR nên hỏng ở đây thì mọi thứ phía
sau chỉ thấy một tấm ảnh trắng và không có gì báo lỗi.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from app.adapters.extract import ExtractionError
from app.adapters.extract.image import extract_image, tien_xu_ly
from app.services.ingest import SUFFIX_TO_KIND, mime_cho
from app.services.upload import UploadError, _kiem_noi_dung
from app.settings import settings
from tests.test_ocr import FakeOcr, dong

Image = pytest.importorskip("PIL.Image", reason="cần Pillow")


def anh(tmp_path: Path, size=(1600, 900), mode="RGB", name="anh.png") -> Path:
    p = tmp_path / name
    Image.new(mode, size, "white" if mode != "RGBA" else (255, 255, 255, 0)).save(p)
    return p


# ═══════════════════════════════════════════════════════
# Tiền xử lý — US-026
# ═══════════════════════════════════════════════════════


def test_anh_nho_duoc_phong_to():
    """Chữ dưới ~32 px thì OCR trả về rỗng mà không báo lỗi gì."""
    ket = tien_xu_ly(Image.new("RGB", (400, 200), "white"))
    assert max(ket.size) == settings.image_min_side
    assert ket.width / ket.height == pytest.approx(2.0), "phải giữ tỉ lệ khung"


def test_anh_lon_duoc_thu_nho():
    ket = tien_xu_ly(Image.new("RGB", (8000, 4000), "white"))
    assert max(ket.size) == settings.image_max_side


def test_anh_dung_kich_thuoc_thi_giu_nguyen():
    ket = tien_xu_ly(Image.new("RGB", (2000, 1000), "white"))
    assert ket.size == (2000, 1000)


def test_nen_trong_suot_thanh_trang_khong_thanh_den():
    """Ảnh PNG chụp màn hình rất hay có nền trong suốt.

    Bỏ kênh alpha một cách ngây thơ biến nền trong suốt thành đen, và chữ đen
    trên nền đen thì OCR không đọc ra gì — một ca hỏng hoàn toàn im lặng.
    """
    goc = Image.new("RGBA", (2000, 1000), (0, 0, 0, 0))
    ket = tien_xu_ly(goc)
    assert ket.mode == "RGB"
    assert ket.getpixel((10, 10)) == (255, 255, 255)


def test_ket_qua_luon_la_RGB():
    for mode in ("L", "P", "RGBA", "CMYK"):
        assert tien_xu_ly(Image.new(mode, (2000, 1000))).mode == "RGB"


# ═══════════════════════════════════════════════════════
# Trích xuất
# ═══════════════════════════════════════════════════════


def test_anh_thanh_tai_lieu_mot_trang(tmp_path: Path):
    ocr = FakeOcr({1: [dong("Điều 1. Phạm vi", y=100), dong("Nội dung điều một", y=140)]})
    ket = extract_image(anh(tmp_path), ocr)

    assert ket.page_count == 1
    assert "Điều 1. Phạm vi" in ket.full_text
    assert ket.method == "image-ocr:fake-ocr"


def test_toa_do_la_pixel_cua_anh(tmp_path: Path):
    """`scale=1.0` — ảnh không có hệ toạ độ điểm nào để quy đổi về.

    Truyền nhầm tỉ lệ dpi vào đây sẽ làm vùng tô sáng lệch, và không có test nào
    khác bắt được vì đường PDF vẫn đúng.
    """
    ocr = FakeOcr({1: [dong("chu", y=250.0, x=180.0)]})
    ket = extract_image(anh(tmp_path), ocr)

    assert ocr.scales == [1.0]
    hop = ket.bboxes_for(0, len(ket.full_text))
    assert (hop[0].x0, hop[0].y0) == (180.0, 250.0)


def test_sap_theo_thu_tu_doc(tmp_path: Path):
    ocr = FakeOcr({1: [dong("ba", y=300), dong("mot", y=100), dong("hai", y=200)]})
    assert extract_image(anh(tmp_path), ocr).full_text.split() == ["mot", "hai", "ba"]


def test_anh_khong_co_chu_bao_OCR_EMPTY(tmp_path: Path):
    with pytest.raises(ExtractionError) as loi:
        extract_image(anh(tmp_path), FakeOcr({}))
    assert loi.value.code == "OCR_EMPTY"
    assert "chữ" in loi.value.message_vi


def test_tep_hong_bao_IMAGE_UNREADABLE(tmp_path: Path):
    p = tmp_path / "hong.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\nnhung phan con lai la rac")
    with pytest.raises(ExtractionError) as loi:
        extract_image(p, FakeOcr({1: [dong("x", 10)]}))
    assert loi.value.code == "IMAGE_UNREADABLE"


# ═══════════════════════════════════════════════════════
# Nhận tệp
# ═══════════════════════════════════════════════════════


def test_bon_duoi_anh_deu_cho_kind_image():
    for duoi in (".png", ".jpg", ".jpeg", ".webp"):
        assert SUFFIX_TO_KIND[duoi] == "image"


def test_mime_tra_theo_duoi_khong_theo_kind():
    """Bốn đuôi cùng `kind='image'` nhưng MIME khác nhau.

    Ghi sai MIME vào MinIO thì trình duyệt tải ảnh về thay vì hiển thị nó.
    """
    assert mime_cho("a.png") == "image/png"
    assert mime_cho("a.jpg") == "image/jpeg"
    assert mime_cho("a.jpeg") == "image/jpeg"
    assert mime_cho("a.webp") == "image/webp"
    assert mime_cho("a.pdf") == "application/pdf"


def test_png_doi_ten_thanh_jpg_bi_tu_choi():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    with pytest.raises(UploadError) as loi:
        _kiem_noi_dung(png, "image", ".jpg")
    assert loi.value.code == "CONTENT_MISMATCH"


def test_anh_that_thi_qua():
    dem = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(dem, format="PNG")
    _kiem_noi_dung(dem.getvalue(), "image", ".png")  # không ném là đạt


def test_vo_RIFF_khong_phai_webp_bi_tu_choi():
    """RIFF là vỏ chung của WAV và AVI, không riêng WebP."""
    wav = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 16
    with pytest.raises(UploadError) as loi:
        _kiem_noi_dung(wav, "image", ".webp")
    assert loi.value.code == "CONTENT_MISMATCH"
