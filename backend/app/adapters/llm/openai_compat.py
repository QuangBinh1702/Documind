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

import json
import logging
from collections.abc import AsyncIterator

from app.ports.llm import Message

__all__ = ["OpenAICompatProvider"]

log = logging.getLogger(__name__)


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

        try:
            async with (
                httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client,
                client.stream("POST", url, json=payload, headers=self._headers()) as resp,
            ):
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")[:300]
                    raise RuntimeError(self._giai_thich(resp.status_code, body))

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if content := delta.get("content"):
                        yield content

        except httpx.ConnectError as exc:
            raise RuntimeError(self.loi_ket_noi.format(base_url=self.base_url)) from exc

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
