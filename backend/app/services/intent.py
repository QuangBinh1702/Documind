"""Phân loại ý định và định tuyến — US-066.

Không phải mọi câu người dùng gõ đều là câu hỏi cần tra tài liệu. "Chào bạn"
hiện vẫn đi qua toàn bộ truy xuất lai, xếp hạng lại và cổng ngưỡng, rồi kết
thúc bằng một lời từ chối — tốn GPU, tốn thời gian, và trả lời sai kiểu.

Hai tầng, cố ý theo thứ tự đó
------------------------------
1. **Luật từ khoá** — rẻ, tất định, và đúng với phần lớn ca rõ ràng.
2. **Mô hình** — chỉ chạy khi luật không kết luận được.

Đặt luật trước không chỉ để tiết kiệm: nó làm hành vi **đoán trước được**.
Một hệ thống mà lời chào lúc được định tuyến đúng lúc không, tuỳ mô hình, là
một hệ thống khó gỡ lỗi.

Thiên về RAG khi phân vân
--------------------------
Định tuyến nhầm một câu hỏi thật sang nhánh trò chuyện làm mất câu trả lời có
căn cứ — đúng thứ hệ thống sinh ra để làm. Định tuyến nhầm một lời chào sang
RAG chỉ tốn vài trăm mili giây. Chi phí hai chiều lệch hẳn nhau, nên ngưỡng
nghiêng về RAG.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from app.ports.llm import LLMProvider
from app.text.normalize import strip_accents

__all__ = [
    "CHITCHAT_SYSTEM_PROMPT",
    "CHITCHAT_SYSTEM_PROMPT_EN",
    "Intent",
    "chitchat_system_prompt",
    "classify",
]

log = logging.getLogger(__name__)

Intent = Literal["rag", "chitchat"]

# Lời chào và lời cảm ơn tiếng Việt gần như luôn kéo theo một từ xưng hô hoặc
# một tiểu từ tình thái — "chào bạn", "cảm ơn nhé", "ok anh". Bỏ qua chúng thì
# luật chỉ bắt được đúng dạng cụt lủn mà gần như không ai gõ.
_ADDRESS = (
    r"(?:\s+(?:moi\s+nguoi|cac\s+ban|ban|cau|may|anh|chi|em|a|oi|nhe|nha|nhi|"
    r"nghe|day|do|ay|documind|bot|assistant))*"
)

# So khớp ở dạng KHÔNG DẤU để bắt cả câu người dùng gõ thiếu dấu.
_GREETING = re.compile(
    rf"^\s*(?:chao|hi|hello|hey|xin\s+chao|alo|oi)\b{_ADDRESS}[\s!.,?]*$",
    re.IGNORECASE,
)
_THANKS = re.compile(
    r"^\s*(?:cam\s*on|thanks?|thank\s+you|tks|ok|oke|okay|duoc\s+roi|tot|hay\s+qua)"
    rf"\b{_ADDRESS}[\s!.,?]*$",
    re.IGNORECASE,
)
_ABOUT_BOT = re.compile(
    r"\b(ban\s+la\s+ai|ban\s+ten\s+gi|ban\s+lam\s+duoc\s+gi|gioi\s+thieu\s+ve\s+ban|"
    r"who\s+are\s+you)\b",
    re.IGNORECASE,
)

# Dấu hiệu chắc chắn là câu hỏi tra cứu, kể cả khi câu rất ngắn.
#
# So khớp trên văn bản CÒN DẤU, không phải bản bỏ dấu. Bỏ dấu làm sập nhiều từ
# khác hẳn nhau về cùng một chuỗi: "mức" và "mục" đều thành "muc", nên "mức
# thu" bị đọc nhầm thành có dấu hiệu tài liệu. Từ ngữ pháp lý hầu như luôn
# được gõ đủ dấu, nên yêu cầu đủ dấu ở đây là hợp lý.
_DOCUMENT_SIGNAL = re.compile(
    r"(?:\bđiều\b|\bkhoản\b|\bchương\b|\bmục\b|phụ\s*lục|quy\s*chế|quy\s*định|"
    r"thông\s*tư|nghị\s*định|quyết\s*định|\btcvn\b|\biso\b|tài\s*liệu|văn\s*bản|"
    r"\btheo\b)",
    re.IGNORECASE,
)

# Những cụm không có từ đồng âm sau khi bỏ dấu — bắt được cả khi người dùng gõ
# thiếu dấu mà không sinh ra kết luận sai như nhóm trên.
_DOCUMENT_SIGNAL_BARE = re.compile(
    r"(?:phu\s*luc|quy\s*che|quy\s*dinh|thong\s*tu|nghi\s*dinh|quyet\s*dinh|"
    r"\btcvn\b|\biso\b|tai\s*lieu|van\s*ban)",
    re.IGNORECASE,
)

CLASSIFY_PROMPT = """Phân loại yêu cầu của người dùng thành đúng MỘT nhãn:

