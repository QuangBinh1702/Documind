"""Chọn nhà cung cấp mô hình ngôn ngữ theo chế độ — US-030.

Privacy Mode và Fast Mode là hai adapter của cùng một cổng, chọn bằng tham số
`mode` chứ không bằng nhánh mã ở tầng service.
"""

from __future__ import annotations

import logging

from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.llm.gemini import GeminiLLMProvider
from app.adapters.llm.local import LocalLLMProvider
from app.ports.llm import LLMProvider
from app.settings import Mode, settings

__all__ = [
    "FakeLLMProvider",
    "GeminiLLMProvider",
    "LocalLLMProvider",
    "get_llm_provider",
]

log = logging.getLogger(__name__)

_cache: dict[str, LLMProvider] = {}


def get_llm_provider(mode: Mode | None = None) -> LLMProvider:
    """Trả về adapter cho chế độ yêu cầu.

    `privacy` → mô hình cục bộ, không có lưu lượng ra ngoài.
    `fast`    → Gemini, nhanh hơn nhưng câu hỏi và ngữ cảnh rời khỏi máy.
    """
    mode = mode or settings.default_mode

    if settings.llm_provider == "fake":
        log.warning(
            "Đang dùng mô hình ngôn ngữ GIẢ (LLM_PROVIDER=fake). "
            "Nó ghép câu trả lời từ ngữ cảnh, không sinh ngôn ngữ."
        )
        return _cache.setdefault("fake", FakeLLMProvider())

    if mode == "privacy":
        return _cache.setdefault("privacy", LocalLLMProvider())
    return _cache.setdefault("fast", GeminiLLMProvider())
