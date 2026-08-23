"""Tiến độ xử lý theo thời gian thực — US-022.

Không cần Redis để chạy: mọi hàm ở đây phải **hỏng thì im lặng bỏ qua**, và đó
chính là tính chất đáng test nhất. Mất thanh tiến trình là phiền; mất tài liệu
vì mất thanh tiến trình là hỏng.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import progress


class RedisGia:
    """Đủ dùng cho `setex`, `mget`, `delete` — không cần tới Redis thật."""

    def __init__(self) -> None:
        self.kho: dict[str, bytes] = {}
        self.ttl: dict[str, int] = {}
        self.da_dong = False

    def setex(self, key, ttl, value):
        self.kho[key] = value.encode() if isinstance(value, str) else value
        self.ttl[key] = ttl

    def mget(self, keys):
        return [self.kho.get(k) for k in keys]

    def delete(self, key):
        self.kho.pop(key, None)

    def close(self):
        self.da_dong = True


class RedisHong:
    def setex(self, *a, **k):
        raise ConnectionError("redis chết")

    def mget(self, *a, **k):
        raise ConnectionError("redis chết")

    def delete(self, *a, **k):
        raise ConnectionError("redis chết")

    def close(self):
        pass


@pytest.fixture
def gia(monkeypatch) -> RedisGia:
    r = RedisGia()
    monkeypatch.setattr(progress, "_redis", lambda: r)
    return r


def test_ghi_roi_doc_lai_duoc(gia: RedisGia):
    sid = uuid.uuid4()
    progress.dat(sid, status="ocr", progress=45, message="Đang nhận dạng chữ 45/120 trang …")

    ket = progress.doc([sid])
    assert ket[str(sid)]["status"] == "ocr"
    assert ket[str(sid)]["progress"] == 45
    assert "45/120" in ket[str(sid)]["message"]


def test_giu_nguyen_dau_tieng_viet(gia: RedisGia):
    """`json.dumps` mặc định thoát non-ASCII; chuỗi đọc lại phải còn dấu."""
    sid = uuid.uuid4()
    progress.dat(sid, status="chunking", progress=75, message="Đang chia đoạn …")
    assert progress.doc([sid])[str(sid)]["message"] == "Đang chia đoạn …"


def test_phan_tram_bi_kep_trong_khoang(gia: RedisGia):
    """Số phần trăm đi thẳng vào thanh tiến trình của giao diện."""
    a, b = uuid.uuid4(), uuid.uuid4()
    progress.dat(a, status="ocr", progress=-10)
    progress.dat(b, status="ocr", progress=400)

    ket = progress.doc([a, b])
    assert ket[str(a)]["progress"] == 0
    assert ket[str(b)]["progress"] == 100


def test_nguon_chua_co_ban_ghi_thi_vang_mat(gia: RedisGia):
    """Vắng mặt chứ không phải một mục rỗng — giao diện phân biệt được hai ca."""
    co, khong = uuid.uuid4(), uuid.uuid4()
    progress.dat(co, status="parsing", progress=20)

    ket = progress.doc([co, khong])
    assert str(co) in ket
    assert str(khong) not in ket


def test_xoa_thi_khong_con(gia: RedisGia):
    sid = uuid.uuid4()
    progress.dat(sid, status="ocr", progress=10)
    progress.xoa(sid)
    assert progress.doc([sid]) == {}


def test_danh_sach_rong_khong_goi_redis(monkeypatch):
    """`MGET` không có khoá nào là một lỗi ở Redis thật, không phải danh sách rỗng."""
    def khong_duoc_goi():
        raise AssertionError("không nên mở kết nối cho danh sách rỗng")

    monkeypatch.setattr(progress, "_redis", khong_duoc_goi)
    assert progress.doc([]) == {}


def test_luon_dong_ket_noi(gia: RedisGia):
    """Rò kết nối tích lại rất nhanh: luồng SSE gọi `doc` mỗi giây."""
    progress.dat(uuid.uuid4(), status="ocr", progress=1)
    assert gia.da_dong


# ══════════════════════════════════════════════════════
# Hỏng thì bỏ qua
# ══════════════════════════════════════════════════════


def test_redis_chet_thi_ghi_khong_nem_loi(monkeypatch):
    monkeypatch.setattr(progress, "_redis", RedisHong)
    progress.dat(uuid.uuid4(), status="ocr", progress=50)  # không ném là đạt


def test_redis_chet_thi_doc_tra_ve_rong(monkeypatch):
    monkeypatch.setattr(progress, "_redis", RedisHong)
    assert progress.doc([uuid.uuid4()]) == {}


def test_khong_co_redis_thi_van_chay(monkeypatch):
    monkeypatch.setattr(progress, "_redis", lambda: None)
    progress.dat(uuid.uuid4(), status="ocr", progress=50)
    assert progress.doc([uuid.uuid4()]) == {}
    progress.xoa(uuid.uuid4())
