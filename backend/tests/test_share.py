"""Chia sẻ notebook chỉ đọc — US-039.

Phần lớn test ở đây kiểm **những gì người xem KHÔNG làm được**. Một tính năng
chia sẻ hỏng theo chiều "cho quá nhiều quyền" thì không có triệu chứng nào:
người xem vẫn thấy đúng thứ họ cần, chỉ là họ còn làm được nhiều hơn thế.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.models.base import session_scope
from app.models.knowledge import User
from app.settings import settings

pytestmark = pytest.mark.db

CHU = "share-chu@example.com"
NGUOI_LA = "share-la@example.com"
MAT_KHAU = "mat-khau-du-dai-2026"

TAI_LIEU = """Điều 1. Thời gian đào tạo
Thời gian đào tạo trình độ đại học từ ba đến năm năm đối với văn bằng thứ nhất.

Điều 2. Nghỉ học tạm thời
Người học được nghỉ học tạm thời tối đa hai năm cộng dồn trong toàn khoá học.
"""


@pytest.fixture(autouse=True)
def _providers(monkeypatch):
    from app.adapters import embedding, llm, rerank

    monkeypatch.setattr(settings, "embedding_provider", "fake")
    monkeypatch.setattr(settings, "rerank_provider", "fake")
    monkeypatch.setattr(settings, "llm_provider", "fake")
    embedding.get_embedding_provider.cache_clear()
    rerank.get_rerank_provider.cache_clear()
    llm._cache.clear()
    yield
    embedding.get_embedding_provider.cache_clear()
    rerank.get_rerank_provider.cache_clear()
    llm._cache.clear()


@pytest.fixture(autouse=True)
def _bo_chan_dang_nhap(monkeypatch):
    from app.services import login_guard

    monkeypatch.setattr(login_guard, "con_bao_lau", lambda email: 0)
    monkeypatch.setattr(login_guard, "ghi_that_bai", lambda email: None)
    monkeypatch.setattr(login_guard, "xoa_dem", lambda email: None)


@pytest.fixture(autouse=True)
def sach():
    def wipe():
        with session_scope() as s:
            s.execute(delete(User).where(User.email.in_([CHU, NGUOI_LA])))

    wipe()
    yield
    wipe()


@pytest.fixture
def khach() -> TestClient:
    """Client không đăng nhập — chính là người nhận liên kết."""
    return TestClient(app)


@pytest.fixture
def chu(khach: TestClient) -> tuple[TestClient, dict, str]:
    """Chủ sở hữu, kèm một notebook đã có tài liệu sẵn sàng."""
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"email": CHU, "password": MAT_KHAU})
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    nb = c.post("/api/notebooks", json={"title": "Quy chế"}, headers=headers).json()["id"]
    up = c.post(
        f"/api/notebooks/{nb}/sources",
        headers=headers,
        files={"file": ("quy-che.txt", io.BytesIO(TAI_LIEU.encode()), "text/plain")},
    )
    assert up.status_code == 202
    return c, headers, nb


def _chia_se(c: TestClient, headers: dict, nb: str) -> str:
    r = c.post(f"/api/notebooks/{nb}/share", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _events(response) -> list[dict]:
    return [
        json.loads(b[6:]) for b in response.text.split("\n\n") if b.startswith("data: ")
    ]


# ══════════════════════════════════════════════════════
# Tạo và thu hồi
# ══════════════════════════════════════════════════════


def test_token_du_dai_va_khong_doan_duoc(chu) -> None:
    """AC-1 — token thay cho mật khẩu, nên độ dài là một yêu cầu chứ không phải
    một chi tiết."""
    c, headers, nb = chu
    a = _chia_se(c, headers, nb)
    assert len(a) >= 32

    # Notebook thứ hai phải có token khác hẳn.
    nb2 = c.post("/api/notebooks", json={"title": "Khác"}, headers=headers).json()["id"]
    assert _chia_se(c, headers, nb2) != a


def test_bam_chia_se_lan_hai_tra_ve_dung_lien_ket_cu(chu) -> None:
    """Sinh token mới mỗi lần bấm sẽ âm thầm cắt quyền của cả nhóm đã nhận link."""
    c, headers, nb = chu
    assert _chia_se(c, headers, nb) == _chia_se(c, headers, nb)


def test_thu_hoi_thi_lien_ket_cu_thanh_404(chu, khach) -> None:
    """AC-3."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb)
    assert khach.get(f"/api/shared/{token}").status_code == 200

    assert c.delete(f"/api/notebooks/{nb}/share", headers=headers).status_code == 204
    assert khach.get(f"/api/shared/{token}").status_code == 404


def test_chia_se_lai_sau_khi_thu_hoi_cap_token_moi(chu, khach) -> None:
    """Thu hồi rồi chia sẻ lại là một ý định rõ ràng — token cũ phải chết hẳn."""
    c, headers, nb = chu
    cu = _chia_se(c, headers, nb)
    c.delete(f"/api/notebooks/{nb}/share", headers=headers)
    moi = _chia_se(c, headers, nb)

    assert moi != cu
    assert khach.get(f"/api/shared/{cu}").status_code == 404
    assert khach.get(f"/api/shared/{moi}").status_code == 200


