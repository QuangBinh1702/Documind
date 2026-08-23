"""Xác thực và phiên đăng nhập — US-002, US-003, US-004.

Ba quyết định đáng giải thích
-----------------------------

**Argon2id chứ không phải bcrypt.** US-002 AC-4 cho phép cả hai. Argon2id thắng
giải Password Hashing Competition và khó tấn công bằng GPU hơn vì nó tốn cả bộ
nhớ chứ không chỉ tốn thời gian — đúng thứ cần khi kẻ tấn công có card đồ hoạ mà
máy chủ thì không.

**Refresh token bị vô hiệu bằng chính mật khẩu, không bằng bảng thu hồi.**
US-004 AC-2 yêu cầu đổi mật khẩu thì **mọi** refresh token cũ chết theo. Cách
thường thấy là lưu danh sách token đã cấp rồi xoá — thêm một bảng, thêm một chỗ
để rò rỉ, và phải dọn rác định kỳ.

Ở đây token mang theo một dấu vân tay lấy từ `password_hash`. Đổi mật khẩu thì
hash đổi, vân tay không khớp nữa, và mọi token cũ hỏng cùng lúc mà không cần lưu
gì cả. Argon2 luôn sinh muối mới nên đổi sang **đúng mật khẩu cũ** cũng đổi hash
— tức là "đổi mật khẩu" luôn thu hồi phiên, đúng như người dùng mong đợi.

**Sai email và sai mật khẩu trả về cùng một câu.** US-003 AC-2. Phân biệt hai ca
đó biến trang đăng nhập thành công cụ dò xem email nào đã đăng ký. Vì lý do đó,
ca "không có tài khoản" vẫn chạy một lượt băm giả để thời gian phản hồi không tố
cáo sự khác biệt.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Literal

import jwt
from argon2 import PasswordHasher

# `VerificationError` là lớp cha: nó phủ cả sai mật khẩu (`VerifyMismatchError`)
# lẫn hash hỏng không giải mã được. Bắt riêng lớp con thì một hash hỏng trong DB
# sẽ nổi thành lỗi 500 thay vì một câu "sai mật khẩu".
from argon2.exceptions import VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge import User
from app.settings import settings

__all__ = [
    "AuthError",
    "TokenPair",
    "bam_mat_khau",
    "dang_ky",
    "dang_nhap",
    "doi_mat_khau",
    "giai_ma",
    "lam_moi",
    "nguoi_dung_tu_token",
]

log = logging.getLogger(__name__)

_hasher = PasswordHasher()

@lru_cache(maxsize=1)
def _hash_moi_nhu() -> str:
    """Một hash THẬT để đối chiếu khi email không tồn tại.

    Không tìm thấy tài khoản mà trả lời ngay thì thời gian phản hồi tố cáo email
    nào đã đăng ký — đúng thứ mà thông báo lỗi giống nhau ở AC-2 sinh ra để che.
    Phải chạy một lượt xác minh để hai ca tốn thời gian như nhau.

    Chuỗi hash phải là hash **thật**: bản dựng tay cho đúng khuôn dạng vẫn làm
    Argon2 ném `VerificationError` ở bước giải mã, tức là ném ra một ngoại lệ
    khác hẳn ngoại lệ của ca sai mật khẩu — và ca đó lại nhanh hơn hẳn, nên bản
    vá chống dò theo thời gian tự nó thành kênh rò rỉ.

    Tính một lần rồi nhớ; chi phí là một lượt băm lúc đăng nhập hụt đầu tiên.
    """
    return _hasher.hash("khong-phai-mat-khau-cua-ai")

MAT_KHAU_TOI_THIEU = 8

Loai = Literal["access", "refresh"]


class AuthError(Exception):
    """Lỗi xác thực có thông báo hiển thị được cho người dùng."""

    def __init__(self, message: str, code: str = "AUTH_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0


def bam_mat_khau(mat_khau: str) -> str:
    return _hasher.hash(mat_khau)


def _van_tay(password_hash: str) -> str:
    """Dấu vân tay ngắn của mật khẩu hiện tại.

    Đưa vào token để đổi mật khẩu là mọi token cũ hỏng theo (US-004 AC-2). Chỉ
    lấy 16 ký tự đầu của SHA-256: đủ để phát hiện thay đổi, và không mang theo
    thông tin nào về chính hash trong một token mà client đọc được.
    """
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def _tao_token(user: User, loai: Loai) -> tuple[str, int]:
    song = (
        timedelta(minutes=settings.access_token_minutes)
        if loai == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    het_han = datetime.now(UTC) + song
    payload = {
        "sub": str(user.id),
        "typ": loai,
        "pwd": _van_tay(user.password_hash),
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int(het_han.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256"), int(
        song.total_seconds()
    )


def _cap_doi(user: User) -> TokenPair:
    access, song = _tao_token(user, "access")
    refresh, _ = _tao_token(user, "refresh")
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=song)


def giai_ma(token: str, loai: Loai) -> dict:
    """Giải mã và kiểm tra token. Ném `AuthError` với câu nói được."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Phiên đăng nhập đã hết hạn.", "TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Token không hợp lệ.", "TOKEN_INVALID") from exc

    if payload.get("typ") != loai:
        # Dùng refresh token thay cho access token sẽ kéo dài phiên vượt hạn
        # mức 60 phút mà không ai để ý.
        raise AuthError("Token không đúng loại.", "TOKEN_INVALID")
    return payload


