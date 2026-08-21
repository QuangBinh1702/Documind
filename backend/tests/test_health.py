"""Kiểm chứng US-001 AC-3 — endpoint health báo đúng trạng thái phụ thuộc.

Cần hạ tầng đang chạy:
    docker compose up -d postgres redis minio minio-init
    pytest tests/test_health.py -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health_tra_ve_200_khi_ha_tang_san_sang(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200, f"Hạ tầng chưa sẵn sàng: {r.json()}"

    body = r.json()
    assert body["status"] == "ok"
    # Ba thành phần bắt buộc của US-001 AC-3, cộng gpu để biết đang chạy máy nào.
    assert set(body["components"]) == {"postgres", "redis", "minio", "gpu"}


def test_postgres_co_du_extension_va_cau_hinh_vi(client: TestClient) -> None:
    """US-001 AC-8. Phép dò postgres cố ý chạm vào vector và to_tsvector('vi'),
    nên nó 'ok' nghĩa là cả hai đều dùng được, không chỉ là kết nối được."""
    body = client.get("/api/health").json()
    assert body["components"]["postgres"]["status"] == "ok"


def test_gpu_bo_qua_khi_chay_cpu(client: TestClient) -> None:
    """SPEC-v1.md §10.0: máy phát triển chạy DEVICE=cpu. Không có GPU ở đây là
    lựa chọn cấu hình, không phải lỗi — nên phải là 'skipped', không phải 'down'."""
    body = client.get("/api/health").json()
    gpu = body["components"]["gpu"]
    if body["device"] == "cpu":
        assert gpu["status"] == "skipped"
    else:
        assert gpu["status"] in {"ok", "down"}


def test_mot_thanh_phan_chet_lam_degraded_chu_khong_lam_sap(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health check phải còn dùng được đúng lúc có sự cố — đó là lúc cần nó nhất."""
    import app.services.health as health_mod

    def _no_redis() -> None:
        raise ConnectionError("giả lập redis chết")

    monkeypatch.setattr(health_mod, "_probe_redis", _no_redis)

    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["components"]["redis"]["status"] == "down"
    # Các thành phần khác vẫn được báo cáo bình thường.
    assert body["components"]["postgres"]["status"] == "ok"
