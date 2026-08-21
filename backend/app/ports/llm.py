"""Cổng mô hình ngôn ngữ — US-030 AC-4.

Privacy Mode và Fast Mode là **hai adapter của cùng một cổng**, không phải hai
nhánh mã. Nhờ vậy thêm nhà cung cấp mới không phải sửa tầng service, và việc
chuyển chế độ ở US-030 chỉ là đổi adapter.

`is_local` không phải thông tin trang trí: US-032 AC-2 yêu cầu **không có
request nào đi ra Internet** khi người dùng chưa đồng ý, và US-029 AC-3 yêu cầu
toàn hệ thống chạy được khi rút mạng. Tầng service dựa vào cờ này để biết một
lần gọi có rời khỏi máy hay không.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

__all__ = ["LLMProvider", "Message"]

Message = dict[str, str]
"""``{"role": "user" | "assistant", "content": "..."}``"""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    """Ghi vào `chat_messages.model_used` (US-012 AC-6) và vào nhãn hiển thị
    cạnh mỗi câu trả lời (US-030 AC-3)."""

    is_local: bool
    """True khi mô hình chạy trên máy này và không có lưu lượng ra ngoài."""

    async def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Sinh câu trả lời theo từng mẩu.

        Streaming là yêu cầu, không phải tối ưu: US-012 AC-2 đòi token đầu
        tiên xuất hiện dưới 3 giây, và điều đó chỉ đạt được nếu giao diện nhận
        được mẩu đầu ngay khi mô hình sinh ra nó.
        """
        ...
