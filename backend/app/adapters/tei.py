"""Máy khách chung cho dịch vụ Text Embeddings Inference (TEI).

TEI là máy chủ suy luận của Hugging Face; bản dùng ở đây do khoa vận hành tại
`https://textembedding.dutai.io.vn` và phục vụ **đúng hai mô hình mà đồ án đang
chạy cục bộ** — `BAAI/bge-m3` và `BAAI/bge-reranker-v2-m3`. Vì vậy đổi sang nó
là đổi **chỗ chạy**, không phải đổi mô hình: số chiều vẫn 1024, lược đồ không
đổi, và không phải lập chỉ mục lại.

Điều phải nói rõ trong báo cáo
------------------------------
Dùng adapter này thì **nội dung tài liệu rời khỏi máy**, ở CẢ Privacy Mode.
Nhúng và xếp hạng lại chạy ở mọi lượt hỏi và mọi lượt nạp tài liệu, không phân
biệt chế độ — nên câu "Privacy Mode không gửi gì ra ngoài" ở `settings.py` sẽ
không còn đúng. `Settings.warnings()` phát cảnh báo tương ứng, và đó là lý do
mặc định vẫn là mô hình cục bộ.

Vì sao gọi `/embed` và `/rerank` chứ không gọi `/v1/embeddings`
--------------------------------------------------------------
Dịch vụ có endpoint tương thích OpenAI, nhưng dùng nó nghĩa là thêm một phụ
thuộc SDK để nhận về đúng những con số ấy dưới một lớp bọc sâu hơn — và TEI
không có endpoint OpenAI nào cho rerank, nên vẫn phải gọi thẳng cho nửa còn
lại. Một cách gọi cho cả hai thì ít chỗ hỏng hơn.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

from app.settings import settings

__all__ = ["TeiClient", "TeiError"]

log = logging.getLogger(__name__)

# Tài liệu dịch vụ chỉ liệt kê 502/504 là "đang bận hoặc quá tải", nhưng TEI còn
# trả 429 khi hàng đợi đầy và 503 khi mô hình đang nạp lại. Cả bốn đều là trạng
# thái *tạm thời*: để chúng nổi lên thành lỗi thì một lượt nạp tài liệu hỏng vì
# lý do không liên quan gì tới chất lượng hệ thống, và giữa một lượt chạy đánh
# giá thì nó làm hỏng luôn phép đo.
_TRANSIENT = frozenset({429, 500, 502, 503, 504})
RETRIES = 2
BACKOFF_S = 1.0


class TeiError(RuntimeError):
    """Lỗi đã dịch sang câu nói được cho người vận hành, không phải mã HTTP."""


class TeiClient:
    """Gọi HTTP có thử lại, dùng chung cho adapter nhúng và adapter rerank."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.tei_base_url).rstrip("/")
        self.api_key = api_key or settings.tei_api_key
        self.timeout = timeout or settings.tei_timeout_seconds

    @property
    def host(self) -> str:
        """Tên miền — đi vào `name` của adapter để metadata lần chạy nói rõ
        số đo này đến từ máy nào (US-045 AC-5)."""
        return urlparse(self.base_url).netloc or self.base_url

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise TeiError(
                "Chưa cấu hình TEI_API_KEY. Đặt khoá trong .env, hoặc đặt "
                "EMBEDDING_PROVIDER=bge-m3 / RERANK_PROVIDER=bge để chạy bằng "
                "mô hình cục bộ."
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        """Gọi một endpoint suy luận và trả về JSON đã giải mã."""
        import httpx

        url = f"{self.base_url}{path}"
        headers = self._headers()
        attempt = 0

        while True:
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(self.timeout, connect=10.0)
                ) as client:
                    response = client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                # Hết giờ cũng là trạng thái tạm thời — thường là lô quá lớn gặp
                # lúc máy chủ bận. Thử lại, rồi mới chịu thua.
                if attempt < RETRIES:
                    attempt = self._cho_roi_thu_lai(path, "hết giờ", attempt)
                    continue
                raise TeiError(
                    f"Dịch vụ TEI ({self.host}) không trả lời trong "
                    f"{self.timeout:.0f}s sau {RETRIES} lần thử. Tăng "
                    f"TEI_TIMEOUT_SECONDS, giảm TEI_MAX_BATCH, hoặc chuyển về "
                    f"mô hình cục bộ."
                ) from exc
            except httpx.ConnectError as exc:
                raise TeiError(
                    f"Không kết nối được tới dịch vụ TEI ({self.host}). Kiểm tra "
                    f"mạng và TEI_BASE_URL, hoặc chuyển về mô hình cục bộ."
                ) from exc

            if response.status_code in _TRANSIENT and attempt < RETRIES:
                attempt = self._cho_roi_thu_lai(path, str(response.status_code), attempt)
                continue

            if response.status_code != 200:
                raise TeiError(
                    _explain(response.status_code, response.text[:300], path, self.host)
                )

            return response.json()

    def _cho_roi_thu_lai(self, path: str, ly_do: str, attempt: int) -> int:
        delay = BACKOFF_S * 2**attempt
        log.warning(
            "TEI %s trả về %s, chờ %.1fs rồi thử lại (lần %d/%d)",
            path, ly_do, delay, attempt + 1, RETRIES,
        )
        time.sleep(delay)
        return attempt + 1

    def health(self, path: str) -> None:
        """Hỏi một endpoint `/health/*`. Ném `TeiError` nếu không sẵn sàng.

        Dùng trong `warm()`: hỏng vì sai khoá hay sai URL phải lộ ra lúc khởi
        động, chứ không phải giữa chừng một lượt nạp tài liệu khi thanh tiến
        trình đã ở 85%.
        """
        import httpx

        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=10.0)) as client:
                response = client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise TeiError(
                f"Không hỏi được tình trạng dịch vụ TEI ({self.host}{path}): {exc}"
            ) from exc

        if response.status_code != 200:
            raise TeiError(
                _explain(response.status_code, response.text[:300], path, self.host)
            )


