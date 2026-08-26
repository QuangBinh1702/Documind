"""Phần chung của mọi máy chủ nói giao thức OpenAI.

Ollama, vLLM, llama.cpp và Ollama Cloud đều phơi ra cùng một giao diện
`/chat/completions`. Khác nhau chỉ ở ba thứ: địa chỉ, có cần khoá không, và
**dữ liệu có rời khỏi máy hay không**.

Thứ ba mới là thứ quan trọng. `is_local` không phải một chi tiết cấu hình — nó
là thứ US-032 AC-2 dựa vào để biết một lượt gọi có gửi nội dung tài liệu ra
ngoài không, và nó điều khiển nhãn cảnh báo trên giao diện. Vì vậy nó là thuộc
tính của **lớp**, do người viết adapter khai báo, chứ không phải một tham số ai
cũng đặt được từ cấu hình.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from app.ports.llm import Message
from app.settings import settings

__all__ = ["OpenAICompatProvider"]

log = logging.getLogger(__name__)

# Trạng thái tạm thời — đáng thử lại trước khi báo lỗi cho người dùng.
_TRANSIENT = frozenset({429, 500, 502, 503, 504})
RETRIES = 2
BACKOFF_S = 1.5


class OpenAICompatProvider:
    """Gọi một máy chủ tương thích OpenAI, phát ra từng mẩu văn bản."""

    is_local: bool = True
    """Lớp con PHẢI khai báo lại nếu lượt gọi rời khỏi máy."""

    # Câu hướng dẫn khi không kết nối được — mỗi nhà cung cấp một cách khắc phục.
    loi_ket_noi = "Không kết nối được máy chủ mô hình tại {base_url}."

    def __init__(self, model: str, base_url: str, api_key: str | None = None) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    @property
    def name(self) -> str:  # pragma: no cover - lớp con đặt tên riêng
        return self.model

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        import httpx

        payload: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        timeout = httpx.Timeout(settings.llm_timeout_seconds, connect=10.0)

        attempt = 0
        try:
            while True:
                async with (
                    httpx.AsyncClient(timeout=timeout) as client,
                    client.stream("POST", url, json=payload, headers=self._headers()) as resp,
                ):
                    if resp.status_code in _TRANSIENT and attempt < RETRIES:
                        await resp.aread()
                        delay = BACKOFF_S * 2**attempt
                        log.warning(
                            "%s trả về %d, chờ %.1fs rồi thử lại (lần %d/%d)",
                            self.name, resp.status_code, delay, attempt + 1, RETRIES,
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue

                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "replace")[:300]
                        raise RuntimeError(self._giai_thich(resp.status_code, body))

                    emitted = False
                    finish: str | None = None
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            choice = json.loads(data)["choices"][0]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        finish = choice.get("finish_reason") or finish
                        if content := (choice.get("delta") or {}).get("content"):
                            emitted = True
                            yield content

                    # Câu trả lời rỗng mà không có lỗi là ca hỏng tệ nhất: cổng
                    # ngưỡng đã cho qua, giao diện hiện bong bóng trống và
                    # `answer_kind` bị ghi là `grounded`. Bắt ngay ở đây, cùng
                    # cách với adapter Gemini.
                    if not emitted:
                        raise RuntimeError(self._giai_thich_rong(finish))
                    return

        except httpx.ConnectError as exc:
            raise RuntimeError(self.loi_ket_noi.format(base_url=self.base_url)) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"{self.name} không trả lời trong {settings.llm_timeout_seconds:.0f}s. "
                f"Tăng LLM_TIMEOUT_SECONDS hoặc dùng mô hình nhỏ hơn."
            ) from exc

    def _giai_thich_rong(self, finish: str | None) -> str:
        if finish == "length":
            return (
                f"{self.name} hết hạn mức token trước khi sinh được chữ nào — "
                f"prompt quá dài so với cửa sổ ngữ cảnh. Giảm RERANK_TOP_K hoặc "
                f"LLM_CONTEXT_TOKENS, hoặc tăng num_ctx của máy chủ mô hình."
            )
        if finish == "content_filter":
            return f"{self.name} từ chối trả lời vì bộ lọc nội dung."
        return f"{self.name} trả về câu trả lời rỗng (finish_reason={finish})."

    def _giai_thich(self, status: int, body: str) -> str:
        """Đổi mã HTTP thành câu nói được — US-029 AC-5, US-030 AC-5."""
        if status in (401, 403):
            return (
                f"{self.name} từ chối khoá API. Kiểm tra lại khoá trong .env, "
                f"hoặc chuyển sang Privacy Mode."
            )
        if status == 404:
            return (
                f"Máy chủ không có mô hình '{self.model}'. Kiểm tra tên mô hình "
                f"trong .env."
            )
        if status == 429:
            return f"Đã vượt hạn mức gọi {self.name}. Đợi ít phút rồi thử lại."
        return f"{self.name} trả về {status}: {body}"
