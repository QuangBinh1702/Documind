"""Endpoint kiểm tra sức khoẻ hệ thống — SPEC.md US-001 AC-3.

Không cần xác thực. Trả về trạng thái kết nối của từng thành phần phụ thuộc
để `docker compose` healthcheck và người vận hành đều dùng được.

Router chỉ điều phối và định dạng phản hồi; việc dò từng thành phần nằm ở
tầng service (DoD D4).
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.schemas.health import HealthResponse
from app.services.health import collect_health
from app.settings import settings

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Trạng thái kết nối của hệ thống",
)
async def health(response: Response) -> HealthResponse:
    result = await collect_health()
    if result.status != "ok":
        # 503 để healthcheck của docker và load balancer hiểu đúng,
        # nhưng vẫn trả về body đầy đủ để chẩn đoán.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    if settings.is_production:
        # Endpoint này công khai. Ở production chỉ trả trạng thái từng thành
        # phần — không trả nội dung ngoại lệ (có thể mang DSN, tên host) hay
        # danh sách cảnh báo cấu hình (nói ra đang dùng nhà cung cấp nào).
        result.warnings = []
        for c in result.components.values():
            c.detail = None
    return result
