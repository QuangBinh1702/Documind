"""Lược đồ cho các endpoint xác thực — US-002, US-003, US-004."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.services.auth import MAT_KHAU_TOI_THIEU

__all__ = [
    "DangKyRequest",
    "DangNhapRequest",
    "DoiMatKhauRequest",
    "LamMoiRequest",
    "TokenResponse",
    "UserResponse",
]


class DangKyRequest(BaseModel):
    email: EmailStr
    # US-002 AC-3 muốn lỗi hiện ngay tại trường nhập trước khi gọi API. Ràng
    # buộc ở đây là lớp thứ hai: giao diện kiểm trước, máy chủ vẫn không tin.
    password: str = Field(min_length=MAT_KHAU_TOI_THIEU)


class DangNhapRequest(BaseModel):
    email: EmailStr
    password: str


class LamMoiRequest(BaseModel):
    refresh_token: str


class DoiMatKhauRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=MAT_KHAU_TOI_THIEU)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Số giây còn lại của access_token")


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    locale: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}
