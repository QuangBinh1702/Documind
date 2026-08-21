"""Mô hình ngôn ngữ giả — tất định, không gọi mạng.

Cùng lý do với hai adapter giả kia: test được **logic** của đường sinh câu trả
lời — tách marker, loại marker giả, ghi trích dẫn, đường từ chối — mà không
cần khoá API, không tốn quota và không phụ thuộc mạng.

Nó *không* sinh ngôn ngữ. Nó đọc ngữ cảnh đã đánh số trong prompt và ghép một
câu trả lời có trích dẫn từ chính các đoạn đó. Đủ để mọi bước hậu xử lý phía
sau có thật việc để làm.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

from app.ports.llm import Message
from app.services.prompt import NO_ANSWER_TEXT

__all__ = ["FakeLLMProvider"]

_BLOCK = re.compile(r"^\[(\d{1,2})\] \(", re.MULTILINE)


class FakeLLMProvider:
    name = "fake-echo"
    is_local = True

    def __init__(self, *, forced_reply: str | None = None, chunk_size: int = 24) -> None:
        self.forced_reply = forced_reply
        """Đặt để test một câu trả lời cụ thể — ví dụ câu chứa marker không hợp lệ."""
        self.chunk_size = chunk_size
        self.calls: list[tuple[str, list[Message]]] = []
        """Ghi lại mọi lần gọi. Test dùng để khẳng định prompt chứa đúng thứ
        cần có, và để chứng minh KHÔNG có lần gọi nào xảy ra (US-032 AC-2)."""

    async def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        self.calls.append((system, list(messages)))

        reply = self.forced_reply if self.forced_reply is not None else self._compose(messages)

        for i in range(0, len(reply), self.chunk_size):
            # Nhường quyền điều khiển để mã gọi thật sự chạy bất đồng bộ —
            # nếu không, test streaming sẽ pass kể cả khi đường xử lý bị chặn.
            await asyncio.sleep(0)
            yield reply[i : i + self.chunk_size]

    def _compose(self, messages: list[Message]) -> str:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        markers = [int(m.group(1)) for m in _BLOCK.finditer(user)]
        if not markers:
            return NO_ANSWER_TEXT

        cited = "".join(f"[{m}]" for m in markers[:2])
        return (
            f"Theo tài liệu, nội dung liên quan nằm ở các đoạn được trích dẫn {cited}. "
            f"Đây là câu trả lời do mô hình giả sinh ra để kiểm thử đường xử lý."
        )
