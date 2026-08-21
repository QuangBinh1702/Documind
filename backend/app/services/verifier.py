"""Tác tử kiểm định câu trả lời — US-063.

Tách vai trò **sinh** khỏi vai trò **kiểm**. Mô hình sinh câu trả lời được
huấn luyện để hữu ích, nên nó nghiêng về việc nói thêm; một lượt kiểm riêng
biệt chỉ có một việc là hỏi *"câu này có nằm trong ngữ cảnh không?"*.

Nó tác động thẳng vào **Faithfulness** — chỉ số mà `SPEC.md` đặt mục tiêu cao
nhất và cũng là chỉ số mà hệ thống tham khảo trong `refs/` chỉ đạt 0.838.

Đánh đổi phải nêu trong báo cáo
-------------------------------
Thêm một lượt gọi mô hình cho mỗi câu trả lời, và thêm một lượt nữa khi phải
sinh lại. Độ trễ tăng gần gấp đôi ở trường hợp xấu. Đó là dòng **F** trong bảng
ablation: đo được lợi ích thì cũng phải đo được cái giá.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.ports.llm import LLMProvider
from app.services.prompt import ContextBlock
from app.settings import settings

__all__ = ["STRICTER_HINT", "VerificationResult", "verify_answer"]

log = logging.getLogger(__name__)

VERIFY_PROMPT = """Bạn kiểm tra xem một câu trả lời có bám sát các đoạn tài \
liệu đã cho hay không.

Với mỗi khẳng định trong câu trả lời, xét xem nó có được các đoạn chứng thực \
hay không. Một khẳng định "được chứng thực" khi nội dung của nó nằm rõ ràng \
trong đoạn, không phải khi nó chỉ nghe hợp lý.

Trả lời theo ĐÚNG khuôn dạng sau, không thêm gì khác:

KẾT LUẬN: ĐẠT
hoặc
KẾT LUẬN: KHÔNG ĐẠT
VẤN ĐỀ: <một câu nêu khẳng định nào không được chứng thực>"""

# Gợi ý thêm vào lượt sinh lại. Nói cụ thể vấn đề là gì, vì một lời nhắc chung
# chung kiểu "hãy chính xác hơn" gần như không đổi được hành vi.
STRICTER_HINT = """Câu trả lời trước có vấn đề: {issue}

Hãy trả lời lại, CHỈ dùng thông tin nằm rõ ràng trong các đoạn được cung cấp. \
Bỏ mọi khẳng định không có trong đó. Nếu các đoạn không đủ để trả lời, hãy nói \
đúng nguyên văn câu từ chối."""

_VERDICT = re.compile(r"KẾT LUẬN:\s*(ĐẠT|KHÔNG ĐẠT)", re.IGNORECASE)
_ISSUE = re.compile(r"VẤN ĐỀ:\s*(.+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    passed: bool
    issue: str | None = None
    raw: str = ""

    @property
    def needs_retry(self) -> bool:
        return not self.passed


async def verify_answer(
    answer: str,
    blocks: list[ContextBlock],
    *,
    llm: LLMProvider,
) -> VerificationResult:
    """Kiểm xem câu trả lời có được ngữ cảnh chứng thực không.

    Khi bộ kiểm hỏng hoặc trả về khuôn dạng lạ, mặc định là **ĐẠT**. Đó là
    lựa chọn có chủ ý: một bộ kiểm không đáng tin không được phép chặn câu trả
    lời vốn có thể đúng. Nó là lớp bảo vệ thêm, không phải cổng chặn.
    """
    if not answer.strip() or not blocks:
        return VerificationResult(passed=True)

    context = "\n\n".join(
        f"[{b.marker}] {b.chunk.candidate.content}" for b in blocks
    )
    user = f"CÁC ĐOẠN TÀI LIỆU:\n{context}\n\nCÂU TRẢ LỜI CẦN KIỂM:\n{answer}"

    try:
        pieces = [
            p
            async for p in llm.stream(
                VERIFY_PROMPT, [{"role": "user", "content": user}],
                temperature=0.0, max_tokens=200,
            )
        ]
        raw = "".join(pieces).strip()
    except Exception as exc:
        log.warning("Bộ kiểm định lỗi, coi như đạt: %s", exc)
        return VerificationResult(passed=True)

    verdict = _VERDICT.search(raw)
    if verdict is None:
        log.warning("Bộ kiểm định trả về khuôn dạng lạ, coi như đạt: %r", raw[:120])
        return VerificationResult(passed=True, raw=raw)

    passed = verdict.group(1).upper() == "ĐẠT"
    issue_match = _ISSUE.search(raw)
    issue = issue_match.group(1).strip() if issue_match else None

    if not passed:
        log.info("Kiểm định KHÔNG ĐẠT: %s", issue or "(không nêu lý do)")

    return VerificationResult(passed=passed, issue=issue, raw=raw)


def max_retries() -> int:
    return settings.verifier_max_retry
