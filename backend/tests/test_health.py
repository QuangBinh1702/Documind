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


@pytest.mark.parametrize(
    ("field", "value", "phai_co"),
    [
        ("llm_provider", "fake", "LLM_PROVIDER=fake"),
        ("embedding_provider", "fake", "EMBEDDING_PROVIDER=fake"),
        ("rerank_provider", "fake", "RERANK_PROVIDER=fake"),
    ],
)
def test_adapter_gia_phai_duoc_bao_ra_ngoai(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, field, value, phai_co
) -> None:
    """Adapter giả trả về kết quả trông hoàn chỉnh — đó là điều nguy hiểm.

    Mô hình giả sinh một câu trả lời đúng khuôn dạng, có chip trích dẫn bấm
    được, nhìn không khác gì kết quả thật. Nếu cảnh báo chỉ nằm trong log của
    máy chủ thì người đang xem giao diện không có cách nào biết mình đang nhìn
    bản dựng để test. `/api/health` là chỗ giao diện đọc được, nên cảnh báo
    phải ra tới đó.
    """
    from app.settings import settings

    monkeypatch.setattr(settings, field, value)
    warnings = client.get("/api/health").json()["warnings"]
    assert any(phai_co in w for w in warnings), warnings


def test_khong_canh_bao_khi_dung_adapter_that(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cảnh báo phải im khi không có gì đáng cảnh báo.

    Một nhãn luôn hiện là một nhãn không ai đọc.
    """
    from app.settings import settings

    monkeypatch.setattr(settings, "llm_provider", "real")
    monkeypatch.setattr(settings, "embedding_provider", "bge-m3")
    monkeypatch.setattr(settings, "rerank_provider", "bge")
    warnings = client.get("/api/health").json()["warnings"]
    assert not any("PROVIDER=fake" in w for w in warnings), warnings


@pytest.mark.parametrize("field", ["embedding_provider", "rerank_provider"])
def test_tei_phai_bao_ra_ngoai_rang_du_lieu_roi_khoi_may(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    """Bật `tei` là bỏ đúng thứ Privacy Mode hứa hẹn — phải nhìn thấy được.

    Nhúng và xếp hạng lại chạy ở mọi lượt hỏi và mọi lượt nạp tài liệu, không
    phân biệt chế độ. Người đang xem giao diện với nhãn "chạy hoàn toàn trên
    máy bạn" không có cách nào tự biết điều đó đã không còn đúng, nên cảnh báo
    không được nằm im trong tệp cấu hình (SPEC-REVIEW.md §A.4).
    """
    from app.settings import settings

    monkeypatch.setattr(settings, field, "tei")
    monkeypatch.setattr(settings, "tei_api_key", "k")
    warnings = client.get("/api/health").json()["warnings"]
    assert any("Privacy Mode" in w and settings.tei_base_url in w for w in warnings), warnings


def test_tei_thieu_khoa_bao_som_thay_vi_de_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.settings import settings

    monkeypatch.setattr(settings, "embedding_provider", "tei")
    monkeypatch.setattr(settings, "tei_api_key", None)
    warnings = client.get("/api/health").json()["warnings"]
    assert any("TEI_API_KEY" in w for w in warnings), warnings


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
