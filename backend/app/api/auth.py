"""Đăng ký, đăng nhập, làm mới phiên, đổi mật khẩu — US-002 → US-004."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import (
    DangKyRequest,
    DangNhapRequest,
    DoiMatKhauRequest,
    LamMoiRequest,
    TokenResponse,
    UserResponse,
)
from app.services import auth as svc
from app.services import login_guard
from app.services.rate_limit import RateLimited, kiem_tra
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _phan_hoi(tokens: svc.TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


def _loi(exc: svc.AuthError) -> HTTPException:
    ma = {
        "EMAIL_TAKEN": status.HTTP_409_CONFLICT,
        "PASSWORD_TOO_SHORT": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }.get(exc.code, status.HTTP_401_UNAUTHORIZED)
    return HTTPException(status_code=ma, detail=exc.message)


@router.post("/register", response_model=TokenResponse, status_code=201,
             summary="Tạo tài khoản rồi đăng nhập luôn")
def register(req: DangKyRequest, session: DbSession, request: Request) -> TokenResponse:
    # Không đòi đăng nhập mà lại tạo bản ghi và băm Argon2id — cần một trần
    # theo IP để không bị dùng làm máy tạo tài khoản rác.
    ip = request.client.host if request.client else "?"
    try:
        kiem_tra("register", ip, limit=settings.register_per_hour_per_ip, window_seconds=3600)
    except RateLimited as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    try:
        _, tokens = svc.dang_ky(session, req.email, req.password)
    except svc.AuthError as exc:
        raise _loi(exc) from exc
    return _phan_hoi(tokens)


@router.post("/login", response_model=TokenResponse, summary="Đăng nhập")
def login(req: DangNhapRequest, session: DbSession) -> TokenResponse:
    # US-003 AC-5. Kiểm khoá TRƯỚC khi băm mật khẩu: Argon2id cố ý tốn tài
    # nguyên, nên để kẻ dò gọi vào đó cũng là một kiểu tấn công từ chối dịch vụ.
    con = login_guard.con_bao_lau(req.email)
    if con > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Đăng nhập sai quá nhiều lần. Thử lại sau {con // 60 + 1} phút.",
        )

    try:
        _, tokens = svc.dang_nhap(session, req.email, req.password)
    except svc.AuthError as exc:
        login_guard.ghi_that_bai(req.email)
        raise _loi(exc) from exc

    login_guard.xoa_dem(req.email)
    return _phan_hoi(tokens)


@router.post("/refresh", response_model=TokenResponse,
             summary="Cấp lại access token")
def refresh(req: LamMoiRequest, session: DbSession) -> TokenResponse:
    try:
        tokens = svc.lam_moi(session, req.refresh_token)
    except svc.AuthError as exc:
        raise _loi(exc) from exc
    return _phan_hoi(tokens)


@router.get("/me", response_model=UserResponse, summary="Thông tin tài khoản")
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


class DoiNgonNgu(BaseModel):
    locale: Literal["vi", "en"]


@router.patch("/me", response_model=UserResponse, summary="Đổi ngôn ngữ giao diện")
def doi_ngon_ngu(
    req: DoiNgonNgu, user: CurrentUser, session: DbSession
) -> UserResponse:
    """US-036 AC-2 — lựa chọn ngôn ngữ theo tài khoản, không theo trình duyệt.

    `localStorage` cũng nhớ được, nhưng nó nhớ theo máy. Người dùng đăng nhập
    trên máy khác sẽ gặp lại giao diện tiếng Việt mà họ đã đổi đi rồi — nên chỗ
    đúng để lưu là `users.locale`.
    """
    user.locale = req.locale
    session.flush()
    return UserResponse.model_validate(user)


@router.post("/change-password", response_model=TokenResponse,
             summary="Đổi mật khẩu và vô hiệu mọi phiên cũ")
def change_password(
    req: DoiMatKhauRequest, user: CurrentUser, session: DbSession
) -> TokenResponse:
    try:
        tokens = svc.doi_mat_khau(session, user, req.old_password, req.new_password)
    except svc.AuthError as exc:
        raise _loi(exc) from exc
    return _phan_hoi(tokens)
