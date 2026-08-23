"""Tải tài liệu lên và hỏi được — US-006, và đường đi đầu-cuối của cả sản phẩm.

Test cuối tệp này là thứ đo đúng câu hỏi *"app đã dùng được chưa?"*: đăng ký,
tạo notebook, tải một tệp, đợi xử lý xong, hỏi, và nhận câu trả lời có trích dẫn
trỏ về đúng tài liệu vừa tải.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.main import app
from app.models.base import session_scope
from app.models.knowledge import Source, User
from app.settings import settings

pytestmark = pytest.mark.db

EMAIL = "tai-len@example.com"
MAT_KHAU = "mat-khau-du-dai"

TAI_LIEU = """Chương I. Quy định chung

Điều 1. Thời gian đào tạo
Thời gian đào tạo trình độ đại học từ ba đến năm năm đối với văn bằng thứ nhất.

Điều 2. Nghỉ học tạm thời
Người học được nghỉ học tạm thời tối đa hai năm cộng dồn trong toàn khoá học.
Đơn xin nghỉ phải nộp trước ngày bắt đầu học kỳ ba mươi ngày.
"""


@pytest.fixture(autouse=True)
def _providers(monkeypatch):
    """Adapter giả: test này kiểm đường đi, không kiểm chất lượng mô hình."""
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
            s.execute(delete(User).where(User.email == EMAIL))

    wipe()
    yield
    wipe()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def phien(client: TestClient) -> tuple[dict, str]:
    """Tài khoản mới kèm một notebook rỗng."""
    r = client.post("/api/auth/register", json={"email": EMAIL, "password": MAT_KHAU})
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    nb = client.post("/api/notebooks", json={"title": "Quy chế"}, headers=headers)
    assert nb.status_code == 201
    return headers, nb.json()["id"]


def _tai_len(client, headers, nb_id, ten: str, noi_dung: bytes):
    return client.post(
        f"/api/notebooks/{nb_id}/sources",
        headers=headers,
        files={"file": (ten, io.BytesIO(noi_dung), "application/octet-stream")},
    )


# ══════════════════════════════════════════════════════
# Từ chối đúng chỗ — US-006 AC-2, AC-3, AC-4
# ══════════════════════════════════════════════════════


def test_dinh_dang_khong_ho_tro_bi_tu_choi(client, phien) -> None:
    """AC-2 — và thông báo phải liệt kê định dạng nào được nhận."""
    headers, nb_id = phien
    r = _tai_len(client, headers, nb_id, "virus.exe", b"MZ\x90\x00")
    assert r.status_code == 415
    assert ".pdf" in r.json()["detail"]


def test_noi_dung_khong_khop_duoi_bi_tu_choi(client, phien) -> None:
    """AC-5 — đuôi tệp do người tải lên đặt, nên nó không chứng minh được gì.

    Một tệp thực thi đổi tên thành `.pdf` qua được mọi phép kiểm dựa trên tên.
    Chỉ có nội dung mới nói tệp thật sự là gì.
    """
    headers, nb_id = phien
    r = _tai_len(client, headers, nb_id, "baocao.pdf", b"MZ\x90\x00 khong phai PDF")
    assert r.status_code == 415
    assert "không phải PDF" in r.json()["detail"]


def test_tep_qua_lon_bi_tu_choi(client, phien, monkeypatch) -> None:
    """AC-3 — chặn trước khi nuốt hết dữ liệu."""
    monkeypatch.setattr(settings, "max_file_mb", 1)
    headers, nb_id = phien
    r = _tai_len(client, headers, nb_id, "to.txt", b"x" * (2 * 1024 * 1024))
    assert r.status_code == 413
    assert "1 MB" in r.json()["detail"]


def test_qua_nhieu_nguon_bi_tu_choi(client, phien, monkeypatch) -> None:
    """AC-4."""
    monkeypatch.setattr(settings, "max_sources_per_notebook", 1)
    headers, nb_id = phien
    assert _tai_len(client, headers, nb_id, "mot.txt",
                    TAI_LIEU.encode()).status_code == 202
    r = _tai_len(client, headers, nb_id, "hai.txt", TAI_LIEU.encode())
    assert r.status_code == 409
    assert "giới hạn" in r.json()["detail"]


def test_khong_tai_len_duoc_vao_notebook_nguoi_khac(client, phien) -> None:
    """INV-4 — và trả 404, không phải 403."""
    _, nb_id = phien
    r = client.post("/api/auth/register",
                    json={"email": "ke-khac@example.com", "password": MAT_KHAU})
    khac = {"Authorization": f"Bearer {r.json()['access_token']}"}
    try:
        assert _tai_len(client, khac, nb_id, "a.txt",
                        TAI_LIEU.encode()).status_code == 404
    finally:
        with session_scope() as s:
            s.execute(delete(User).where(User.email == "ke-khac@example.com"))


# ══════════════════════════════════════════════════════
# Tên tệp không được dùng làm đường dẫn — US-006 AC-5
# ══════════════════════════════════════════════════════


def test_ten_tep_khong_thanh_duong_dan(client, phien) -> None:
    """Tên do người dùng đặt mà dùng thẳng làm đường dẫn là path traversal.

    Khoá lưu trữ phải là UUID sinh mới; tên gốc chỉ được giữ ở `original_name`
    nơi nó là dữ liệu chứ không phải vị trí.
    """
    headers, nb_id = phien
    doc = "../../../etc/passwd.txt"
    r = _tai_len(client, headers, nb_id, doc, TAI_LIEU.encode())
    assert r.status_code == 202
    assert r.json()["original_name"] == doc

    with session_scope() as s:
        src = s.get(Source, r.json()["id"])
        assert ".." not in src.storage_key
        assert "passwd" not in src.storage_key
        assert src.storage_key.endswith(".txt")


# ══════════════════════════════════════════════════════
# Đường đi đầy đủ: tải lên → xử lý → hỏi → trích dẫn
# ══════════════════════════════════════════════════════


def test_tai_tai_lieu_len_roi_hoi_duoc(client, phien) -> None:
    """Đây là câu hỏi *"app đã dùng được chưa?"* viết thành test.

    `TestClient` chạy `BackgroundTasks` đồng bộ ngay sau khi phản hồi trả về,
    nên khi lệnh POST kết thúc thì tài liệu đã xử lý xong.
    """
    headers, nb_id = phien

    tai_len = _tai_len(client, headers, nb_id, "quy-che.txt", TAI_LIEU.encode())
    assert tai_len.status_code == 202
    assert tai_len.json()["status"] == "queued", "phải trả về ngay, chưa xử lý xong"

    nguon = client.get(f"/api/notebooks/{nb_id}/sources", headers=headers).json()
    assert len(nguon) == 1
    assert nguon[0]["status"] == "ready", nguon[0].get("error_message")
    assert nguon[0]["progress"] == 100
    assert nguon[0]["page_count"] >= 1

    nb = client.get(f"/api/notebooks/{nb_id}", headers=headers).json()
    assert nb["source_count"] == 1
    assert nb["ready_count"] == 1

    hoi = client.post(
        "/api/chat/ask",
        json={"question": "nghỉ học tạm thời tối đa bao lâu", "notebook_id": nb_id},
        headers=headers,
    )
    assert hoi.status_code == 200

    events = [
        json.loads(b[6:]) for b in hoi.text.split("\n\n") if b.startswith("data: ")
    ]
    kinds = [e["type"] for e in events]
    assert "token" in kinds

    trich_dan = [e for e in events if e["type"] == "citation"]
    assert trich_dan, "câu trả lời phải kèm trích dẫn về tài liệu vừa tải"

    chi_tiet = client.get(
        f"/api/citations/{trich_dan[0]['chunk_id']}", headers=headers
    )
    assert chi_tiet.status_code == 200
    assert chi_tiet.json()["content"]


def test_xoa_nguon_thi_xoa_ca_doan_tri_thuc(client, phien) -> None:
    headers, nb_id = phien
    r = _tai_len(client, headers, nb_id, "quy-che.txt", TAI_LIEU.encode())
    source_id = r.json()["id"]

    with session_scope() as s:
        from app.models.knowledge import SourceChunk

        assert s.scalars(
            select(SourceChunk).where(SourceChunk.source_id == source_id)
        ).all()

    assert client.delete(
        f"/api/notebooks/{nb_id}/sources/{source_id}", headers=headers
    ).status_code == 204

    with session_scope() as s:
        from app.models.knowledge import SourceChunk

        assert not s.scalars(
            select(SourceChunk).where(SourceChunk.source_id == source_id)
        ).all()


def test_xoa_notebook_xoa_sach_moi_thu(client, phien) -> None:
    """US-005 AC-4."""
    headers, nb_id = phien
    _tai_len(client, headers, nb_id, "quy-che.txt", TAI_LIEU.encode())

    assert client.delete(f"/api/notebooks/{nb_id}",
                         headers=headers).status_code == 204
    assert client.get(f"/api/notebooks/{nb_id}",
                      headers=headers).status_code == 404
    assert client.get("/api/notebooks", headers=headers).json() == []
