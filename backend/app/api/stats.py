"""Trang thống kê — US-041.

Số liệu chỉ trong phạm vi tài khoản đang đăng nhập (INV-4). Tổng số nguồn của cả
hệ thống nghe như một con số vô hại, nhưng nó vẫn là thông tin về dữ liệu của
người khác.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.services.stats import tinh_thong_ke

router = APIRouter(tags=["stats"])


class DoTreRa(BaseModel):
    so_luot: int
    trung_binh_ms: float
    p95_ms: float


class ThongKeRa(BaseModel):
    so_notebook: int
    so_nguon: int
    so_chunk: int
    dung_luong_bytes: int

    so_luot_goi_ngoai: int = Field(description="Lượt thật sự gọi ra dịch vụ ngoài")
    so_luot_tu_cache: int = Field(description="Lượt phục vụ từ cache, không tốn hạn mức")
    ty_le_cache_hit: float
    so_ban_ghi_cache: int

    do_tre_privacy: DoTreRa
    do_tre_fast: DoTreRa

    phan_bo_answer_kind: dict[str, int]
    luot_hoi_theo_ngay: list[dict]


@router.get("/stats", response_model=ThongKeRa, summary="Số liệu vận hành")
def thong_ke(user: CurrentUser, session: DbSession) -> ThongKeRa:
    tk = tinh_thong_ke(session, user.id)
    return ThongKeRa(
        so_notebook=tk.so_notebook,
        so_nguon=tk.so_nguon,
        so_chunk=tk.so_chunk,
        dung_luong_bytes=tk.dung_luong_bytes,
        so_luot_goi_ngoai=tk.so_luot_goi_ngoai,
        so_luot_tu_cache=tk.so_luot_tu_cache,
        ty_le_cache_hit=tk.ty_le_cache_hit,
        so_ban_ghi_cache=tk.so_ban_ghi_cache,
        do_tre_privacy=DoTreRa(
            so_luot=tk.do_tre_privacy.so_luot,
            trung_binh_ms=tk.do_tre_privacy.trung_binh,
            p95_ms=tk.do_tre_privacy.p95,
        ),
        do_tre_fast=DoTreRa(
            so_luot=tk.do_tre_fast.so_luot,
            trung_binh_ms=tk.do_tre_fast.trung_binh,
            p95_ms=tk.do_tre_fast.p95,
        ),
        phan_bo_answer_kind=tk.phan_bo_answer_kind,
        luot_hoi_theo_ngay=tk.luot_hoi_theo_ngay,
    )
