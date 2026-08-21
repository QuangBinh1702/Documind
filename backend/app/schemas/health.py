"""Lược đồ phản hồi cho endpoint health."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ComponentStatus = Literal["ok", "down", "skipped"]


class ComponentHealth(BaseModel):
    status: ComponentStatus
    detail: str | None = None
    latency_ms: int | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app_env: str
    device: str = Field(description="cpu hoặc cuda — SPEC-v1.md §10.0")
    components: dict[str, ComponentHealth]
    warnings: list[str] = Field(
        default_factory=list,
        description="Cảnh báo cấu hình đáng ngờ, không chặn khởi động",
    )
