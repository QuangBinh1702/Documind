"""Adapter nhúng tất định, không cần mô hình.

Vì sao cần
----------
`bge-m3` nặng 2.2 GB và trên laptop 2 GB VRAM phải chạy CPU, mất hàng giây cho
mỗi lô. Điều đó khiến không thể viết test cho **logic** truy xuất — RRF, cổng
ngưỡng, gắn trích dẫn — vì mỗi lần chạy test sẽ mất vài phút.

Adapter này thay thế mô hình ở tầng logic. Nó **không** đo được chất lượng
truy xuất; nó chỉ kiểm chứng rằng đường ống nối đúng.

Không phải nhiễu ngẫu nhiên
---------------------------
Nếu sinh vector ngẫu nhiên thuần thì mọi phép so sánh đều vô nghĩa và test
retrieval không khẳng định được gì. Ở đây dùng **thủ thuật băm** (hashing
trick): mỗi token được băm thành một số chiều mang dấu, cộng dồn rồi chuẩn hoá.

Kết quả là một phép nhúng **thật sự có ý nghĩa từ vựng**: hai đoạn dùng chung
nhiều từ sẽ có cosine cao. Nhờ vậy một test kiểu *"câu hỏi về chuẩn hoá dữ liệu
phải xếp chunk về chuẩn hoá lên trên chunk về tuyển sinh"* có ý nghĩa thật, chứ
không chỉ là kiểm tra kiểu dữ liệu.

Giới hạn phải nhớ
-----------------
Nó nắm được **trùng lặp từ vựng**, không nắm được **ngữ nghĩa**. Một câu hỏi
diễn đạt hoàn toàn khác tài liệu sẽ không khớp — đúng cái mà `bge-m3` sinh ra
để giải quyết. Vì vậy mọi con số chất lượng trong báo cáo **bắt buộc** phải đo
bằng mô hình thật trên máy đích (US-045 AC-5).
"""

from __future__ import annotations

import hashlib
import math
import re

__all__ = ["FakeEmbeddingProvider"]

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

# Mỗi token rải vào vài chiều thay vì một, để hai token khác nhau ít khi trùng
# hoàn toàn dấu vết. Bốn là đủ để giảm va chạm mà vẫn rẻ.
_SLOTS_PER_TOKEN = 4


class FakeEmbeddingProvider:
    """Nhúng bằng thủ thuật băm. Tất định, không phụ thuộc mô hình."""

    name = "fake-hash"

    def __init__(self, dim: int = 1024) -> None:
        if dim < 8:
            raise ValueError("dim phải ≥ 8")
        self.dim = dim

    # ── Nội bộ ─────────────────────────────────────────

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = _TOKEN.findall(text.lower())

        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            for slot in range(_SLOTS_PER_TOKEN):
                offset = slot * 3
                index = int.from_bytes(digest[offset : offset + 2], "big") % self.dim
                # Bit thấp nhất quyết định dấu, để token không chỉ cộng thêm mà
                # còn trừ đi — nếu không thì mọi vector đều nằm ở góc dương và
                # cosine giữa hai văn bản bất kỳ luôn cao.
                sign = 1.0 if digest[offset + 2] & 1 else -1.0
                vec[index] += sign

        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            # Văn bản rỗng hoặc không có token nào. Trả về một vector hợp lệ
            # thay vì vector 0 — pgvector tính cosine với vector 0 sẽ ra NaN.
            vec[0] = 1.0
            return vec

        return [v / norm for v in vec]

    # ── Hợp đồng EmbeddingProvider ─────────────────────

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @property
    def da_san_sang(self) -> bool:
        """Luôn sẵn sàng — adapter này băm chuỗi, không có trọng số nào."""
        return True

    def warm(self) -> None:
        """Không có gì để nạp."""
