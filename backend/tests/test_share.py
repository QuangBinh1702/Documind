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


@pytest.fixture
def nguoi_xem(khach: TestClient) -> dict:
    """Một tài khoản khác chủ sở hữu — người nhận liên kết, đã đăng nhập."""
    r = khach.post("/api/auth/register", json={"email": NGUOI_LA, "password": MAT_KHAU})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _chia_se(c: TestClient, headers: dict, nb: str, phien: str | None = None) -> str:
    r = c.post(
        f"/api/notebooks/{nb}/share",
        headers=headers,
        json={"session_id": phien} if phien else None,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _events(response) -> list[dict]:
    return [
        json.loads(b[6:]) for b in response.text.split("\n\n") if b.startswith("data: ")
    ]


def _hoi(c: TestClient, headers: dict, nb: str, cau_hoi: str) -> str:
    """Một lượt hỏi của chủ sở hữu. Trả về id phiên vừa sinh ra."""
    r = c.post(
        "/api/chat/ask",
        json={"question": cau_hoi, "notebook_id": nb},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return next(e for e in _events(r) if e["type"] == "session")["session_id"]


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


def test_nguoi_xem_doc_duoc_doan_chat_da_chia_se(chu, khach) -> None:
    """Lý do tồn tại của liên kết: người nhận thấy đúng đoạn hỏi đáp đã gửi.

    Đây từng là ca hỏng nặng nhất của tính năng — liên kết mở ra một màn hình
    trống, và không có gì trên giao diện nói được vì sao.
    """
    c, headers, nb = chu
    phien = _hoi(c, headers, nb, "nghỉ học tạm thời tối đa bao lâu")
    token = _chia_se(c, headers, nb, phien)

    d = khach.get(f"/api/shared/{token}").json()
    assert d["phien_id"] == phien
    assert d["phien_tieu_de"]

    vai = [m["role"] for m in d["tin_nhan"]]
    assert vai == ["user", "assistant"], vai
    assert d["tin_nhan"][0]["content"] == "nghỉ học tạm thời tối đa bao lâu"
    assert d["tin_nhan"][1]["content"]


def test_chip_trich_dan_van_bam_duoc_qua_lien_ket(chu, khach) -> None:
    """US-018 AC-3 nhìn từ phía người xem: chip phải mở ra được đoạn gốc."""
    c, headers, nb = chu
    phien = _hoi(c, headers, nb, "nghỉ học tạm thời tối đa bao lâu")
    token = _chia_se(c, headers, nb, phien)

    tra_loi = khach.get(f"/api/shared/{token}").json()["tin_nhan"][1]
    assert tra_loi["citations"], "câu trả lời có căn cứ mà không kèm trích dẫn nào"

    chunk_id = tra_loi["citations"][0]["chunk_id"]
    chi_tiet = khach.get(f"/api/shared/{token}/citations/{chunk_id}")
    assert chi_tiet.status_code == 200
    assert chi_tiet.json()["content"]


def test_lien_ket_chi_mo_dung_phien_da_chia_se(chu, khach) -> None:
    """Chia sẻ một hội thoại không được kéo theo những hội thoại khác."""
    c, headers, nb = chu
    phien = _hoi(c, headers, nb, "thời gian đào tạo")
    _hoi(c, headers, nb, "nghỉ học tạm thời tối đa bao lâu")
    token = _chia_se(c, headers, nb, phien)

    tin_nhan = khach.get(f"/api/shared/{token}").json()["tin_nhan"]
    assert [m["content"] for m in tin_nhan if m["role"] == "user"] == [
        "thời gian đào tạo"
    ]


def test_khong_chia_se_duoc_phien_cua_notebook_khac(chu) -> None:
    """Thiếu phép kiểm này, một `session_id` đoán được là đọc được mọi hội thoại."""
    c, headers, nb = chu
    nb2 = c.post("/api/notebooks", json={"title": "Riêng tư"}, headers=headers).json()["id"]
    c.post(
        f"/api/notebooks/{nb2}/sources",
        headers=headers,
        files={"file": ("rieng.txt", io.BytesIO(TAI_LIEU.encode()), "text/plain")},
    )
    phien_rieng = _hoi(c, headers, nb2, "thời gian đào tạo")

    r = c.post(
        f"/api/notebooks/{nb}/share",
        headers=headers,
        json={"session_id": phien_rieng},
    )
    assert r.status_code == 404, r.text


def test_moi_phien_co_lien_ket_rieng(chu) -> None:
    """Một notebook nhiều hội thoại thì mỗi hội thoại một token."""
    c, headers, nb = chu
    a = _chia_se(c, headers, nb, _hoi(c, headers, nb, "thời gian đào tạo"))
    b = _chia_se(c, headers, nb, _hoi(c, headers, nb, "nghỉ học tạm thời"))
    assert a != b


def test_nguoi_xem_da_dang_nhap_hoi_duoc(chu, khach, nguoi_xem) -> None:
    """AC-2 — hỏi được là điểm khác biệt so với "gửi một tệp PDF"."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb, _hoi(c, headers, nb, "thời gian đào tạo"))

    r = khach.post(
        f"/api/shared/{token}/ask",
        json={"question": "nghỉ học tạm thời tối đa bao lâu"},
        headers=nguoi_xem,
    )
    assert r.status_code == 200, r.text
    events = _events(r)
    assert any(e["type"] == "token" for e in events)

    cite = next(e for e in events if e["type"] == "citation")
    chi_tiet = khach.get(f"/api/shared/{token}/citations/{cite['chunk_id']}")
    assert chi_tiet.status_code == 200
    assert chi_tiet.json()["content"]


def test_chua_dang_nhap_thi_doc_duoc_nhung_khong_hoi_duoc(chu, khach) -> None:
    """Ranh giới của tính năng, trong một test.

    Đọc không cần tài khoản — đó là thứ làm liên kết có ích. Hỏi thì cần, vì
    câu hỏi phải thuộc về một ai đó và tiêu hạn mức của người ấy.
    """
    c, headers, nb = chu
    token = _chia_se(c, headers, nb, _hoi(c, headers, nb, "thời gian đào tạo"))

    assert khach.get(f"/api/shared/{token}").status_code == 200
    r = khach.post(f"/api/shared/{token}/ask", json={"question": "nghỉ học"})
    assert r.status_code == 401, r.text


def test_cau_hoi_cua_nguoi_xem_khong_vao_lich_su_chu_so_huu(chu, khach, nguoi_xem) -> None:
    """Chia sẻ tài liệu không đồng nghĩa với cho người khác ghi vào lịch sử của mình."""
    c, headers, nb = chu
    cua_chu = _hoi(c, headers, nb, "thời gian đào tạo")
    token = _chia_se(c, headers, nb, cua_chu)

    khach.post(
        f"/api/shared/{token}/ask",
        json={"question": "nghỉ học tạm thời tối đa bao lâu"},
        headers=nguoi_xem,
    )

    cua_toi = c.get(f"/api/sessions?notebook_id={nb}", headers=headers).json()
    assert [p["id"] for p in cua_toi] == [cua_chu], (
        "hội thoại của người xem lọt vào danh sách phiên của chủ notebook"
    )


def test_cau_hoi_cua_nguoi_xem_vao_lich_su_cua_chinh_ho(chu, khach, nguoi_xem) -> None:
    """Người xem quay lại thì đọc lại được thứ chính mình đã hỏi."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb, _hoi(c, headers, nb, "thời gian đào tạo"))

    khach.post(
        f"/api/shared/{token}/ask",
        json={"question": "nghỉ học tạm thời tối đa bao lâu"},
        headers=nguoi_xem,
    )

    phien = khach.get(f"/api/shared/{token}/my-sessions", headers=nguoi_xem).json()
    assert len(phien) == 1, phien

    tin_nhan = khach.get(
        f"/api/shared/{token}/my-sessions/{phien[0]['id']}/messages", headers=nguoi_xem
    ).json()
    assert tin_nhan[0]["content"] == "nghỉ học tạm thời tối đa bao lâu"


def test_nguoi_xem_khong_doc_duoc_phien_cua_nguoi_khac(chu, khach, nguoi_xem) -> None:
    """Cùng một notebook, hai người — mỗi người chỉ thấy hội thoại của mình."""
    c, headers, nb = chu
    cua_chu = _hoi(c, headers, nb, "thời gian đào tạo")
    token = _chia_se(c, headers, nb, cua_chu)

    assert khach.get(
        f"/api/shared/{token}/my-sessions", headers=nguoi_xem
    ).json() == []
    assert (
        khach.get(
            f"/api/shared/{token}/my-sessions/{cua_chu}/messages", headers=nguoi_xem
        ).status_code
        == 404
    )


def test_chu_notebook_khong_doc_duoc_phien_cua_nguoi_xem(chu, khach, nguoi_xem) -> None:
    """Chiều ngược lại, và là chiều dễ bị bỏ quên.

    Chủ notebook sở hữu tài liệu, không sở hữu câu hỏi người khác đặt ra về
    chúng. Trước migration 0004 điều này không diễn đạt được ở tầng SQL.
    """
    c, headers, nb = chu
    token = _chia_se(c, headers, nb, _hoi(c, headers, nb, "thời gian đào tạo"))

    r = khach.post(
        f"/api/shared/{token}/ask",
        json={"question": "nghỉ học tạm thời tối đa bao lâu"},
        headers=nguoi_xem,
    )
    cua_ho = next(e for e in _events(r) if e["type"] == "session")["session_id"]

    assert c.get(f"/api/sessions/{cua_ho}/messages", headers=headers).status_code == 404
    assert c.get(f"/api/sessions/{cua_ho}/export", headers=headers).status_code == 404


def test_nguoi_xem_mo_duoc_tai_lieu_de_kiem_chung(chu, khach) -> None:
    """US-015 — trích dẫn chỉ kiểm chứng được khi mở ra được ngữ cảnh quanh nó."""
    c, headers, nb = chu
    token = _chia_se(c, headers, nb, _hoi(c, headers, nb, "thời gian đào tạo"))
    src = khach.get(f"/api/shared/{token}").json()["nguon"][0]["id"]

    r = khach.get(f"/api/shared/{token}/sources/{src}/text")
    assert r.status_code == 200, r.text
    assert "Nghỉ học tạm thời" in r.json()["full_text"]


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

    # Và điều đó phải đúng cho cả đường đọc tài liệu, không chỉ đường trích dẫn.
    src_rieng = c.get(f"/api/notebooks/{nb2}/sources", headers=headers).json()[0]["id"]
    assert khach.get(f"/api/shared/{token}/sources/{src_rieng}/text").status_code == 404
    assert khach.get(f"/api/shared/{token}/sources/{src_rieng}/file").status_code == 404
