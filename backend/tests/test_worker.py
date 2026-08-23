"""Hàng đợi xử lý tài liệu — US-021.

Không dựng một worker Celery thật ở đây. Cái đáng test là **hợp đồng giữa API
và hàng đợi**, và nó nằm gọn trong hai câu hỏi: việc có được đẩy đi không, và
nếu đẩy hỏng thì tài liệu có kẹt không.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import BackgroundTasks

from app.api.notebooks import xep_hang
from app.settings import settings


class HangDoiGia:
    """Thay cho `xu_ly_nguon_task`, ghi lại những gì được đẩy vào."""

    def __init__(self, hong: bool = False) -> None:
        self.da_nhan: list[str] = []
        self.hong = hong

    def delay(self, source_id: str) -> None:
        if self.hong:
            raise ConnectionError("redis không phản hồi")
        self.da_nhan.append(source_id)


@pytest.fixture
def bg() -> BackgroundTasks:
    return BackgroundTasks()


def _va_o_hang_doi(monkeypatch, gia: HangDoiGia) -> None:
    import app.workers.celery_app as mo_dun

    monkeypatch.setattr(mo_dun, "xu_ly_nguon_task", gia)


def test_che_do_celery_day_viec_vao_hang_doi(monkeypatch, bg) -> None:
    monkeypatch.setattr(settings, "worker_mode", "celery")
    gia = HangDoiGia()
    _va_o_hang_doi(monkeypatch, gia)

    sid = uuid.uuid4()
    xep_hang(bg, sid)

    assert gia.da_nhan == [str(sid)]
    assert not bg.tasks, "không được chạy trong tiến trình API khi đã có hàng đợi"


def test_che_do_inline_chay_ngay_trong_api(monkeypatch, bg) -> None:
    """Đường dành cho phát triển và cho bộ test."""
    monkeypatch.setattr(settings, "worker_mode", "inline")
    gia = HangDoiGia()
    _va_o_hang_doi(monkeypatch, gia)

    xep_hang(bg, uuid.uuid4())

    assert gia.da_nhan == []
    assert len(bg.tasks) == 1


def test_hang_doi_chet_thi_van_xu_ly_chu_khong_ket(monkeypatch, bg, caplog) -> None:
    """Redis chết là sự cố hạ tầng, không phải lý do để tài liệu biến mất.

    Đường dự phòng yếu hơn — mất việc nếu API khởi động lại — nên nó phải ghi
    cảnh báo chứ không im lặng nuốt lỗi.
    """
    monkeypatch.setattr(settings, "worker_mode", "celery")
    _va_o_hang_doi(monkeypatch, HangDoiGia(hong=True))

    with caplog.at_level("WARNING"):
        xep_hang(bg, uuid.uuid4())

    assert len(bg.tasks) == 1, "phải rơi về xử lý ngay thay vì bỏ mặc"
    assert any("hàng đợi" in r.message for r in caplog.records)


# ══════════════════════════════════════════════════════
# Cấu hình Celery
# ══════════════════════════════════════════════════════


def test_cau_hinh_giu_viec_cho_toi_khi_xong() -> None:
    """`acks_late` — worker chết giữa chừng thì việc được giao lại, không mất."""
    celery = pytest.importorskip("app.workers.celery_app", reason="cần celery")
    assert celery.celery_app.conf.task_acks_late is True
    assert celery.celery_app.conf.worker_prefetch_multiplier == 1


def test_co_tran_thoi_gian_cho_mot_tai_lieu() -> None:
    """Không có trần thì một việc treo giữ chỗ của mọi tài liệu xếp sau."""
    celery = pytest.importorskip("app.workers.celery_app", reason="cần celery")
    cung = celery.celery_app.conf.task_time_limit
    mem = celery.celery_app.conf.task_soft_time_limit
    assert cung == settings.task_time_limit_seconds
    assert mem < cung, "ngưỡng mềm phải tới trước ngưỡng cứng"
