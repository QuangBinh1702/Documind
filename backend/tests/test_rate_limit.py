"""Giới hạn tốc độ theo cửa sổ cố định — cho endpoint không đòi đăng nhập."""

from __future__ import annotations

import pytest

from app.services import rate_limit
from app.services.rate_limit import RateLimited, kiem_tra


class RedisGia:
    def __init__(self) -> None:
        self.dem: dict[str, int] = {}
        self.ttl_cua: dict[str, int] = {}

    def incr(self, key):
        self.dem[key] = self.dem.get(key, 0) + 1
        return self.dem[key]

    def expire(self, key, ttl):
        self.ttl_cua[key] = ttl

    def ttl(self, key):
        return self.ttl_cua.get(key, -1)


class RedisHong:
    def incr(self, *a):
        raise ConnectionError("redis chết")


@pytest.fixture
def gia(monkeypatch) -> RedisGia:
    r = RedisGia()
    monkeypatch.setattr(rate_limit, "get_redis", lambda: r)
    return r


def test_cho_qua_toi_han_roi_chan(gia):
    for _ in range(3):
        kiem_tra("t", "k", limit=3, window_seconds=60)
    with pytest.raises(RateLimited) as exc:
        kiem_tra("t", "k", limit=3, window_seconds=60)
    assert exc.value.retry_after == 60


def test_cua_so_chi_dat_o_lan_dau(gia):
    kiem_tra("t", "k", limit=5, window_seconds=60)
    gia.ttl_cua["documind:ratelimit:t:k"] = 7  # giả lập thời gian trôi
    kiem_tra("t", "k", limit=5, window_seconds=60)
    assert gia.ttl_cua["documind:ratelimit:t:k"] == 7, "không được reset cửa sổ"


def test_khoa_khac_nhau_dem_rieng(gia):
    kiem_tra("t", "a", limit=1, window_seconds=60)
    kiem_tra("t", "b", limit=1, window_seconds=60)  # không ném


def test_limit_khong_duong_la_tat(gia):
    for _ in range(50):
        kiem_tra("t", "k", limit=0, window_seconds=60)
    assert gia.dem == {}


def test_redis_chet_thi_cho_qua(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis", lambda: RedisHong())
    kiem_tra("t", "k", limit=1, window_seconds=60)
    kiem_tra("t", "k", limit=1, window_seconds=60)  # vẫn không ném


def test_khong_co_redis_thi_cho_qua(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis", lambda: None)
    kiem_tra("t", "k", limit=1, window_seconds=60)
    kiem_tra("t", "k", limit=1, window_seconds=60)
