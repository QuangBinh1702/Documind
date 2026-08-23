"""Xác thực và phiên đăng nhập — US-002, US-003, US-004.

Phần lớn test ở đây kiểm những thứ **không được lộ ra**, chứ không phải những
thứ hoạt động: thông báo lỗi không được phân biệt sai email với sai mật khẩu,
notebook của người khác không được trả về 403, và mật khẩu không được nằm trong
cơ sở dữ liệu ở dạng đọc được.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.main import app
from app.models.base import session_scope
from app.models.knowledge import User

pytestmark = pytest.mark.db

MAT_KHAU = "mat-khau-du-dai"
EMAIL = "nguoi-dung@example.com"
EMAIL_2 = "nguoi-khac@example.com"


@pytest.fixture(autouse=True)
def sach():
    def wipe():
        with session_scope() as s:
            s.execute(delete(User).where(User.email.in_([EMAIL, EMAIL_2])))

    wipe()
    yield
    wipe()


@pytest.fixture(autouse=True)
def _bo_chan_dang_nhap(monkeypatch):
    """Tắt bộ đếm Redis cho phần lớn test.

    Nó đếm theo email và sống qua nhiều lần chạy, nên để nguyên thì test thứ
    hai gọi sai mật khẩu sẽ dính khoá của test thứ nhất. Ca khoá được kiểm
    riêng ở `test_khoa_sau_nam_lan_sai`.
    """
    from app.services import login_guard

    monkeypatch.setattr(login_guard, "con_bao_lau", lambda email: 0)
    monkeypatch.setattr(login_guard, "ghi_that_bai", lambda email: None)
    monkeypatch.setattr(login_guard, "xoa_dem", lambda email: None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _dang_ky(client: TestClient, email: str = EMAIL) -> dict:
    r = client.post("/api/auth/register", json={"email": email, "password": MAT_KHAU})
    assert r.status_code == 201, r.text
    return r.json()


def _headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ══════════════════════════════════════════════════════
# Đăng ký — US-002
# ══════════════════════════════════════════════════════


def test_dang_ky_xong_la_dang_nhap_luon(client: TestClient) -> None:
    """AC-1 — không bắt người dùng nhập lại ngay thứ vừa nhập."""
    tokens = _dang_ky(client)
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["expires_in"] > 0

    r = client.get("/api/auth/me", headers=_headers(tokens))
    assert r.status_code == 200
    assert r.json()["email"] == EMAIL


def test_mat_khau_khong_bao_gio_nam_trong_db_o_dang_doc_duoc(client: TestClient) -> None:
    """AC-4 — cột `password_hash` phải là hash, không phải mật khẩu."""
    _dang_ky(client)
    with session_scope() as s:
        user = s.scalar(select(User).where(User.email == EMAIL))
        assert MAT_KHAU not in user.password_hash
        assert user.password_hash.startswith("$argon2id$")


def test_email_trung_khong_tiet_lo_them_gi(client: TestClient) -> None:
    """AC-2 — báo trùng, và KHÔNG nói gì thêm về tài khoản đó."""
    _dang_ky(client)
    r = client.post(
        "/api/auth/register", json={"email": EMAIL, "password": "mot-mat-khau-khac"}
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "đã được đăng ký" in detail
    # Không được lộ thời điểm tạo, vai trò, hay có bao nhiêu notebook.
    assert not any(x in detail.lower() for x in ("notebook", "created", "role", "admin"))


@pytest.mark.parametrize(
    "email,mat_khau",
    [("khong-phai-email", MAT_KHAU), (EMAIL, "ngan"), (EMAIL, "")],
)
def test_dau_vao_sai_bi_tu_choi(client: TestClient, email, mat_khau) -> None:
    """AC-3 — giao diện kiểm trước, nhưng máy chủ vẫn không tin giao diện."""
    r = client.post("/api/auth/register", json={"email": email, "password": mat_khau})
    assert r.status_code == 422


# ══════════════════════════════════════════════════════
# Đăng nhập — US-003
# ══════════════════════════════════════════════════════


def test_dang_nhap_dung(client: TestClient) -> None:
    _dang_ky(client)
    r = client.post("/api/auth/login", json={"email": EMAIL, "password": MAT_KHAU})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_sai_email_va_sai_mat_khau_khong_phan_biet_duoc(client: TestClient) -> None:
    """AC-2 — đây là điều biến trang đăng nhập thành công cụ dò email nếu làm sai.

    Hai ca phải trả về **cùng mã trạng thái và cùng câu chữ**.
    """
    _dang_ky(client)
    sai_mat_khau = client.post(
        "/api/auth/login", json={"email": EMAIL, "password": "sai-mat-khau-roi"}
    )
    khong_co_email = client.post(
        "/api/auth/login", json={"email": "ai-do@example.com", "password": MAT_KHAU}
    )

    assert sai_mat_khau.status_code == khong_co_email.status_code == 401
    assert sai_mat_khau.json() == khong_co_email.json()


def test_khong_co_token_thi_401(client: TestClient) -> None:
    """AC-4 — truy cập thẳng URL khi chưa đăng nhập."""
    assert client.get("/api/notebooks").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_token_bay_ba_bi_tu_choi(client: TestClient) -> None:
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer khong-phai-token"})
    assert r.status_code == 401


def test_lam_moi_cap_token_moi(client: TestClient) -> None:
    """AC-3 — frontend tự refresh, người dùng không thấy gián đoạn."""
    tokens = _dang_ky(client)
    r = client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=_headers(r.json())).status_code == 200


def test_khong_dung_access_token_thay_cho_refresh(client: TestClient) -> None:
    """Nhận nhầm sẽ kéo dài phiên vượt hạn mức 60 phút mà không ai để ý."""
    tokens = _dang_ky(client)
    r = client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert r.status_code == 401


def test_khoa_sau_nam_lan_sai(client: TestClient, monkeypatch) -> None:
    """AC-5 — năm lần sai thì lần thứ sáu bị chặn.

    Dùng bộ đếm trong bộ nhớ thay cho Redis: test này kiểm **chính sách**, còn
    việc Redis đếm đúng hay không là chuyện của Redis.
    """
    from app.services import login_guard

    dem: dict[str, int] = {}
    monkeypatch.setattr(login_guard, "ghi_that_bai",
                        lambda e: dem.__setitem__(e, dem.get(e, 0) + 1))
    monkeypatch.setattr(login_guard, "con_bao_lau",
                        lambda e: 900 if dem.get(e, 0) >= 5 else 0)

    _dang_ky(client)
    for _ in range(5):
        r = client.post("/api/auth/login", json={"email": EMAIL, "password": "sai-roi"})
        assert r.status_code == 401

    r = client.post("/api/auth/login", json={"email": EMAIL, "password": MAT_KHAU})
    assert r.status_code == 429, "đúng mật khẩu nhưng đã bị khoá thì vẫn phải chặn"
    assert "phút" in r.json()["detail"]


# ══════════════════════════════════════════════════════
# Đổi mật khẩu — US-004
# ══════════════════════════════════════════════════════


def test_doi_mat_khau_giet_moi_token_cu(client: TestClient) -> None:
    """AC-2 — **tất cả** refresh token cũ bị vô hiệu.

    Đây là điều bảo vệ tài khoản khi người dùng đổi mật khẩu vì nghi bị lộ:
    kẻ đang giữ token cũ phải mất quyền ngay, không phải đợi token hết hạn.
    """
    tokens = _dang_ky(client)
    assert client.get("/api/auth/me", headers=_headers(tokens)).status_code == 200

    r = client.post(
        "/api/auth/change-password",
        json={"old_password": MAT_KHAU, "new_password": "mat-khau-hoan-toan-moi"},
        headers=_headers(tokens),
    )
    assert r.status_code == 200

    assert client.get("/api/auth/me", headers=_headers(tokens)).status_code == 401
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).status_code == 401

    # Cặp token mới cấp cùng lúc thì vẫn dùng được — người vừa đổi không bị đá ra.
    assert client.get("/api/auth/me", headers=_headers(r.json())).status_code == 200


def test_sai_mat_khau_cu_thi_khong_doi_gi(client: TestClient) -> None:
    """AC-3."""
    tokens = _dang_ky(client)
    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "khong-phai-cai-nay", "new_password": "mat-khau-moi-dai"},
        headers=_headers(tokens),
    )
    assert r.status_code == 401
    # Mật khẩu cũ vẫn dùng được, token cũ vẫn sống.
    assert client.post(
        "/api/auth/login", json={"email": EMAIL, "password": MAT_KHAU}
    ).status_code == 200
    assert client.get("/api/auth/me", headers=_headers(tokens)).status_code == 200


# ══════════════════════════════════════════════════════
# Cách ly giữa người dùng — US-005 AC-5, INV-4
# ══════════════════════════════════════════════════════


def test_notebook_cua_nguoi_khac_tra_ve_404_khong_phai_403(client: TestClient) -> None:
    """403 xác nhận tài nguyên CÓ tồn tại.

    Ai muốn dò xem người khác có notebook nào chỉ cần thử id cho tới khi thấy
    403 thay vì 404. Với 404 thì "không tồn tại" và "không phải của bạn" không
    phân biệt được từ bên ngoài.
    """
    a = _dang_ky(client, EMAIL)
    b = _dang_ky(client, EMAIL_2)

    nb = client.post("/api/notebooks", json={"title": "Của A"}, headers=_headers(a))
    assert nb.status_code == 201
    nb_id = nb.json()["id"]

    for goi in (
        lambda: client.get(f"/api/notebooks/{nb_id}", headers=_headers(b)),
        lambda: client.patch(f"/api/notebooks/{nb_id}", json={"title": "Cướp"},
                             headers=_headers(b)),
        lambda: client.delete(f"/api/notebooks/{nb_id}", headers=_headers(b)),
        lambda: client.get(f"/api/notebooks/{nb_id}/sources", headers=_headers(b)),
    ):
        assert goi().status_code == 404


def test_chi_thay_notebook_cua_minh(client: TestClient) -> None:
    a = _dang_ky(client, EMAIL)
    b = _dang_ky(client, EMAIL_2)
    client.post("/api/notebooks", json={"title": "Của A"}, headers=_headers(a))
    client.post("/api/notebooks", json={"title": "Của B"}, headers=_headers(b))

    cua_a = client.get("/api/notebooks", headers=_headers(a)).json()
    assert [n["title"] for n in cua_a] == ["Của A"]
