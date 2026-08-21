"""Bộ xếp hạng lại giả — tất định, không cần mô hình.

Cùng lý do với `FakeEmbeddingProvider`: cho phép test **logic** của cổng ngưỡng
τ, thứ tự kết quả và đường từ chối trả lời mà không phải nạp 2.2 GB.

Cách chấm
---------
Tỉ lệ từ trong câu hỏi tìm thấy trong đoạn văn — tức **độ bao phủ câu hỏi**.
Chọn công thức này vì nó gần với thứ mà một cross-encoder thật sự thưởng: một
đoạn trả lời được câu hỏi thường nhắc lại phần lớn các khái niệm trong đó.

Phân bố điểm cũng được uốn cho gần với `bge-reranker-v2-m3` sau sigmoid: cặp
không liên quan rơi về gần 0, cặp liên quan mạnh vượt 0.7. Nhờ vậy ngưỡng mặc
định ``τ = 0.35`` phân tách có ý nghĩa trong test, thay vì phải đặt một giá trị
riêng chỉ dùng cho bản giả.

Giới hạn: nó **không** hiểu phủ định, điều kiện hay đối tượng áp dụng — đúng
những thứ mà cross-encoder thật sinh ra để giải quyết. Nó kiểm chứng đường ống,
không kiểm chứng chất lượng.
"""

from __future__ import annotations

import re

from app.text.normalize import strip_accents

__all__ = ["FakeRerankProvider"]

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

# Từ quá ngắn hầu như không mang thông tin phân biệt và làm nhiễu tỉ lệ.
_MIN_TOKEN_LEN = 2


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in _TOKEN.findall(strip_accents(text).lower())
        if len(t) >= _MIN_TOKEN_LEN
    }


class FakeRerankProvider:
    name = "fake-overlap"

    def score(self, query: str, documents: list[str]) -> list[float]:
        q = _tokens(query)
        if not q:
            return [0.0] * len(documents)

        out: list[float] = []
        for doc in documents:
            coverage = len(q & _tokens(doc)) / len(q)
            # Uốn cong để giãn vùng giữa: bao phủ 50% cho ~0.35, bao phủ 80%
            # cho ~0.72. Không uốn thì phần lớn cặp dồn quanh 0.2–0.4 và ngưỡng
            # τ không tách được gì.
            out.append(round(coverage**1.4 * 0.95 + coverage * 0.05, 6))
        return out
