"""Giới hạn tốc độ theo cửa sổ cố định, lưu ở Redis.

Dùng cho những endpoint **không đòi đăng nhập** mà lại tốn tài nguyên thật:
hỏi qua liên kết chia sẻ (mỗi lượt là một lần nhúng + xếp hạng lại + gọi mô
hình, tính vào hạn mức của chủ sở hữu) và đăng ký tài khoản.

Cùng triết lý với `login_guard`: Redis chết thì **cho qua và ghi cảnh báo**,
không biến một sự cố phụ trợ thành sập dịch vụ.
"""

from __future__ import annotations

import logging

from app.adapters.redis_client import get_redis

__all__ = ["RateLimited", "kiem_tra"]

log = logging.getLogger(__name__)

_KHOA = "documind:ratelimit:{scope}:{key}"


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Quá nhiều yêu cầu. Thử lại sau {retry_after} giây.")
        self.retry_after = retry_after


def kiem_tra(scope: str, key: str, *, limit: int, window_seconds: int) -> None:
    """Đếm thêm một lượt; vượt `limit` trong `window_seconds` thì ném `RateLimited`.

    `limit <= 0` nghĩa là tắt — bộ test dùng để không tự khoá mình khi tạo
    hàng chục tài khoản từ cùng một địa chỉ.
    """
    if limit <= 0:
        return
    r = get_redis()
    if r is None:
        return
    khoa = _KHOA.format(scope=scope, key=key)
    try:
        so_lan = r.incr(khoa)
        if so_lan == 1:
            r.expire(khoa, window_seconds)
        if so_lan > limit:
            con = int(r.ttl(khoa) or window_seconds)
            raise RateLimited(max(1, con))
    except RateLimited:
        raise
    except Exception as exc:
        log.warning("Redis lỗi khi giới hạn tốc độ (%s), tạm cho qua: %s", scope, exc)
