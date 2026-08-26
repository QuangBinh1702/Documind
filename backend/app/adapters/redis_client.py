"""Một client Redis dùng chung cho cả tiến trình.

`redis.from_url` tạo ra một connection pool, và pool đó an toàn giữa các luồng.
Trước đây `login_guard` và `progress` mở một client mới cho **mỗi lượt gọi** rồi
đóng lại — với luồng SSE hỏi tiến độ mỗi giây cho mỗi tab đang mở, đó là một
lượt bắt tay TCP mỗi giây mỗi tab, vô ích.

Trả về `None` khi không dựng được client — chỗ gọi tự quyết định "hỏng thì
mở" (login_guard) hay "hỏng thì im" (progress).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.settings import settings

__all__ = ["get_redis"]

log = logging.getLogger(__name__)


@lru_cache
def _client():
    import redis

    return redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )


def get_redis():
    try:
        return _client()
    except Exception as exc:
        log.warning("Không dựng được client Redis: %s", exc)
        return None