RAG      — câu hỏi cần tra cứu nội dung tài liệu để trả lời
CHITCHAT — chào hỏi, cảm ơn, hỏi về chính trợ lý, hoặc trò chuyện thông thường

Nếu phân vân, chọn RAG.

Chỉ trả về đúng một từ: RAG hoặc CHITCHAT."""

CHITCHAT_SYSTEM_PROMPT = """Bạn là trợ lý của DocuMind, một hệ thống hỏi đáp \
trên tài liệu do người dùng tải lên.

Trả lời ngắn gọn, thân thiện, bằng tiếng Việt.

Nếu người dùng hỏi bạn làm được gì, hãy nói rằng bạn trả lời câu hỏi dựa trên \
tài liệu của họ và luôn kèm trích dẫn để họ tự kiểm chứng.

KHÔNG bịa nội dung tài liệu. Nếu họ hỏi điều gì cần tra cứu, hãy mời họ đặt \
câu hỏi cụ thể."""

CHITCHAT_SYSTEM_PROMPT_EN = """You are the assistant of DocuMind, a system that \
answers questions about documents the user has uploaded.

Answer briefly and warmly, in English.

If the user asks what you can do, say that you answer questions from their own \
documents and always cite the passages so they can check for themselves.

NEVER invent document content. If they ask something that needs looking up, \
invite them to ask a specific question."""


def chitchat_system_prompt(language: str = "vi") -> str:
    """Prompt trò chuyện theo ngôn ngữ người dùng đang dùng — US-037."""
    return CHITCHAT_SYSTEM_PROMPT_EN if language == "en" else CHITCHAT_SYSTEM_PROMPT


def _by_rules(question: str) -> Intent | None:
    """Kết luận nhanh, hoặc `None` khi không chắc."""
    accented = question.strip().lower()
    bare = strip_accents(question).strip().lower()

    if _DOCUMENT_SIGNAL.search(accented) or _DOCUMENT_SIGNAL_BARE.search(bare):
        return "rag"
    if _GREETING.match(bare) or _THANKS.match(bare) or _ABOUT_BOT.search(bare):
        return "chitchat"

    # Câu dài thường là câu hỏi thật; câu rất ngắn không có dấu hiệu tài liệu
    # nào thì để mô hình quyết.
    if len(bare.split()) >= 5:
        return "rag"
    return None


async def classify(
    question: str,
    *,
    llm: LLMProvider | None = None,
    use_llm_fallback: bool = True,
) -> tuple[Intent, str]:
    """Trả về ``(ý định, cách quyết định)``.

    Vế thứ hai đi vào log và vào thống kê tỉ lệ định tuyến ở báo cáo
    (US-066 AC-5).
    """
    decided = _by_rules(question)
    if decided is not None:
        return decided, "rule"

    if not use_llm_fallback or llm is None:
        return "rag", "default"

    try:
        pieces = [
            p
            async for p in llm.stream(
                CLASSIFY_PROMPT, [{"role": "user", "content": question}],
                temperature=0.0, max_tokens=8,
            )
        ]
        label = "".join(pieces).strip().upper()
    except Exception as exc:
        log.warning("Phân loại ý định lỗi, mặc định RAG: %s", exc)
        return "rag", "error"

    return ("chitchat", "llm") if "CHITCHAT" in label else ("rag", "llm")
