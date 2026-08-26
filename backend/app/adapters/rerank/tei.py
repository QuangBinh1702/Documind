"""Adapter xếp hạng lại qua dịch vụ TEI — `BAAI/bge-reranker-v2-m3`.

Đây là adapter được lợi nhiều nhất từ việc chạy ở xa. Cross-encoder chạy tuyến
tính theo số ứng viên, nên trên CPU `RERANK_CANDIDATES=50` biến mỗi câu hỏi
thành hàng phút — chính chú thích ở `settings.py` khuyên hạ xuống 10–20. Qua
TEI thì 50 ứng viên là một lượt gọi trên GPU, tức là lấy lại được cấu hình thật
trên máy phát triển.

Đánh đổi: **nội dung các đoạn tài liệu ứng viên rời khỏi máy ở mọi lượt hỏi**,
kể cả Privacy Mode. Xem `app/adapters/tei.py`.

Cái bẫy: phản hồi ĐÃ ĐƯỢC SẮP XẾP
---------------------------------
`/rerank` trả về danh sách xếp theo điểm giảm dần, mỗi phần tử mang `index` trỏ
về vị trí trong `texts` đã gửi. Nhưng `RerankProvider.score()` bắt buộc trả về
điểm **cùng thứ tự với `documents`** — việc sắp xếp là của chỗ gọi.

Nhận thẳng danh sách ấy làm kết quả thì hệ thống vẫn chạy, vẫn ra câu trả lời,
chỉ là điểm bị gán cho nhầm đoạn: cổng ngưỡng τ chấm một đoạn nhưng ngữ cảnh
đưa vào mô hình lại là đoạn khác, và trích dẫn trỏ sai chỗ. Không có gì báo
lỗi. Vì vậy `_sap_lai_theo_index` không phải là chi tiết cài đặt.
"""

from __future__ import annotations

import logging

from app.adapters.tei import TeiClient, TeiError
from app.settings import settings

__all__ = ["TeiRerankProvider"]

log = logging.getLogger(__name__)

RERANK_PATH = "/rerank"
HEALTH_PATH = "/health/rerank"


class TeiRerankProvider:
    """Cross-encoder chạy trên máy chủ TEI, cho điểm đã sigmoid về [0, 1]."""

    def __init__(
        self,
        model_name: str | None = None,
        client: TeiClient | None = None,
        max_batch: int | None = None,
    ) -> None:
        self.model_name = model_name or settings.rerank_model
        self.client = client or TeiClient()
        self.max_batch = max(1, max_batch or settings.tei_max_batch)

    @property
    def name(self) -> str:
        return f"tei:{self.model_name}@{self.client.host}"

    def warm(self) -> None:
        self.client.health(HEALTH_PATH)

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []

        # `RERANK_CANDIDATES` mặc định là 50, lớn hơn mức 32 mà dịch vụ khuyến
        # nghị cho một gói tin. Chia lô thay vì bắt người vận hành phải nhớ hai
        # con số này ràng buộc nhau — điểm của mỗi cặp (câu hỏi, đoạn) độc lập
        # với các đoạn còn lại, nên chia lô không đổi kết quả.
        scores: list[float] = []
        for i in range(0, len(documents), self.max_batch):
            lo = documents[i : i + self.max_batch]
            data = self.client.post(
                RERANK_PATH,
                {
                    "query": query,
                    "texts": lo,
                    # Không xin lại văn bản: chỗ gọi đã có sẵn, và với 50 đoạn
                    # thì nó nhân đôi kích thước phản hồi mà không thêm gì.
                    "return_text": False,
                    "truncate": True,
                },
            )
            scores.extend(_sap_lai_theo_index(data, len(lo)))

        return scores


def _sap_lai_theo_index(data: object, so_luong: int) -> list[float]:
    """Đưa phản hồi đã sắp xếp về đúng thứ tự đầu vào.

    Kiểm luôn thang điểm tại đây. Nếu một bản triển khai TEI nào đó trả về logit
    thô (khoảng −10…+10 với bge-reranker-v2-m3) thay vì điểm đã sigmoid thì
    `TAU = 0.35` mất nghĩa và hệ thống sẽ nhận **mọi thứ** là "đủ căn cứ" —
    hỏng nặng, và không có triệu chứng nào ngoài việc câu trả lời tệ đi.
    """
    if not isinstance(data, list):
        raise TeiError(
            f"Dịch vụ TEI trả về khuôn dạng lạ ở {RERANK_PATH}: mong đợi một mảng, "
            f"nhận được {type(data).__name__}."
        )
    if len(data) != so_luong:
        raise TeiError(
            f"Reranker trả về {len(data)} điểm cho {so_luong} đoạn."
        )

    scores: list[float | None] = [None] * so_luong
    for item in data:
        try:
            vi_tri = int(item["index"])
            diem = float(item["score"])
        except (TypeError, KeyError, ValueError) as exc:
            raise TeiError(
                f"Phần tử trong phản hồi {RERANK_PATH} thiếu 'index' hoặc 'score': "
                f"{item!r}"
            ) from exc

        if not 0 <= vi_tri < so_luong:
            raise TeiError(
                f"Reranker trả về index {vi_tri} ngoài phạm vi 0..{so_luong - 1}."
            )
        if scores[vi_tri] is not None:
            raise TeiError(f"Reranker trả về index {vi_tri} hai lần.")
        if not 0.0 <= diem <= 1.0:
            raise TeiError(
                f"Reranker trả về điểm {diem} ngoài khoảng [0, 1]. Hợp đồng cổng "
                f"yêu cầu điểm ĐÃ qua sigmoid vì ngưỡng TAU so sánh trực tiếp với "
                f"con số này — xem ports/rerank.py."
            )
        scores[vi_tri] = diem

    # Không thể còn ô trống sau ba phép kiểm ở trên (đủ số lượng, không trùng,
    # không ngoài phạm vi), nhưng khẳng định lại để mypy yên tâm và để lỗi lộ ra
    # tại đây nếu có ai nới lỏng các phép kiểm kia.
    if any(s is None for s in scores):  # pragma: no cover - phòng thủ
        raise TeiError("Reranker bỏ sót một số đoạn trong phản hồi.")

    return [float(s) for s in scores]  # type: ignore[arg-type]
