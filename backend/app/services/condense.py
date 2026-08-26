"""Gộp lịch sử hội thoại thành một câu hỏi độc lập — US-019.

Vì sao cần
----------
Truy xuất là **không trạng thái**: nó chỉ nhìn thấy chuỗi ký tự được đưa vào.
Câu hỏi *"thế còn phần sau thì sao?"* không chứa từ nào để tìm, nên dù hội
thoại trước đó có rõ ràng đến đâu thì nhánh vector lẫn nhánh từ khoá đều trả
về rác.

Bước này viết lại câu hỏi thành dạng đứng một mình được, **trước** khi truy
xuất.

Hai cái bẫy đã tính tới
-----------------------
**Bóp méo câu hỏi vốn đã đầy đủ** (US-019 AC-3). Một câu hỏi rõ ràng bị viết
lại có thể mất chi tiết quan trọng. Nên có bước kiểm tra rẻ tiền phía trước:
câu hỏi không chứa từ tham chiếu và đủ dài thì giữ nguyên, không gọi mô hình.

**Cưỡng ép gán vào chủ đề cũ** (US-019 AC-4). Người dùng đổi chủ đề hoàn toàn
thì việc nhét ngữ cảnh cũ vào làm hỏng truy xuất. Prompt nói rõ điều này.
"""

from __future__ import annotations

import logging
import re

from app.ports.llm import LLMProvider, Message
from app.settings import settings

__all__ = ["condense_question", "needs_condensing"]

log = logging.getLogger(__name__)

# Từ tham chiếu ngược: sự có mặt của chúng là dấu hiệu câu hỏi phụ thuộc ngữ
# cảnh trước đó. Danh sách thiên về bắt sót hơn bắt nhầm — gộp nhầm một câu
# vốn đã đầy đủ chỉ tốn một lượt gọi, còn bỏ sót thì truy xuất ra rác.
_REFERENTIAL = re.compile(
    r"\b(đó|này|kia|ấy|vậy|thế|trên|dưới|sau|trước|nó|họ|chúng|"
    r"cái\s+đó|phần\s+(đó|này|trên|sau)|điều\s+(đó|này)|"
    r"còn|thì\s+sao|ra\s+sao|như\s+thế\s+nào)\b",
    re.IGNORECASE,
)

_MIN_STANDALONE_WORDS = 6

CONDENSE_PROMPT = """Viết lại câu hỏi cuối cùng thành một câu hỏi ĐỘC LẬP, đọc \
hiểu được mà không cần xem lịch sử hội thoại.

QUY TẮC
1. Thay các từ tham chiếu (đó, này, nó, phần trên…) bằng đối tượng cụ thể mà \
chúng trỏ tới trong lịch sử.
2. Giữ NGUYÊN ý định và mức chi tiết của câu hỏi gốc. Không thêm, không bớt.
3. Nếu câu hỏi cuối đã đầy đủ nghĩa, chép lại gần như nguyên văn.
4. Nếu người dùng đổi hẳn sang chủ đề khác, KHÔNG gán nó vào chủ đề cũ.
5. Viết lại bằng ĐÚNG ngôn ngữ của câu hỏi cuối (hỏi tiếng Anh thì viết lại \
bằng tiếng Anh). Không dịch.
6. Chỉ trả về câu hỏi đã viết lại. Không giải thích, không thêm lời dẫn."""


def needs_condensing(question: str) -> bool:
    """Đoán nhanh xem câu hỏi có phụ thuộc ngữ cảnh không.

    Cố ý rẻ và thiên về gộp: bỏ sót một câu hỏi phụ thuộc làm truy xuất ra rác,
    còn gộp nhầm một câu đã đầy đủ chỉ tốn thêm một lượt gọi mô hình.
    """
    if _REFERENTIAL.search(question):
        return True
    return len(question.split()) < _MIN_STANDALONE_WORDS


async def condense_question(
    question: str,
    history: list[Message],
    *,
    llm: LLMProvider,
) -> tuple[str, bool]:
    """Trả về ``(câu hỏi dùng để truy xuất, đã gộp hay chưa)``.

    Không có lịch sử, hoặc câu hỏi đã đứng một mình được, thì trả về nguyên
    văn và **không gọi mô hình**.
    """
    if not history or not needs_condensing(question):
        return question, False

    turns = "\n".join(
        f"{'Người dùng' if m['role'] == 'user' else 'Trợ lý'}: {m['content']}"
        for m in history[-settings.condense_history_turns * 2 :]
    )
    user = f"LỊCH SỬ HỘI THOẠI:\n{turns}\n\nCÂU HỎI CUỐI: {question}"

    pieces = [
        p
        async for p in llm.stream(
            CONDENSE_PROMPT, [{"role": "user", "content": user}], temperature=0.0
        )
    ]
    rewritten = " ".join("".join(pieces).split()).strip().strip('"')

    if not rewritten:
        # Mô hình trả về rỗng thì dùng câu gốc — suy giảm êm, không sập.
        return question, False

    if settings.log_condensed_query:  # US-019 AC-5
        log.info("Condense: %r → %r", question, rewritten)

    return rewritten, True
