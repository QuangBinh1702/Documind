"""Số liệu vận hành — US-041.

Đây là nguồn số cho chương "Đánh giá" của báo cáo, nên nó đo **dữ liệu thật đã
xảy ra** chứ không phải đếm lại từ log. Mọi con số ở đây đều truy được về một
hàng trong cơ sở dữ liệu.

Phân biệt Privacy Mode với Fast Mode
------------------------------------
`chat_messages` không có cột "chế độ", nhưng nó có `model_used`, và mọi adapter
đều tự đặt tên theo quy ước: `local:*` chạy trên máy, còn lại thì không. Đó là
cùng một thông tin, lấy từ chỗ đã có sẵn thay vì thêm một cột nữa phải giữ đồng
bộ. `tests/test_stats.py` ghim quy ước này lại để nó không lặng lẽ hỏng khi có
adapter mới.

Phạm vi
-------
Mọi truy vấn lọc theo `user_id` — INV-4. Trang thống kê của một người không được
đếm dữ liệu của người khác, kể cả khi nó chỉ hiện số tổng: tổng số nguồn của cả
hệ thống cũng là thông tin rò rỉ.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession, ExternalAnswerCache, ExternalCallLog
from app.models.knowledge import Notebook, Source, SourceChunk

__all__ = ["ThongKe", "tinh_thong_ke"]

# Adapter chạy cục bộ đặt tên bắt đầu bằng tiền tố này. Xem chú thích đầu tệp.
TIEN_TO_CUC_BO = "local:"


@dataclass(frozen=True, slots=True)
class DoTre:
    """Độ trễ của một nhóm câu trả lời, tính bằng mili giây."""

    so_luot: int
    trung_binh: float
    p95: float


@dataclass
class ThongKe:
    # AC-1 — quy mô kho tri thức
    so_notebook: int = 0
    so_nguon: int = 0
    so_chunk: int = 0
    dung_luong_bytes: int = 0

    # AC-2 — chi phí gọi ra ngoài
    so_luot_goi_ngoai: int = 0
    so_luot_tu_cache: int = 0
    ty_le_cache_hit: float = 0.0
    so_ban_ghi_cache: int = 0

    # AC-3 — độ trễ, tách theo chế độ
    do_tre_privacy: DoTre = field(default_factory=lambda: DoTre(0, 0.0, 0.0))
    do_tre_fast: DoTre = field(default_factory=lambda: DoTre(0, 0.0, 0.0))

    # AC-4 — phân bố loại câu trả lời
    phan_bo_answer_kind: dict[str, int] = field(default_factory=dict)

    # Bối cảnh: hoạt động 30 ngày gần nhất, để biểu đồ có trục thời gian
    luot_hoi_theo_ngay: list[dict[str, int | str]] = field(default_factory=list)

    @property
    def tong_cau_tra_loi(self) -> int:
        return sum(self.phan_bo_answer_kind.values())


def _cua_toi(user_id: uuid.UUID):
    """Điều kiện lọc dùng lại — mọi truy vấn đều phải đi qua nó (INV-4)."""
    return Notebook.user_id == user_id


def tinh_thong_ke(session: Session, user_id: uuid.UUID) -> ThongKe:
    """Toàn bộ số liệu cho một người dùng."""
    tk = ThongKe()

    # ── AC-1 ────────────────────────────────────────────
    tk.so_notebook = session.scalar(
        select(func.count()).select_from(Notebook).where(_cua_toi(user_id))
    ) or 0

    quy_mo = session.execute(
        select(func.count(Source.id), func.coalesce(func.sum(Source.size_bytes), 0))
        .select_from(Source)
        .join(Notebook, Notebook.id == Source.notebook_id)
        .where(_cua_toi(user_id))
    ).one()
    tk.so_nguon, tk.dung_luong_bytes = int(quy_mo[0]), int(quy_mo[1])

    tk.so_chunk = session.scalar(
        select(func.count())
        .select_from(SourceChunk)
        .join(Notebook, Notebook.id == SourceChunk.notebook_id)
        .where(_cua_toi(user_id))
    ) or 0

    # ── AC-2 ────────────────────────────────────────────
    #
    # `external_call_log` ghi CẢ lượt phục vụ từ cache (`from_cache=true`) lẫn
    # lượt gọi thật. Tỉ lệ hit là số lượt cache trên tổng lượt hỏi ra ngoài —
    # không phải trên tổng số câu hỏi, vì câu hỏi trong tài liệu không bao giờ
    # chạm tới cache này (INV-3).
    goi = session.execute(
        select(
            func.count().filter(~ExternalCallLog.from_cache),
            func.count().filter(ExternalCallLog.from_cache),
        ).where(ExternalCallLog.user_id == user_id)
    ).one()
    tk.so_luot_goi_ngoai, tk.so_luot_tu_cache = int(goi[0]), int(goi[1])
    tong_ngoai = tk.so_luot_goi_ngoai + tk.so_luot_tu_cache
    tk.ty_le_cache_hit = tk.so_luot_tu_cache / tong_ngoai if tong_ngoai else 0.0

    tk.so_ban_ghi_cache = session.scalar(
        select(func.count())
        .select_from(ExternalAnswerCache)
        .where(
            ExternalAnswerCache.user_id == user_id,
            ExternalAnswerCache.expires_at > datetime.now(UTC),
        )
    ) or 0

    # ── AC-3 ────────────────────────────────────────────
    #
    # p95 lấy bằng `percentile_disc` của Postgres: nó trả về một giá trị CÓ
    # THẬT trong tập dữ liệu thay vì nội suy giữa hai mẫu. Với độ trễ, một con
    # số đã từng thật sự xảy ra dễ bảo vệ hơn trước hội đồng.
    cuc_bo = ChatMessage.model_used.startswith(TIEN_TO_CUC_BO)
    hang = session.execute(
        select(
            case((cuc_bo, "privacy"), else_="fast").label("che_do"),
            func.count(),
            func.avg(cast(ChatMessage.latency_ms, Float)),
            func.percentile_disc(0.95).within_group(ChatMessage.latency_ms.asc()),
        )
        .select_from(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .join(Notebook, Notebook.id == ChatSession.notebook_id)
        .where(
            _cua_toi(user_id),
            ChatMessage.role == "assistant",
            ChatMessage.latency_ms.isnot(None),
            # Câu từ chối không gọi mô hình nào, nên đưa vào sẽ kéo trung bình
            # xuống và nói sai về chi phí sinh câu trả lời.
            ChatMessage.model_used.isnot(None),
            ChatMessage.model_used != "",
        )
        .group_by("che_do")
    ).all()

    for che_do, n, tb, p95 in hang:
        gia_tri = DoTre(int(n), float(tb or 0.0), float(p95 or 0.0))
        if che_do == "privacy":
            tk.do_tre_privacy = gia_tri
        else:
            tk.do_tre_fast = gia_tri

    # ── AC-4 ────────────────────────────────────────────
    for kind, n in session.execute(
        select(ChatMessage.answer_kind, func.count())
        .select_from(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .join(Notebook, Notebook.id == ChatSession.notebook_id)
        .where(_cua_toi(user_id), ChatMessage.answer_kind.isnot(None))
        .group_by(ChatMessage.answer_kind)
    ).all():
        tk.phan_bo_answer_kind[str(kind)] = int(n)

    # ── Hoạt động 30 ngày ───────────────────────────────
    tu_ngay = datetime.now(UTC) - timedelta(days=30)
    theo_ngay = session.execute(
        select(
            func.date_trunc("day", ChatMessage.created_at).label("ngay"),
            func.count(),
        )
        .select_from(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .join(Notebook, Notebook.id == ChatSession.notebook_id)
        .where(
            _cua_toi(user_id),
            ChatMessage.role == "user",
            ChatMessage.created_at >= tu_ngay,
        )
        .group_by("ngay")
        .order_by("ngay")
    ).all()
    tk.luot_hoi_theo_ngay = [
        {"ngay": ngay.date().isoformat(), "so_luot": int(n)} for ngay, n in theo_ngay
    ]

    return tk
