"""Trả lời câu hỏi về TOÀN BỘ tài liệu — US-069.

Vì sao đường RAG không làm được việc này
-----------------------------------------
*"Tóm tắt 2 tài liệu của tôi"* là câu hỏi tự nhiên nhất mà một người đặt cho hệ
thống đọc tài liệu, và đường truy xuất trả lời nó bằng *"không tìm thấy thông
tin này trong tài liệu của bạn"*.

Đó không phải lỗi cài đặt. Truy xuất đi tìm những đoạn **giống câu hỏi**, mà câu
hỏi này không chứa một từ nội dung nào của tài liệu — nó nói *về* tài liệu chứ
không nói về chủ đề của tài liệu. Điểm liên quan vì thế thấp, cổng ngưỡng τ từ
chối, và cổng đã làm đúng việc của nó.

Sai ở chỗ định tuyến: đây là câu hỏi **toàn cục**, không phải câu hỏi tra cứu.

Cách làm
--------
Không tìm kiếm gì cả. Lấy các đoạn **đầu tiên** của từng tài liệu đang trong
phạm vi, theo đúng thứ tự trong tài liệu, tới một hạn mức token, rồi đưa cho mô
hình. Phần đầu của một văn bản hành chính là chỗ đặt phạm vi, đối tượng áp dụng
và mục đích — đúng những gì một bản tóm tắt cần.

Vì sao vẫn có trích dẫn
------------------------
Bản tóm tắt vẫn phải kiểm chứng được. Mỗi đoạn đưa vào ngữ cảnh vẫn được đánh
số như đường RAG, nên người đọc bấm được vào từng ý để xem nó lấy từ đâu. Một
bản tóm tắt không trích dẫn được thì cũng chỉ là một đoạn văn đáng ngờ như bất
kỳ mô hình nào khác sinh ra.

Vì sao KHÔNG bỏ qua cổng ngưỡng một cách âm thầm
-------------------------------------------------
Đường này không đi qua τ, và đó là chủ đích — nhưng nó chỉ chạy khi **có tài
liệu thật** trong phạm vi. Không có tài liệu nào thì trả lời "chưa có tài liệu
nào", chứ không để mô hình tự nghĩ ra một bản tóm tắt.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge import Source, SourceChunk
from app.services.retrieval import Candidate, ScoredChunk

__all__ = ["KHONG_CO_TAI_LIEU", "KHONG_CO_TAI_LIEU_EN", "gom_dau_tai_lieu"]

log = logging.getLogger(__name__)

KHONG_CO_TAI_LIEU = (
    "Chưa có tài liệu nào sẵn sàng trong sổ tay này. Hãy tải một tệp lên và đợi "
    "xử lý xong, rồi hỏi lại."
)
KHONG_CO_TAI_LIEU_EN = (
    "No document is ready in this notebook yet. Upload a file, wait for it to "
    "finish processing, and ask again."
)

# Ngân sách ngữ cảnh, tính thô bằng token. Giữ dưới hạn mức đầu vào của mô hình
# nhỏ nhất đang dùng, và chừa chỗ cho prompt lẫn câu trả lời.
_NGAN_SACH_TOKEN = 6000

# Số đoạn tối đa lấy từ MỘT tài liệu.
#
# Có hạn mức riêng cho từng tài liệu vì hạn mức chung là không đủ: một tài liệu
# 500 trang sẽ chiếm trọn ngân sách và những tài liệu còn lại không có mặt trong
# bản tóm tắt — mà người dùng vừa nói rõ là muốn tóm tắt **cả hai**.
_TOI_DA_MOI_TAI_LIEU = 12


def gom_dau_tai_lieu(
    session: Session,
    *,
    notebook_id: uuid.UUID,
    source_ids: list[uuid.UUID] | None = None,
) -> list[ScoredChunk]:
    """Các đoạn mở đầu của từng tài liệu trong phạm vi, theo thứ tự tài liệu.

    Trả về danh sách rỗng khi không có tài liệu nào sẵn sàng — chỗ gọi phải xử
    lý ca đó chứ không được đưa ngữ cảnh rỗng cho mô hình.
    """
    q = select(Source).where(
        Source.notebook_id == notebook_id,
        Source.status == "ready",
        Source.in_scope.is_(True),
    )
    if source_ids:
        q = q.where(Source.id.in_(source_ids))

    nguon = list(session.scalars(q.order_by(Source.created_at)).all())
    if not nguon:
        return []

    # Chia đều ngân sách cho từng tài liệu. Người dùng hỏi "tóm tắt 2 tài liệu"
    # thì cả hai phải có mặt, kể cả khi một cái dài gấp mười cái kia.
    moi_tai_lieu = max(1, _NGAN_SACH_TOKEN // len(nguon))

    ket: list[ScoredChunk] = []
    for src in nguon:
        chunks = session.scalars(
            select(SourceChunk)
            .where(SourceChunk.source_id == src.id)
            .order_by(SourceChunk.chunk_index)
            .limit(_TOI_DA_MOI_TAI_LIEU)
        ).all()

        da_dung = 0
        for c in chunks:
            if da_dung and da_dung + c.token_count > moi_tai_lieu:
                break
            da_dung += c.token_count
            ket.append(
                ScoredChunk(
                    candidate=Candidate(
                        chunk_id=c.id,
                        source_id=c.source_id,
                        content=c.content,
                        page_no=c.page_no,
                        heading_path=c.heading_path,
                        char_start=c.char_start,
                        char_end=c.char_end,
                        # Không có điểm liên quan nào để ghi: đường này không
                        # chấm điểm, nó lấy theo vị trí trong tài liệu. Ghi 1.0
                        # sẽ là một con số bịa đi thẳng vào `top_rerank_score`
                        # và làm hỏng thống kê ở US-041.
                        score=0.0,
                    ),
                    rrf_score=0.0,
                )
            )

    log.info(
        "Tóm tắt %d tài liệu bằng %d đoạn mở đầu", len(nguon), len(ket)
    )
    return ket
