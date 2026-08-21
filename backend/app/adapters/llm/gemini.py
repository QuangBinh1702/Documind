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
import re
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

# Vượt hạn mức (429) khác hẳn quá tải (503) và phải xử lý khác.
#
# Quá tải là ngẫu nhiên: thử lại sau một hai giây thường được. Vượt hạn mức thì
# có kỳ hạn — bản miễn phí cho 20 request mỗi phút, nên nếu đã hết thì phải chờ
# đủ hết phút đó, không có cách nào lách. Đợi 1,5 giây rồi thử lại chỉ tốn thêm
# một lần gọi hỏng.
#
# Máy chủ nói thẳng phải chờ bao lâu — *"Please retry in 57.8s"*. Nghe theo con
# số đó thay vì tự đoán, và cho 429 nhiều lượt thử hơn vì mỗi lượt chờ lâu hơn.
RATE_LIMIT_RETRIES = 3
_RETRY_AFTER = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)

# Chặn trên cho thời gian nghe theo máy chủ. Hạn mức theo ngày có thể trả về
# hàng nghìn giây, và treo cả tiến trình chừng ấy thì tệ hơn là báo lỗi.
MAX_WAIT_S = 90.0

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
            "generationConfig": {
                "temperature": temperature,
                # Phần suy nghĩ ăn vào cùng hạn mức với câu trả lời — xem chú
                # thích ở `settings.gemini_thinking_budget`.
                "thinkingConfig": {"thinkingBudget": settings.gemini_thinking_budget},
            },
        }
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        # `alt=sse` đổi phản hồi từ một mảng JSON dài sang từng sự kiện một.
        # Thiếu tham số này thì không có gì phát ra cho tới khi sinh xong, và
        # mốc "token đầu tiên dưới 3 giây" của US-012 AC-2 mất ý nghĩa.
        url = f"{API_ROOT}/models/{self.model}:streamGenerateContent?alt=sse"

        attempt = 0
        while True:
            try:
                async with (
                    httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client,
                    client.stream(
                        "POST", url, json=payload,
                        headers={"x-goog-api-key": self.api_key},
                    ) as response,
                ):
                    con_lai = (
                        RATE_LIMIT_RETRIES if response.status_code == 429 else RETRIES
                    )
                    if response.status_code in _TRANSIENT and attempt < con_lai:
                        body = (await response.aread()).decode("utf-8", "replace")
                        delay = _cho_bao_lau(response.status_code, body, attempt)
                        log.warning(
                            "Gemini trả về %d, chờ %.1fs rồi thử lại (lần %d/%d)",
                            response.status_code, delay, attempt + 1, con_lai,
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue

                    if response.status_code != 200:
                        body = (await response.aread()).decode("utf-8", "replace")[:300]
                        raise RuntimeError(_explain(response.status_code, body))

                    emitted = False
                    finish = None
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        texts, reason = _parse(line[6:])
                        finish = reason or finish
                        for piece in texts:
                            emitted = True
                            yield piece

                    # Một câu trả lời rỗng mà không có lỗi là ca hỏng tệ nhất:
                    # cổng ngưỡng đã cho qua, giao diện hiện một bong bóng
                    # trống, và không có gì trong log nói vì sao. Bắt ngay ở đây.
                    if not emitted:
                        raise RuntimeError(_explain_empty(finish))
                    return

            except httpx.ConnectError as exc:
                raise RuntimeError(
                    "Không kết nối được tới Gemini. Fast Mode cần mạng; "
                    "chuyển sang Privacy Mode để chạy hoàn toàn cục bộ."
                ) from exc


def _cho_bao_lau(status: int, body: str, attempt: int) -> float:
    """Chờ bao lâu trước lượt thử tiếp theo.

    Ưu tiên con số máy chủ đưa ra: với 429 nó biết chính xác khi nào hạn mức
    được nạp lại, còn ta thì chỉ đoán được. Không có con số đó thì lùi theo cấp
    số nhân — mốc xuất phát của 429 lớn hơn hẳn, vì hạn mức tính theo phút.
    """
    if status == 429:
        if m := _RETRY_AFTER.search(body):
            # Cộng thêm một giây cho lệch đồng hồ giữa hai máy.
            return min(float(m.group(1)) + 1.0, MAX_WAIT_S)
        return min(20.0 * 2**attempt, MAX_WAIT_S)
    return BACKOFF_S * 2**attempt


def _parse(data: str) -> tuple[list[str], str | None]:
    """Rút văn bản và `finishReason` khỏi một sự kiện SSE.

    Một sự kiện có thể mang nhiều `part`, và có part không phải văn bản — ví dụ
    `thoughtSignature` của các mô hình biết suy luận. Bỏ qua chúng thay vì báo
    lỗi: chúng là chi tiết nội bộ của mô hình, không phải nội dung câu trả lời.
    """
    try:
        candidate = json.loads(data)["candidates"][0]
    except (json.JSONDecodeError, KeyError, IndexError):
        return [], None

    parts = candidate.get("content", {}).get("parts", [])
    texts = [p["text"] for p in parts if isinstance(p.get("text"), str)]
    return texts, candidate.get("finishReason")


def _explain_empty(finish: str | None) -> str:
    """Vì sao mô hình không trả về chữ nào — US-030 AC-5."""
    if finish == "MAX_TOKENS":
        return (
            "Gemini hết hạn mức token trước khi viết được câu trả lời. Nếu "
            "GEMINI_THINKING_BUDGET đang khác 0 thì phần suy nghĩ đã ăn hết "
            "LLM_MAX_TOKENS; đặt về 0 hoặc tăng LLM_MAX_TOKENS."
        )
    if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
        return (
            f"Gemini chặn câu trả lời vì bộ lọc nội dung ({finish}). "
            f"Privacy Mode chạy mô hình cục bộ nên không có bộ lọc này."
        )
    if finish == "RECITATION":
        return (
            "Gemini từ chối vì câu trả lời trùng quá nhiều với văn bản có bản "
            "quyền mà nó đã học. Thử hỏi lại theo cách khác."
        )
    return f"Gemini kết thúc mà không trả về chữ nào (finishReason={finish})."


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
