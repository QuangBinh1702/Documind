"""Adapter mô hình cục bộ — Privacy Mode (US-029).

Gọi một máy chủ tương thích OpenAI chạy trên chính máy này: Ollama, vLLM hay
llama.cpp đều phơi ra cùng giao diện đó. Nhờ vậy việc chọn runtime — quyết
định thuộc spike S2 (`SPEC-v1.md` §10) — không ảnh hưởng tới mã nguồn, chỉ đổi
một dòng cấu hình.

`is_local = True` là điều làm nên US-029 AC-3: rút dây mạng, hệ thống vẫn hỏi
đáp đầy đủ.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from app.ports.llm import Message
from app.settings import settings

__all__ = ["LocalLLMProvider"]

log = logging.getLogger(__name__)


class LocalLLMProvider:
    is_local = True

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.local_llm_model
        self.base_url = (base_url or settings.local_llm_base_url).rstrip("/")

    @property
    def name(self) -> str:
        return f"local:{self.model}"

    async def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Thiếu httpx.") from exc

        payload = {
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
                httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client,
                client.stream("POST", url, json=payload) as response,
            ):
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")[:200]
                    raise RuntimeError(
                        f"Máy chủ mô hình cục bộ trả về {response.status_code}: {body}"
                    )

                async for line in response.aiter_lines():
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
            # US-029 AC-5: hướng dẫn rõ ràng thay vì lỗi kết nối khó hiểu.
            raise RuntimeError(
                f"Không kết nối được máy chủ mô hình cục bộ tại {self.base_url}.\n"
                f"Khởi động Ollama (`ollama serve`) hoặc vLLM, hoặc chuyển sang "
                f"Fast Mode nếu có mạng."
            ) from exc
