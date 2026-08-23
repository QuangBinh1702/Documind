"""Chặn dò mật khẩu — US-003 AC-5.

Năm lần sai trong năm phút thì khoá mười lăm phút. Đếm theo **email**, không
theo địa chỉ IP: nhiều người dùng chung một NAT sẽ khoá lẫn nhau, còn kẻ tấn
công thì đổi IP dễ hơn đổi mục tiêu.

Hỏng thì mở, và nói to
----------------------
Redis chết thì hàm này cho qua thay vì chặn. Đây là đánh đổi có chủ ý và cần
nói rõ: chặn hết mọi lượt đăng nhập vì một thành phần phụ trợ chết là biến một
sự cố nhỏ thành sập toàn hệ thống, trong khi hậu quả của việc cho qua chỉ là mất
lớp chống dò trong lúc Redis hỏng — mật khẩu vẫn được băm bằng Argon2id và vẫn
phải đoán đúng.

Đổi lại, mỗi lần cho qua đều ghi một dòng cảnh báo, để chuyện đó không diễn ra
âm thầm.
"""

from __future__ import annotations

import logging

from app.settings import settings

__all__ = ["con_bao_lau", "ghi_that_bai", "xoa_dem"]

log = logging.getLogger(__name__)

_KHOA = "documind:login:{email}"


def _redis():
    try:
        import redis

        return redis.from_url(settings.redis_url, socket_connect_timeout=2)
    except Exception as exc:
        log.warning("Không dùng được Redis, tạm bỏ chặn dò mật khẩu: %s", exc)
        return None


def con_bao_lau(email: str) -> int:
    """Số giây còn bị khoá. 0 nghĩa là được phép thử."""
    r = _redis()
    if r is None:
        return 0
    try:
        key = _KHOA.format(email=email.strip().lower())
        so_lan = int(r.get(key) or 0)
        if so_lan < settings.login_max_attempts:
            return 0
        return max(0, int(r.ttl(key) or 0))
    except Exception as exc:
        log.warning("Redis lỗi khi kiểm khoá đăng nhập: %s", exc)
        return 0
    finally:
        r.close()


def ghi_that_bai(email: str) -> None:
    """Đếm thêm một lần sai, và khoá dài ra khi chạm ngưỡng."""
    r = _redis()
    if r is None:
        return
    try:
        key = _KHOA.format(email=email.strip().lower())
        so_lan = r.incr(key)
        if so_lan == 1:
            # Lần sai đầu mở cửa sổ đếm.
            r.expire(key, settings.login_window_minutes * 60)
        elif so_lan >= settings.login_max_attempts:
            # Chạm ngưỡng thì chuyển từ cửa sổ đếm sang thời gian khoá.
            r.expire(key, settings.login_lockout_minutes * 60)
            log.warning("Khoá đăng nhập %s trong %d phút", email,
                        settings.login_lockout_minutes)
    except Exception as exc:
        log.warning("Redis lỗi khi đếm lần đăng nhập sai: %s", exc)
    finally:
        r.close()


def xoa_dem(email: str) -> None:
    """Đăng nhập đúng thì xoá bộ đếm."""
    r = _redis()
    if r is None:
        return
    try:
        r.delete(_KHOA.format(email=email.strip().lower()))
    except Exception as exc:
        log.warning("Redis lỗi khi xoá bộ đếm đăng nhập: %s", exc)
    finally:
        r.close()
