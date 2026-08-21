"""Fixture dùng chung.

Điểm đáng chú ý: các PDF thử được **sinh ra tại chỗ** bằng PyMuPDF thay vì
kèm sẵn tệp mẫu. Nhờ vậy bộ test chạy được trên máy sạch, không phụ thuộc tài
liệu có bản quyền, và nội dung mong đợi luôn biết trước chính xác.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Nội dung tiếng Việt có đủ dấu, dùng chung cho nhiều test.
VI_PARAGRAPHS = [
    "Điều 5. Phạm vi áp dụng",
    "Quy chế này áp dụng cho toàn bộ hoạt động đào tạo trình độ đại học.",
    "Người học được cấp bằng khi hoàn thành chương trình và đạt chuẩn đầu ra.",
    "Theo TCVN 5945:2005 thì nước thải phải đạt loại B trước khi xả ra môi trường.",
]


def _font_file() -> str | None:
    """Tìm một font có dấu tiếng Việt trên máy đang chạy test."""
    candidates = [
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


@pytest.fixture(scope="session")
def vi_font() -> str:
    font = _font_file()
    if font is None:
        pytest.skip("Không tìm thấy font hỗ trợ tiếng Việt trên máy này")
    return font


@pytest.fixture
def make_pdf(tmp_path: Path, vi_font: str):
    """Sinh một PDF nhiều trang với nội dung cho trước.

    Trả về hàm ``make_pdf(pages: list[list[str]]) -> Path`` — mỗi trang là một
    danh sách đoạn văn.
    """
    fitz = pytest.importorskip("fitz", reason="cần PyMuPDF")

    def _make(pages: list[list[str]], name: str = "test.pdf") -> Path:
        doc = fitz.open()
        for paragraphs in pages:
            page = doc.new_page()
            y = 72.0
            for para in paragraphs:
                page.insert_text(
                    (72, y),
                    para,
                    fontsize=11,
                    fontfile=vi_font,
                    fontname="vi",
                )
                y += 28
            page.clean_contents()
        path = tmp_path / name
        doc.save(str(path))
        doc.close()
        return path

    return _make


@pytest.fixture
def scanned_pdf(tmp_path: Path):
    """PDF không có lớp text — mô phỏng bản scan."""
    fitz = pytest.importorskip("fitz", reason="cần PyMuPDF")

    doc = fitz.open()
    for _ in range(3):
        page = doc.new_page()
        # Vẽ hình khối, không chèn chữ nào.
        page.draw_rect(fitz.Rect(72, 72, 500, 300), color=(0, 0, 0), width=1)
    path = tmp_path / "scan.pdf"
    doc.save(str(path))
    doc.close()
    return path
