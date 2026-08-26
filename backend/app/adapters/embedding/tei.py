"""Adapter nhúng qua dịch vụ TEI — cùng mô hình `BAAI/bge-m3`, khác chỗ chạy.

Vì sao đáng có adapter này
--------------------------
`BgeM3EmbeddingProvider` nạp 2.2 GB trọng số và chạy trên `DEVICE`. Trên laptop
CPU nó chạy được nhưng chậm khoảng 10–20 lần (`SPEC-v1.md` §10.0), nên phát
triển thì phải hạ tham số xuống mức không còn giống cấu hình thật. Dịch vụ TEI
chạy đúng mô hình ấy trên GPU của khoa, nên nó trả lại cấu hình thật cho máy
phát triển mà không cần máy đích.

Đánh đổi: **nội dung mọi tài liệu được nạp đều rời khỏi máy**, kể cả ở Privacy
Mode. Xem `app/adapters/tei.py`.

Vì sao không có `revision` để ghim
----------------------------------
`EMBEDDING_REVISION` là cơ chế US-045 AC-5 dùng để tái lập kết quả, nhưng dịch
vụ bên ngoài có thể đổi trọng số bất kỳ lúc nào mà phía gọi không biết. Bù lại
bằng cách đưa tên miền vào `name`, để metadata của lần chạy nói rõ số đo này
đến từ máy nào — và khi cần chốt số cho báo cáo thì chạy lại bằng adapter cục
bộ có ghim revision.
"""

from __future__ import annotations

import logging
import math

from app.adapters.tei import TeiClient, TeiError
from app.settings import settings

__all__ = ["TeiEmbeddingProvider"]

log = logging.getLogger(__name__)

EMBED_PATH = "/embed"
HEALTH_PATH = "/health/embedding"

# Sai lệch cho phép khi kiểm tra vector đã chuẩn hoá L2 chưa. Nới tay vì dịch vụ
# trả về float32 đã qua JSON; chặt hơn thì báo động giả, lỏng hơn thì không bắt
# được ca `normalize` bị bỏ qua (chuẩn của bge-m3 lệch hẳn khỏi 1).
_NORM_TOL = 1e-3


class TeiEmbeddingProvider:
    """Nhúng bằng bge-m3 chạy trên máy chủ TEI, trả về vector đã chuẩn hoá L2."""

    def __init__(
        self,
        model_name: str | None = None,
        client: TeiClient | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.model_name = model_name or settings.embedding_model
        self.client = client or TeiClient()
        self.dim = settings.embedding_dim
        # Hai trần khác nhau và phải lấy cái nhỏ hơn: `EMBEDDING_BATCH_SIZE` là
        # lựa chọn về bộ nhớ của mô hình cục bộ, còn `TEI_MAX_BATCH` là giới hạn
        # gói tin của dịch vụ (vượt thì 413).
        self.batch_size = max(
            1, min(batch_size or settings.embedding_batch_size, settings.tei_max_batch)
        )
        self._da_kiem_tra = False

    @property
    def name(self) -> str:
        """Ghi cả tên miền: số đo từ máy chủ khác là số đo khác."""
        return f"tei:{self.model_name}@{self.client.host}"

    @property
    def da_san_sang(self) -> bool:
        """Luôn sẵn sàng — không có trọng số nào phải tải về máy này.

        Đây chính là điều chỗ gọi muốn biết: `warm()` sắp tới chỉ là một lượt
        hỏi tình trạng, không phải một lượt tải vài GB.
        """
        return True

    def warm(self) -> None:
        """Hỏi tình trạng mô hình, và để lỗi cấu hình nổ ra ngay tại đây.

        Ném lỗi thay vì ghi log: sai khoá hay sai URL mà im lặng đi tiếp thì nó
        sẽ nổ ở giữa lượt nhúng, sau khi tài liệu đã được tách đoạn và thanh
        tiến trình đã nhảy tới 85%.
        """
        self.client.health(HEALTH_PATH)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            lo = texts[i : i + self.batch_size]
            data = self.client.post(
                EMBED_PATH,
                {
                    "inputs": lo,
                    # Phần của hợp đồng cổng, không phải tuỳ chọn — xem
                    # `ports/embedding.py`.
                    "normalize": True,
                    # bge-m3 nhận 8192 token còn CHUNK_TOKENS mặc định là 768,
                    # nên bình thường không đoạn nào chạm trần. Bật `truncate`
                    # để một đoạn bất thường bị cắt chứ không làm hỏng cả lượt
                    # nạp tài liệu bằng một lỗi 413.
                    "truncate": True,
                },
            )
            vectors.extend(self._kiem_tra(data, lo))

        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def _kiem_tra(self, data: object, lo: list[str]) -> list[list[float]]:
        """Khẳng định phản hồi đúng hình dạng trước khi nó đi vào cơ sở dữ liệu.

        Ba phép kiểm ở đây bắt ba lỗi mà nếu lọt thì đều **hỏng im lặng**: lệch
        số lượng làm vector gán nhầm đoạn, lệch số chiều làm Postgres từ chối
        ghi bằng một thông báo khó lần ra, còn vector chưa chuẩn hoá thì vẫn
        ghi được và vẫn tính ra điểm cosine — chỉ là sai.
        """
        if not isinstance(data, list) or not all(isinstance(v, list) for v in data):
            raise TeiError(
                f"Dịch vụ TEI trả về khuôn dạng lạ ở {EMBED_PATH}: mong đợi mảng "
                f"các vector, nhận được {type(data).__name__}."
            )
        if len(data) != len(lo):
            raise TeiError(
                f"Dịch vụ TEI trả về {len(data)} vector cho {len(lo)} đoạn văn bản."
            )

        vectors = [[float(x) for x in v] for v in data]

        if not self._da_kiem_tra and vectors:
            dai = len(vectors[0])
            if dai != self.dim:
                raise TeiError(
                    f"{self.model_name} trên {self.client.host} sinh vector {dai} "
                    f"chiều nhưng cấu hình và lược đồ mong đợi {self.dim}. Sửa "
                    f"EMBEDDING_DIM và cột source_chunks.embedding cho khớp."
                )
            do_dai = math.sqrt(sum(x * x for x in vectors[0]))
            if not math.isclose(do_dai, 1.0, abs_tol=_NORM_TOL):
                raise TeiError(
                    f"Dịch vụ TEI trả về vector chưa chuẩn hoá (|v| = {do_dai:.4f}). "
                    f"Hợp đồng cổng yêu cầu L2 = 1 vì truy vấn dùng toán tử cosine "
                    f"của pgvector — xem ports/embedding.py."
                )
            self._da_kiem_tra = True

        return vectors

    def unload(self) -> None:
        """Không có gì để giải phóng — trọng số không nằm trên máy này.

        Vẫn khai báo để chính sách nạp/giải phóng ở US-057 gọi được đồng nhất
        trên mọi adapter mà không phải hỏi adapter nào có hàm này.
        """
        return None
