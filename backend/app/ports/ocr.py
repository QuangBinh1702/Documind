"""Cổng nhận dạng chữ — US-024.

Cùng khuôn với `EmbeddingProvider` và `RerankProvider`: một giao thức hẹp, mỗi
engine là một adapter, và tầng service không biết engine nào đang chạy.

Ở đây khuôn đó có ích hơn hai cổng kia, vì US-048 yêu cầu **so ba engine** trên
ba trục CER · thời gian · VRAM. So sánh chỉ làm được khi đổi engine là đổi một
dòng cấu hình chứ không phải sửa đường xử lý.

Trả về **toạ độ**, không chỉ trả về chữ
--------------------------------------
`OcrLine` mang theo hộp bao của dòng chữ trên trang. Bỏ toạ độ đi thì tiện hơn
nhiều, nhưng khi ấy tài liệu scan mất khả năng tô sáng trích dẫn (US-015) — đúng
thứ phân biệt đồ án này với một chatbot đọc tài liệu. Tài liệu có lớp text giữ
được toạ độ nhờ PyMuPDF; tài liệu scan phải lấy từ chính OCR, không có nguồn nào
khác.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["OcrLine", "OcrPage", "OcrProvider"]


@dataclass(frozen=True, slots=True)
class OcrLine:
    """Một dòng chữ nhận ra được, kèm vị trí trên trang."""

    text: str
    confidence: float
    """Độ tin cậy trong [0, 1]. US-027 dùng nó để tô những chỗ cần người rà."""

    x0: float
    y0: float
    x1: float
    y1: float
    """Hộp bao, theo **hệ toạ độ trang PDF** (điểm, gốc trên-trái) — cùng hệ với
    `bbox` của PyMuPDF, để hai đường có text và scan gộp lại được."""


@dataclass(frozen=True, slots=True)
class OcrPage:
    page: int
    lines: list[OcrLine]
    seconds: float

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def confidence(self) -> float:
        """Độ tin cậy trung bình, có trọng số theo độ dài dòng.

        Trung bình đơn thuần làm một dòng hai ký tự nặng ngang một đoạn văn, nên
        vài mẩu nhiễu ở lề trang kéo tụt điểm của cả trang.
        """
        if not self.lines:
            return 0.0
        tong = sum(len(x.text) for x in self.lines) or 1
        return sum(x.confidence * len(x.text) for x in self.lines) / tong


@runtime_checkable
class OcrProvider(Protocol):
    name: str

    def read_page(self, image_png: bytes, page: int, scale: float) -> OcrPage:
        """Nhận dạng một trang đã render sang PNG.

        `scale` là tỉ lệ giữa ảnh và trang PDF (ảnh 200 dpi thì scale = 200/72).
        Adapter chia toạ độ cho nó để trả về đúng hệ toạ độ trang.
        """
        ...
