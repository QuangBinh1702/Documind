"""Adapter Gemini — Fast Mode (US-030).

`is_local = False`. Tầng service dựa vào cờ đó để biết một lần gọi sẽ rời khỏi
máy, và US-032 AC-2 yêu cầu không có lần gọi nào xảy ra khi người dùng chưa
đồng ý.

**Điều phải nói rõ trong báo cáo:** ở Fast Mode, cả câu hỏi lẫn các đoạn tài
liệu được chọn đều được gửi tới Google. Đó là đánh đổi có ý thức giữa tốc độ
và quyền riêng tư, và là lý do Privacy Mode tồn tại.

Vì sao gọi HTTP thẳng thay vì dùng SDK
--------------------------------------
Google đã có hai thế hệ SDK Python cho Gemini, thế hệ đầu (`google-generativeai`)
nay ngừng hỗ trợ. REST endpoint thì không đổi. Gọi thẳng bằng `httpx` — thư
viện mà `LocalLLMProvider` vốn đã dùng — giữ hai adapter cùng một hình dạng,
bỏ được một phụ thuộc nặng, và không buộc đồ án chạy theo vòng đời phát hành
của một SDK.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from app.ports.llm import Message
from app.settings import settings

__all__ = ["GeminiLLMProvider"]

log = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

# Quá tải và vượt hạn mức là trạng thái *tạm thời*, rất hay gặp ở hạn mức miễn
# phí. Để chúng nổi lên thành lỗi thì một câu trả lời hỏng vì lý do không liên
# quan gì tới chất lượng hệ thống — và trong lúc chạy bộ đánh giá thì nó làm
# hỏng cả phép đo.
_TRANSIENT = frozenset({429, 500, 503})
RETRIES = 2
BACKOFF_S = 1.5

# Chỉ thử lại TRƯỚC khi có byte đầu tiên. Đứt giữa chừng thì không thử lại được:
# giao diện đã hiện phần đã nhận, và sinh lại từ đầu sẽ nối vào thành câu trùng
# lặp. Đó là lý do vòng lặp `return` ngay sau khi phát xong.


class GeminiLLMProvider:
    is_local = False

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or settings.gemini_model
        self.api_key = api_key or settings.gemini_api_key

    @property
    def name(self) -> str:
        return f"gemini:{self.model}"

    async def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            # US-030 AC-5: hướng dẫn cấu hình, không văng lỗi khó hiểu.
            raise RuntimeError(
                "Chưa cấu hình GEMINI_API_KEY. Đặt khoá trong .env để dùng Fast Mode, "
                "hoặc chuyển sang Privacy Mode để chạy hoàn toàn bằng mô hình cục bộ."
            )

        import httpx

        payload: dict = {
            # Chỉ dẫn hệ thống đi ở trường RIÊNG, không trộn vào lượt hội thoại.
            # Đây là ranh giới mà US-061 dựa vào: nội dung tài liệu nằm trong
            # `contents` với tư cách dữ liệu, chỉ dẫn nằm ngoài.
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "model" if m["role"] == "assistant" else "user",
                    "parts": [{"text": m["content"]}],
                }
                for m in messages
            ],
            "generationConfig": {"temperature": temperature},
        }
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        # `alt=sse` đổi phản hồi từ một mảng JSON dài sang từng sự kiện một.
        # Thiếu tham số này thì không có gì phát ra cho tới khi sinh xong, và
        # mốc "token đầu tiên dưới 3 giây" của US-012 AC-2 mất ý nghĩa.
        url = f"{API_ROOT}/models/{self.model}:streamGenerateContent?alt=sse"

        for attempt in range(RETRIES + 1):
            try:
                async with (
                    httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client,
                    client.stream(
                        "POST", url, json=payload,
                        headers={"x-goog-api-key": self.api_key},
                    ) as response,
                ):
                    if response.status_code in _TRANSIENT and attempt < RETRIES:
                        await response.aread()
                        delay = BACKOFF_S * 2**attempt
                        log.warning(
                            "Gemini trả về %d, thử lại sau %.1fs (lần %d/%d)",
                            response.status_code, delay, attempt + 1, RETRIES,
                        )
                        await asyncio.sleep(delay)
                        continue

                    if response.status_code != 200:
                        body = (await response.aread()).decode("utf-8", "replace")[:300]
                        raise RuntimeError(_explain(response.status_code, body))

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        for piece in _texts(line[6:]):
                            yield piece
                    return

            except httpx.ConnectError as exc:
                raise RuntimeError(
                    "Không kết nối được tới Gemini. Fast Mode cần mạng; "
                    "chuyển sang Privacy Mode để chạy hoàn toàn cục bộ."
                ) from exc


def _texts(data: str) -> list[str]:
    """Rút phần văn bản khỏi một sự kiện SSE.

    Một sự kiện có thể mang nhiều `part`, và có part không phải văn bản — ví dụ
    `thoughtSignature` của các mô hình biết suy luận. Bỏ qua chúng thay vì báo
    lỗi: chúng là chi tiết nội bộ của mô hình, không phải nội dung câu trả lời.
    """
    try:
        parts = json.loads(data)["candidates"][0]["content"]["parts"]
    except (json.JSONDecodeError, KeyError, IndexError):
        return []
    return [p["text"] for p in parts if isinstance(p.get("text"), str)]


def _explain(status: int, body: str) -> str:
    """Đổi mã lỗi HTTP thành câu nói được cho người dùng — US-030 AC-5."""
    if status in (401, 403):
        return (
            "Gemini từ chối khoá API. Kiểm tra GEMINI_API_KEY trong .env, "
            "hoặc chuyển sang Privacy Mode."
        )
    if status == 404:
        return (
            f"Gemini không có mô hình '{settings.gemini_model}'. Sửa GEMINI_MODEL "
            f"trong .env — ví dụ 'gemini-flash-latest'."
        )
    if status == 429:
        return "Đã vượt hạn mức gọi Gemini. Đợi ít phút hoặc chuyển sang Privacy Mode."
    if status in (500, 503):
        return (
            f"Gemini đang quá tải và vẫn chưa phục hồi sau {RETRIES} lần thử lại. "
            f"Thử lại sau ít phút, hoặc chuyển sang Privacy Mode."
        )
    return f"Gemini trả về {status}: {body}"