def nguoi_dung_tu_token(session: Session, token: str, loai: Loai = "access") -> User:
    payload = giai_ma(token, loai)

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthError("Token không hợp lệ.", "TOKEN_INVALID") from exc

    user = session.get(User, user_id)
    if user is None:
        raise AuthError("Tài khoản không còn tồn tại.", "TOKEN_INVALID")

    if payload.get("pwd") != _van_tay(user.password_hash):
        # US-004 AC-2: mật khẩu đã đổi kể từ lúc cấp token này.
        raise AuthError(
            "Mật khẩu đã thay đổi, hãy đăng nhập lại.", "PASSWORD_CHANGED"
        )
    return user


# ══════════════════════════════════════════════════════
# Đăng ký · đăng nhập · làm mới · đổi mật khẩu
# ══════════════════════════════════════════════════════


def _kiem_mat_khau(mat_khau: str) -> None:
    if len(mat_khau) < MAT_KHAU_TOI_THIEU:
        raise AuthError(
            f"Mật khẩu phải có ít nhất {MAT_KHAU_TOI_THIEU} ký tự.", "PASSWORD_TOO_SHORT"
        )


def dang_ky(session: Session, email: str, mat_khau: str) -> tuple[User, TokenPair]:
    """US-002. Tạo tài khoản rồi đăng nhập luôn (AC-1)."""
    _kiem_mat_khau(mat_khau)
    email = email.strip().lower()

    if session.scalar(select(User).where(User.email == email)) is not None:
        # AC-2: không tiết lộ gì thêm về tài khoản đã tồn tại.
        raise AuthError("Email này đã được đăng ký.", "EMAIL_TAKEN")

    user = User(email=email, password_hash=bam_mat_khau(mat_khau))
    session.add(user)
    session.flush()
    log.info("Tài khoản mới: %s", email)
    return user, _cap_doi(user)


def dang_nhap(session: Session, email: str, mat_khau: str) -> tuple[User, TokenPair]:
    """US-003. Sai email và sai mật khẩu cho ra cùng một câu trả lời (AC-2)."""
    email = email.strip().lower()
    user = session.scalar(select(User).where(User.email == email))

    if user is None:
        # Vẫn xác minh một lần để thời gian phản hồi không tố cáo email nào tồn tại.
        with contextlib.suppress(VerificationError):
            _hasher.verify(_hash_moi_nhu(), mat_khau)
        raise AuthError("Email hoặc mật khẩu không đúng.", "BAD_CREDENTIALS")

    try:
        _hasher.verify(user.password_hash, mat_khau)
    except VerificationError as exc:
        raise AuthError("Email hoặc mật khẩu không đúng.", "BAD_CREDENTIALS") from exc

    # Argon2 nâng tham số theo thời gian; băm lại khi tham số đã lạc hậu.
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = bam_mat_khau(mat_khau)
        session.flush()

    return user, _cap_doi(user)


def lam_moi(session: Session, refresh_token: str) -> TokenPair:
    """US-003 AC-3. Cấp cặp token mới từ một refresh token còn hạn."""
    user = nguoi_dung_tu_token(session, refresh_token, loai="refresh")
    return _cap_doi(user)


def doi_mat_khau(session: Session, user: User, cu: str, moi: str) -> TokenPair:
    """US-004 AC-2, AC-3. Đổi xong thì mọi token cũ chết theo."""
    _kiem_mat_khau(moi)
    try:
        _hasher.verify(user.password_hash, cu)
    except VerificationError as exc:
        raise AuthError("Mật khẩu cũ không đúng.", "BAD_CREDENTIALS") from exc

    user.password_hash = bam_mat_khau(moi)
    session.flush()
    log.info("Đổi mật khẩu: %s", user.email)

    # Cấp cặp mới để người vừa đổi không bị đá ra khỏi phiên đang dùng.
    return _cap_doi(user)
