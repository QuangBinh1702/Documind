"""Adapter Gemini — Fast Mode (US-030).

`is_local = False`. Tầng service dựa vào cờ đó để biết một lần gọi sẽ rời khỏi
máy, và US-032 AC-2 yêu cầu không có lần gọi nào xảy ra khi người dùng chưa
đồng ý.

**Điều phải nói rõ trong báo cáo:** ở Fast Mode, cả câu hỏi lẫn các đoạn tài
liệu được chọn đều được gửi tới Google. Đó là đánh đổi có ý thức giữa tốc độ
và quyền riêng tư, và là lý do Privacy Mode tồn tại.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from app.ports.llm import Message
from app.settings import settings

__all__ = ["GeminiLLMProvider"]

log = logging.getLogger(__name__)


class GeminiLLMProvider:
    is_local = False

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or settings.gemini_model
        self.api_key = api_key or settings.gemini_api_key
        self._client = None

    @property
    def name(self) -> str:
        return f"gemini:{self.model}"

    def _load(self):
        if self._client is not None:
            return self._client

        if not self.api_key:
            # US-030 AC-5: hướng dẫn cấu hình, không văng lỗi khó hiểu.
            raise RuntimeError(
                "Chưa cấu hình GEMINI_API_KEY. Đặt khoá trong .env để dùng Fast Mode, "
                "hoặc chuyển sang Privacy Mode để chạy hoàn toàn bằng mô hình cục bộ."
            )

        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise RuntimeError(
                "Thiếu google-generativeai. Cài bằng: pip install google-generativeai"
            ) from exc

        genai.configure(api_key=self.api_key)
        self._client = genai
        return genai

    async def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        genai = self._load()

        model = genai.GenerativeModel(self.model, system_instruction=system)
        history = [
            {"role": "model" if m["role"] == "assistant" else "user",
             "parts": [m["content"]]}
            for m in messages
        ]

        config = {"temperature": temperature}
        if max_tokens:
            config["max_output_tokens"] = max_tokens

        response = await model.generate_content_async(
            history, generation_config=config, stream=True
        )
        async for piece in response:
            if piece.text:
                yield piece.text