def _explain(status: int, body: str, path: str, host: str) -> str:
    """Đổi mã lỗi HTTP thành câu chỉ được việc phải làm.

    Bảng mã lỗi lấy từ tài liệu dịch vụ; phần "cách khắc phục" nói tên tham số
    trong `.env` chứ không nói tên trường trong payload, vì người gặp thông báo
    này là người vận hành chứ không phải người viết adapter.
    """
    if status in (401, 403):
        return (
            f"Dịch vụ TEI ({host}) từ chối khoá API. Kiểm tra TEI_API_KEY trong "
            f".env, hoặc chuyển về mô hình cục bộ."
        )
    if status == 404:
        return (
            f"Dịch vụ TEI ({host}) không có endpoint {path}. Kiểm tra TEI_BASE_URL "
            f"— nó phải là gốc tên miền, không kèm /v1."
        )
    if status == 413:
        return (
            f"Gói tin gửi tới {path} vượt quá giới hạn kích thước. Giảm "
            f"TEI_MAX_BATCH (khuyến nghị ≤ 32), hoặc giảm CHUNK_TOKENS nếu từng "
            f"đoạn quá dài."
        )
    if status == 422:
        return f"Dịch vụ TEI từ chối khuôn dạng payload gửi tới {path}: {body}"
    if status in _TRANSIENT:
        return (
            f"Dịch vụ TEI ({host}) đang quá tải và vẫn chưa phục hồi sau "
            f"{RETRIES} lần thử lại (HTTP {status}). Thử lại sau ít phút, giảm "
            f"TEI_MAX_BATCH, hoặc chuyển về mô hình cục bộ."
        )
    return f"Dịch vụ TEI trả về {status} ở {path}: {body}"
