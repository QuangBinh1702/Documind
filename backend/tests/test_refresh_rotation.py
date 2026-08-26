"""Xoay vòng và thu hồi refresh token — US-003 AC-3, US-004.

Ba điều bảng `refresh_tokens` phải bảo đảm mà dấu vân tay mật khẩu không làm được:

* một refresh token chỉ đổi được ĐÚNG MỘT lần;
* đăng xuất thì token của phiên đó chết ngay, không đợi hết hạn;
* dùng lại một token đã xoay là dấu hiệu bị lộ, và mọi phiên của người đó bị
  thu hồi theo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.models.base import session_scope
from app.models.knowledge import User

pytestmark = pytest.mark.db

EMAIL = "rotation@example.com"
MAT_KHAU = "mat-khau-xoay-vong"


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        with session_scope() as s:
            s.execute(delete(User).where(User.email == EMAIL))

    wipe()
    yield
    wipe()


@pytest.fixture
def client():
    return TestClient(app)


def _dang_ky(client: TestClient) -> dict:
    r = client.post("/api/auth/register", json={"email": EMAIL, "password": MAT_KHAU})
    assert r.status_code == 201, r.text
    return r.json()


def test_refresh_chi_dung_duoc_mot_lan(client: TestClient) -> None:
    cap = _dang_ky(client)

    lan_1 = client.post("/api/auth/refresh", json={"refresh_token": cap["refresh_token"]})
    assert lan_1.status_code == 200
    assert lan_1.json()["refresh_token"] != cap["refresh_token"]

    lan_2 = client.post("/api/auth/refresh", json={"refresh_token": cap["refresh_token"]})
    assert lan_2.status_code == 401
    assert "không còn hiệu lực" in lan_2.json()["detail"]


def test_dung_lai_token_da_xoay_thu_hoi_ca_chuoi(client: TestClient) -> None:
    cap = _dang_ky(client)
    moi = client.post("/api/auth/refresh", json={"refresh_token": cap["refresh_token"]}).json()

    # Kẻ giữ bản sao cũ dùng lại → cả token mới (đang ở tay người dùng) cũng chết.
    client.post("/api/auth/refresh", json={"refresh_token": cap["refresh_token"]})
    r = client.post("/api/auth/refresh", json={"refresh_token": moi["refresh_token"]})
    assert r.status_code == 401


def test_dang_xuat_thu_hoi_refresh_token(client: TestClient) -> None:
    cap = _dang_ky(client)

    r = client.post("/api/auth/logout", json={"refresh_token": cap["refresh_token"]})
    assert r.status_code == 204

    r = client.post("/api/auth/refresh", json={"refresh_token": cap["refresh_token"]})
    assert r.status_code == 401

    # Access token vẫn dùng được tới khi hết hạn — đó là giới hạn đã biết của
    # JWT không trạng thái, và là lý do access token chỉ sống 60 phút.
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {cap['access_token']}"})
    assert r.status_code == 200


def test_dang_xuat_voi_token_hong_khong_loi(client: TestClient) -> None:
    r = client.post("/api/auth/logout", json={"refresh_token": "khong-phai-token"})
    assert r.status_code == 204


def test_doi_mat_khau_thu_hoi_moi_refresh_token(client: TestClient) -> None:
    cap = _dang_ky(client)
    khac = client.post("/api/auth/refresh", json={"refresh_token": cap["refresh_token"]}).json()

    r = client.post(
        "/api/auth/change-password",
        json={"old_password": MAT_KHAU, "new_password": "mat-khau-moi-hoan-toan"},
        headers={"Authorization": f"Bearer {khac['access_token']}"},
    )
    assert r.status_code == 200
    moi_nhat = r.json()

    assert client.post("/api/auth/refresh", json={"refresh_token": khac["refresh_token"]}).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": moi_nhat["refresh_token"]}).status_code == 200
