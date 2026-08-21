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
    return result
