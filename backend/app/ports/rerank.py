"""Cổng xếp hạng lại — US-011.

Khác biệt cốt lõi so với `EmbeddingProvider`
--------------------------------------------
Nhúng nén mỗi văn bản thành **một vector độc lập**, rồi so sánh bằng khoảng
cách. Điều đó khiến nó nhanh và lập chỉ mục trước được, nhưng cũng khiến nó
không bao giờ nhìn thấy câu hỏi và đoạn văn **cùng lúc**.

Bộ xếp hạng lại là một **cross-encoder**: nó nhận cả cặp và đọc chúng cùng
nhau, nên bắt được những quan hệ mà hai vector rời rạc không biểu diễn nổi —
phủ định, điều kiện, đối tượng áp dụng. Đổi lại nó đắt gấp nhiều lần, nên chỉ
chạy trên vài chục ứng viên đã lọc chứ không chạy trên cả kho.

Thang điểm là một phần của hợp đồng
-----------------------------------
Điểm trả về **bắt buộc nằm trong [0, 1]**, đã qua sigmoid. Cổng ngưỡng τ ở
US-031 so sánh trực tiếp với con số này; nếu adapter trả về logit thô (khoảng
−10…+10 với `bge-reranker-v2-m3`) thì `τ = 0.35` trở nên vô nghĩa và hệ thống
sẽ nhận mọi thứ là "đủ căn cứ" mà không báo lỗi gì.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["RerankProvider"]


@runtime_checkable
class RerankProvider(Protocol):
    name: str
    """Định danh ghi vào metadata lần chạy đánh giá (US-045 AC-5)."""

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Chấm mức độ liên quan của từng đoạn với câu hỏi.

        Trả về danh sách **cùng thứ tự và cùng độ dài** với `documents`; việc
        sắp xếp là của chỗ gọi. Mỗi điểm nằm trong ``[0, 1]``, càng cao càng
        liên quan.
        """
        ...