def test_khong_chia_se_duoc_notebook_cua_nguoi_khac(chu, khach) -> None:
    _, _, nb = chu
    r = khach.post("/api/auth/register", json={"email": NGUOI_LA, "password": MAT_KHAU})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert khach.post(f"/api/notebooks/{nb}/share", headers=h).status_code == 404


def test_token_bia_ra_tra_404(khach) -> None:
    assert khach.get("/api/shared/khong-co-that-dau-nhe-dai-hon-hai-muoi").status_code == 404
    assert khach.get("/api/shared/ngan").status_code == 404


# ══════════════════════════════════════════════════════
# Người xem làm được gì
# ══════════════════════════════════════════════════════


def test_nguoi_xem_thay_danh_sach_nguon(chu, khach) -> None:
    """AC-2 — xem được, và chỉ thấy tài liệu đã xử lý xong."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb)

    d = khach.get(f"/api/shared/{token}").json()
    assert d["title"] == "Quy chế"
    assert len(d["nguon"]) == 1
    assert d["nguon"][0]["status"] == "ready"


def test_nguoi_xem_khong_thay_chi_tiet_ky_thuat(chu, khach) -> None:
    """Khoá lưu trữ và thông báo lỗi là chuyện nội bộ của chủ sở hữu."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb)

    nguon = khach.get(f"/api/shared/{token}").json()["nguon"][0]
    for cam in ("storage_key", "error_message", "original_name", "text_quality"):
        assert cam not in nguon, f"lộ trường {cam} cho người xem"


def test_nguoi_xem_hoi_duoc_va_co_trich_dan(chu, khach) -> None:
    """AC-2 — hỏi được là điểm khác biệt so với "gửi một tệp PDF"."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb)

    r = khach.post(
        f"/api/shared/{token}/ask",
        json={"question": "nghỉ học tạm thời tối đa bao lâu"},
    )
    assert r.status_code == 200
    events = _events(r)
    assert any(e["type"] == "token" for e in events)

    cite = next(e for e in events if e["type"] == "citation")
    chi_tiet = khach.get(f"/api/shared/{token}/citations/{cite['chunk_id']}")
    assert chi_tiet.status_code == 200
    assert chi_tiet.json()["content"]


def test_cau_hoi_cua_nguoi_xem_khong_vao_lich_su_chu_so_huu(chu, khach) -> None:
    """Chia sẻ tài liệu không đồng nghĩa với cho người lạ ghi vào lịch sử của mình."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb)

    khach.post(f"/api/shared/{token}/ask", json={"question": "thời gian đào tạo"})

    phien = c.get(f"/api/sessions?notebook_id={nb}", headers=headers).json()
    assert phien == [], "hội thoại của người xem không được lưu"


# ══════════════════════════════════════════════════════
# Người xem KHÔNG làm được gì
# ══════════════════════════════════════════════════════


def test_nguoi_xem_khong_tai_len_khong_xoa_duoc(chu, khach) -> None:
    """AC-2 — và đây là nửa quan trọng hơn của AC đó."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb)
    sid = c.get(f"/api/notebooks/{nb}/sources", headers=headers).json()[0]["id"]

    # Không có endpoint ghi nào dưới /api/shared.
    assert khach.post(f"/api/shared/{token}/sources").status_code in (404, 405)

    # Và đường của chủ sở hữu vẫn đòi token đăng nhập, token chia sẻ không thay được.
    h_gia = {"Authorization": f"Bearer {token}"}
    assert khach.get(f"/api/notebooks/{nb}/sources", headers=h_gia).status_code == 401
    assert khach.delete(f"/api/notebooks/{nb}/sources/{sid}", headers=h_gia).status_code == 401
    assert khach.delete(f"/api/notebooks/{nb}", headers=h_gia).status_code == 401


def test_lien_ket_khong_mo_duoc_doan_cua_notebook_khac(chu, khach) -> None:
    """Thiếu điều kiện `notebook_id` thì một liên kết hợp lệ đọc được cả hệ thống."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb)

    # Notebook thứ hai của cùng chủ sở hữu, KHÔNG chia sẻ.
    nb2 = c.post("/api/notebooks", json={"title": "Riêng tư"}, headers=headers).json()["id"]
    c.post(
        f"/api/notebooks/{nb2}/sources",
        headers=headers,
        files={"file": ("rieng.txt", io.BytesIO(TAI_LIEU.encode()), "text/plain")},
    )
    r = c.post(
        "/api/chat/ask",
        json={"question": "thời gian đào tạo", "notebook_id": nb2},
        headers=headers,
    )
    chunk_rieng = next(e for e in _events(r) if e["type"] == "citation")["chunk_id"]

    assert (
        khach.get(f"/api/shared/{token}/citations/{chunk_rieng}").status_code == 404
    ), "liên kết của notebook này không được mở đoạn của notebook khác"
