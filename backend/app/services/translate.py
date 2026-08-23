"""Dịch câu hỏi sang ngôn ngữ tài liệu để truy xuất — US-037.

Vì sao cần bước này
--------------------
US-037 làm câu **trả lời** đi theo ngôn ngữ câu hỏi. Nhưng nó không giúp được gì
nếu bước **truy xuất** không tìm ra đoạn nào — và đo thật cho thấy nó không tìm
ra thật:

============================================  ==============  ===========
Câu hỏi                                       Điểm cao nhất   Kết quả
============================================  ==============  ===========
"điều kiện tốt nghiệp là gì"                  qua cổng        có căn cứ
"What are the graduation requirements?"       0.1428          **từ chối**
"graduation requirements"                     0.3228          **từ chối**
============================================  ==============  ===========

Cùng một tài liệu, cùng một câu trả lời nằm sẵn trong đó. Nút thắt là
`bge-reranker-v2-m3`: nó đa ngữ, nhưng nó chấm cặp **khác ngôn ngữ** thấp hơn
hẳn cặp cùng ngôn ngữ, và cổng ngưỡng τ chặn lại.

Nếu không có bước này thì tính năng song ngữ chỉ đúng một nửa: giao diện dịch
được, còn hỏi bằng tiếng Anh thì luôn nhận "không tìm thấy thông tin này".

Vì sao dịch chứ không hạ ngưỡng
--------------------------------
Hạ τ cho câu hỏi tiếng Anh sẽ "sửa" được ca này, và làm hỏng đúng thứ τ sinh ra
để bảo vệ: cổng ngưỡng chống bịa. Điểm 0.14 nghĩa là *"những đoạn này không liên
quan"* — hạ ngưỡng chỉ khiến hệ thống trả lời dựa trên đoạn không liên quan.

Dịch câu hỏi thì đưa cả hai vế về cùng một ngôn ngữ, và điểm số lấy lại đúng ý
nghĩa của nó.

Chỉ dịch **câu dùng để truy xuất**
-----------------------------------
Câu hỏi gốc vẫn là thứ được lưu vào lịch sử, hiển thị lại, và đưa cho mô hình
sinh câu trả lời. Cùng nguyên tắc với bước gộp ngữ cảnh ở US-019: bản viết lại
phục vụ việc tìm kiếm, không thay thế thứ người dùng đã gõ.
"""

from __future__ import annotations

import logging

from app.ports.llm import LLMProvider

__all__ = ["dich_de_truy_xuat"]

log = logging.getLogger(__name__)

_PROMPT = """Bạn dịch câu hỏi tìm kiếm sang tiếng Việt.

QUY TẮC
1. Chỉ trả về bản dịch, không thêm lời giải thích nào.
2. Giữ NGUYÊN VĂN mọi con số, ngày tháng, mã văn bản và tên riêng.
3. Dùng đúng thuật ngữ hành chính - giáo dục tiếng Việt: "graduation
   requirements" là "điều kiện tốt nghiệp", "credit" là "tín chỉ",
   "regulation" là "quy chế", "article" là "điều".
4. Giữ dạng câu hỏi."""

# Câu hỏi dài hơn mức này gần như chắc chắn không phải câu hỏi — có thể là một
# đoạn dán vào. Dịch nó vừa đắt vừa không giúp gì cho việc tìm kiếm.
_TOI_DA_KY_TU = 500


async def dich_de_truy_xuat(
    question: str, *, llm: LLMProvider, ngon_ngu: str
) -> tuple[str, bool]:
    """Trả về ``(câu để truy xuất, có dịch hay không)``.

    Hỏng thì trả lại câu gốc. Một lượt dịch thất bại làm chất lượng truy xuất
    kém đi; ném lỗi ra ngoài thì làm cả câu hỏi thất bại — đánh đổi rõ ràng.
    """
    if ngon_ngu == "vi" or not question.strip():
        return question, False

    if len(question) > _TOI_DA_KY_TU:
        return question, False

    try:
        mau: list[str] = []
        async for phan in llm.stream(
            _PROMPT,
            [{"role": "user", "content": question}],
            temperature=0.0,
            max_tokens=200,
        ):
            mau.append(phan)
        ban_dich = "".join(mau).strip()
    except Exception as exc:
        log.warning("Không dịch được câu hỏi để truy xuất: %s", exc)
        return question, False

    if not ban_dich:
        return question, False

    # Mô hình đôi khi trả về nhiều dòng kèm giải thích dù đã dặn. Lấy dòng đầu
    # có nội dung — bản dịch luôn nằm ở đó.
    dong = [d.strip() for d in ban_dich.splitlines() if d.strip()]
    ban_dich = dong[0] if dong else ban_dich
    ban_dich = ban_dich.strip('"').strip()

    if not ban_dich:
        return question, False

    log.info("Dịch câu hỏi để truy xuất: %r → %r", question, ban_dich)
    return ban_dich, True
