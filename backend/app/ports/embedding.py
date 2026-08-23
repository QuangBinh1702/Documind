"""Cổng sinh vector biểu diễn văn bản.

Tầng nghiệp vụ chỉ biết giao diện này, không biết mô hình nào đứng sau. Ba lợi
ích trực tiếp cho đồ án (`SPEC-v1.md` §3.1):

* **Ablation US-046 chạy được mà không sửa code** — đổi mô hình chỉ là đổi
  adapter qua cấu hình.
* **Test chạy trên laptop** — adapter giả không cần GPU, không cần tải 2.2 GB.
* Chương 2 của báo cáo có một mục lý thuyết thật về Ports & Adapters.

Vì sao tách `embed_documents` và `embed_query`
----------------------------------------------
`bge-m3` xử lý hai bên như nhau, nhưng nhiều họ mô hình khác thì không: dòng
E5 yêu cầu tiền tố ``query:`` và ``passage:``, và dùng sai tiền tố làm chất
lượng truy xuất tụt mà **không báo lỗi gì**. Tách sẵn hai phương thức để khi
đổi mô hình ở US-062 thì chỗ cần sửa nằm trong adapter, không lan ra ngoài.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["EmbeddingProvider"]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Sinh vector đã chuẩn hoá độ dài (L2 norm = 1).

    Chuẩn hoá là một phần của hợp đồng, không phải chi tiết cài đặt: truy vấn
    trong `SPEC-v1.md` §5.1 dùng toán tử ``<=>`` của pgvector (khoảng cách
    cosine) và cột chỉ mục HNSW được tạo với ``vector_cosine_ops``. Nếu adapter
    trả về vector chưa chuẩn hoá thì điểm số vẫn tính ra được nhưng sai lệch,
    và không có gì báo lỗi.
    """

    name: str
    """Định danh ghi vào metadata lần chạy đánh giá (US-045 AC-5)."""

    dim: int
    """Số chiều. Phải khớp `settings.embedding_dim` và cột `vector(1024)`."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Nhúng các đoạn tri thức khi lập chỉ mục."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Nhúng câu hỏi khi truy xuất."""
        ...

    @property
    def da_san_sang(self) -> bool:
        """Mô hình đã sẵn sàng dùng ngay chưa.

        Không phải chi tiết cài đặt: worker hỏi nó để biết lượt `warm()` sắp
        tới là tức thời hay là một lượt tải về vài GB, rồi **nói cho người dùng
        biết trước**. Thiếu thông tin ấy thì lần chạy đầu tiên trông y hệt một
        hệ thống bị treo.
        """
        ...

    def warm(self) -> None:
        """Nạp mô hình ngay, thay vì đợi lượt nhúng đầu tiên.

        Adapter nào không có gì để nạp thì để rỗng — đó là lý do cổng khai nó
        chứ không bắt chỗ gọi phải biết adapter nào cần và adapter nào không.
        """
        ...
