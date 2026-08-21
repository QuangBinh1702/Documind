"""Adapter Ollama Cloud — trọng số mở, chạy trên máy người khác.

Vì sao có adapter riêng thay vì trỏ lại adapter cục bộ
-------------------------------------------------------
Ollama Cloud nói đúng cùng giao thức với Ollama chạy máy mình, nên về mặt kỹ
thuật chỉ cần đổi `LOCAL_LLM_BASE_URL` là xong. Nhưng làm vậy thì `is_local` nói
dối, và cờ đó không phải chi tiết cấu hình: US-032 AC-2 dựa vào nó để biết một
lượt gọi có rời khỏi máy hay không, và giao diện dựa vào nó để hiện cảnh báo.
Một hệ thống lấy *"dữ liệu không rời khỏi máy"* làm luận điểm mà lại im lặng gửi
nội dung tài liệu đi thì hỏng ở chỗ tệ nhất có thể hỏng.

Nên đây là adapter riêng, `is_local = False`, và nó đi cùng Fast Mode chứ không
đi cùng Privacy Mode.

Vị trí trong đồ án
------------------
Ba cách triển khai cùng một hệ thống, cho một bảng so sánh mà luận văn tham khảo
không có::

    Privacy Mode   mô hình cục bộ trên máy đích   dữ liệu không đi đâu
    Ollama Cloud   trọng số mở, máy người khác    tái lập được, không khoá nhà cung cấp
    Gemini         mô hình đóng                   nhanh, nhưng không biết bên trong là gì

Trọng số mở là điểm mạnh riêng của cột giữa cho phần *"kết quả có tái lập
được không?"*: một nhà cung cấp mô hình đóng có thể đổi mô hình dưới cùng một
tên bất cứ lúc nào, còn `gemma4:31b` thì ai tải về cũng ra đúng trọng số đó.

Cảnh báo về VRAM
----------------
`gemma4:31b` lượng tử q4 cần khoảng 18–20 GB. Máy đích 16 GB còn phải giữ
`bge-m3` và `bge-reranker-v2-m3`, nên **mô hình này không chạy được cục bộ ở
đó**. Số liệu đo bằng nó là số liệu của cột "cloud", không phải của Privacy
Mode — muốn đo Privacy Mode thì phải chạy một mô hình vừa ngân sách VRAM.
"""

from __future__ import annotations

from app.adapters.llm.openai_compat import OpenAICompatProvider
from app.settings import settings

__all__ = ["OllamaCloudLLMProvider"]


class OllamaCloudLLMProvider(OpenAICompatProvider):
    is_local = False

    loi_ket_noi = (
        "Không kết nối được Ollama Cloud tại {base_url}. Chế độ này cần mạng; "
        "chuyển sang Privacy Mode để chạy hoàn toàn cục bộ."
    )

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(
            model=model or settings.ollama_cloud_model,
            base_url=base_url or settings.ollama_cloud_base_url,
            api_key=api_key if api_key is not None else settings.ollama_cloud_api_key,
        )

    @property
    def name(self) -> str:
        return f"ollama-cloud:{self.model}"

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            # US-030 AC-5: hướng dẫn cấu hình, không để lỗi 401 khó hiểu nổi lên.
            raise RuntimeError(
                "Chưa cấu hình OLLAMA_CLOUD_API_KEY. Lấy khoá ở "
                "ollama.com/settings/keys, hoặc chuyển sang Privacy Mode."
            )
        return super()._headers()
