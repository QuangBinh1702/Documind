"""Adapter mô hình cục bộ — Privacy Mode (US-029).

Gọi một máy chủ tương thích OpenAI chạy trên **chính máy này**: Ollama, vLLM hay
llama.cpp đều phơi ra cùng giao diện đó. Nhờ vậy việc chọn runtime — quyết định
thuộc spike S2 (`SPEC-v1.md` §10) — không ảnh hưởng tới mã nguồn, chỉ đổi một
dòng cấu hình.

`is_local = True` là điều làm nên US-029 AC-3: rút dây mạng, hệ thống vẫn hỏi
đáp đầy đủ.

**Đừng trỏ `LOCAL_LLM_BASE_URL` sang một dịch vụ đám mây.** Nó chạy được, nhưng
cờ `is_local` khi đó nói dối: giao diện sẽ không hiện cảnh báo, và hệ thống âm
thầm gửi nội dung tài liệu ra ngoài trong khi vẫn tự nhận là chạy cục bộ. Dùng
`OllamaCloudLLMProvider` cho trường hợp đó — nó khai báo đúng sự thật.
"""

from __future__ import annotations

from app.adapters.llm.openai_compat import OpenAICompatProvider
from app.settings import settings

__all__ = ["LocalLLMProvider"]


class LocalLLMProvider(OpenAICompatProvider):
    is_local = True

    loi_ket_noi = (
        "Không kết nối được máy chủ mô hình cục bộ tại {base_url}.\n"
        "Khởi động Ollama (`ollama serve`) hoặc vLLM, hoặc chuyển sang Fast Mode "
        "nếu có mạng."
    )

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        super().__init__(
            model=model or settings.local_llm_model,
            base_url=base_url or settings.local_llm_base_url,
        )

    @property
    def name(self) -> str:
        return f"local:{self.model}"
