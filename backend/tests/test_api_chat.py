"""API hội thoại và hợp đồng SSE — `SPEC-v1.md` §7.1.

Giao diện phụ thuộc vào tên sự kiện và thứ tự phát ra, nên chúng là **hợp
đồng** chứ không phải chi tiết cài đặt. Đổi chúng mà không đổi giao diện là
làm hỏng một cách im lặng.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.adapters.embedding.fake import FakeEmbeddingProvider
from app.main import app
from app.models.base import session_scope
from app.models.knowledge import Notebook, User
from app.services.ingest import ingest_file_sync
from app.settings import settings

pytestmark = pytest.mark.db

# `@example.com` chứ không phải `@documind.local`: `email-validator` từ chối
# `.local` vì đó là tên miền dành riêng, và lượt đăng ký sẽ trả 422.
OWNER = "api@example.com"
NGUOI_LA = "api-nguoila@example.com"
MAT_KHAU = "Mat-Khau-Rat-Dai-2026"
NOTEBOOK = "api-test"

DOC = """Điều 1. Thời gian đào tạo
Thời gian đào tạo trình độ đại học từ ba đến năm năm đối với văn bằng thứ nhất.

Điều 2. Chương trình đào tạo
Chương trình đào tạo được xây dựng theo chuẩn đầu ra đã công bố công khai.
"""


@pytest.fixture(autouse=True)
def _providers(monkeypatch):
    """Ép dùng adapter giả để test không cần GPU, khoá API hay mạng."""
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
def clean():
    def wipe():
        with session_scope() as s:
            s.execute(delete(User).where(User.email.in_([OWNER, NGUOI_LA])))

    wipe()
    yield
    wipe()


@pytest.fixture(autouse=True)
def _bo_chan_dang_nhap(monkeypatch):
    """Tắt bộ đếm chặn đăng nhập — nó cần Redis và không liên quan gì ở đây."""
    from app.services import login_guard

    monkeypatch.setattr(login_guard, "con_bao_lau", lambda email: 0)
    monkeypatch.setattr(login_guard, "ghi_that_bai", lambda email: None)
    monkeypatch.setattr(login_guard, "xoa_dem", lambda email: None)


def _dang_ky(c: TestClient, email: str) -> str:
    r = c.post("/api/auth/register", json={"email": email, "password": MAT_KHAU})
    assert r.status_code in (200, 201), r.text
    return r.json()["access_token"]


@pytest.fixture
def khach() -> TestClient:
    """Client chưa đăng nhập — dùng để kiểm chính việc bị từ chối."""
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    """Client đã đăng nhập bằng tài khoản chủ sở hữu.

    Mọi endpoint hội thoại đều đòi token. Trước đây chúng mở, và bàn thử ở `/`
    dựa vào điều đó — nhưng nó có nghĩa là biết `notebook_id` là hỏi được tài
    liệu của người khác, đồng thời tiêu hạn mức gọi API của họ.
    """
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {_dang_ky(c, OWNER)}"
    return c


@pytest.fixture
def notebook_id(tmp_path, client: TestClient):
    """Phụ thuộc `client` để tài khoản được tạo qua API TRƯỚC khi nạp tài liệu.

    Ngược lại thì `get_or_create_user` tạo một hàng không có mật khẩu, và lượt
    đăng ký sau đó báo trùng email.
    """
    p = tmp_path / "quy-che.txt"
    p.write_text(DOC, encoding="utf-8")
    with session_scope() as s:
        ingest_file_sync(
            s, p, notebook_title=NOTEBOOK,
            embedder=FakeEmbeddingProvider(dim=1024), owner_email=OWNER,
        )
    with session_scope() as s:
        user = s.scalar(select(User).where(User.email == OWNER))
        nb = s.scalar(select(Notebook).where(Notebook.user_id == user.id))
        return str(nb.id)


def _events(response) -> list[dict]:
    out = []
    for block in response.text.split("\n\n"):
        if block.startswith("data: "):
            out.append(json.loads(block[6:]))
    return out


# ══════════════════════════════════════════════════════
# Dữ liệu phụ trợ
# ══════════════════════════════════════════════════════


def test_loi_he_thong_khong_lo_cau_sql_ra_giao_dien(
    client: TestClient, notebook_id: str, monkeypatch
) -> None:
    """Thông báo lỗi của SQLAlchemy mang theo cả câu lệnh và tham số.

    Đã gặp thật: một `CheckViolation` làm nguyên văn câu INSERT — kèm nội dung
    tin nhắn, khoá chính, tên bảng và tên cột — hiện lên khung chat. Vừa là rò
    rỉ cấu trúc cơ sở dữ liệu, vừa là thứ người dùng không làm gì được.
    """
    import app.api.chat as mod

    class VoTinh(Exception):
        """Ngoại lệ hệ thống bất kỳ — không phải loại đã soạn cho người dùng."""

    async def no_vo(*a, **kw):
        raise VoTinh(
            "[SQL: INSERT INTO chat_messages ...] [parameters: {'content': 'bí mật'}]"
        )
        yield  # pragma: no cover

    monkeypatch.setattr(mod, "ask", no_vo)
    r = client.post("/api/chat/ask", json={"question": "x", "notebook_id": notebook_id})
    err = next(e for e in _events(r) if e["type"] == "error")

    assert "SQL" not in err["message"]
    assert "bí mật" not in err["message"]
    assert "INSERT" not in err["message"]
    assert err["code"] == "VoTinh", "mã lỗi vẫn phải giữ để đối chiếu với log"


def test_loi_da_soan_cho_nguoi_dung_thi_giu_nguyen(
    client: TestClient, notebook_id: str, monkeypatch
) -> None:
    """Adapter mô hình ném `RuntimeError` với câu đã viết sẵn cho người dùng —
    hết hạn mức, sai khoá. Nuốt mất câu đó là bỏ đi thứ duy nhất giúp họ tự sửa.
    """
    import app.api.chat as mod

    async def het_han_muc(*a, **kw):
        raise RuntimeError("Đã hết hạn mức gọi trong ngày. Đổi GEMINI_MODEL.")
        yield  # pragma: no cover

    monkeypatch.setattr(mod, "ask", het_han_muc)
    r = client.post("/api/chat/ask", json={"question": "x", "notebook_id": notebook_id})
    err = next(e for e in _events(r) if e["type"] == "error")
    assert "hạn mức" in err["message"]


# ══════════════════════════════════════════════════════
# Quyền truy cập
# ══════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("phuong_thuc", "duong", "than"),
    [
        ("post", "/api/chat/ask", {"question": "x", "notebook_id": str(uuid.uuid4())}),
        ("post", "/api/chat/ask-external",
         {"question": "x", "notebook_id": str(uuid.uuid4())}),
        ("get", f"/api/sessions?notebook_id={uuid.uuid4()}", None),
        ("get", f"/api/sessions/{uuid.uuid4()}/messages", None),
        ("get", "/api/citations/1", None),
    ],
)
def test_moi_endpoint_hoi_thoai_deu_doi_dang_nhap(
    khach: TestClient, phuong_thuc: str, duong: str, than: dict | None
) -> None:
    """Không có endpoint hội thoại nào được mở.

    Đây từng là một lỗ hổng thật: biết `notebook_id` là hỏi được tài liệu của
    người khác, và lượt gọi ra ngoài tính vào hạn mức của họ.
    """
    r = getattr(khach, phuong_thuc)(duong, **({"json": than} if than else {}))
    assert r.status_code == 401, duong


def test_notebook_cua_nguoi_khac_tra_ve_khong_tim_thay(
    khach: TestClient, notebook_id: str
) -> None:
    """404 chứ không phải 403 — xem `app/api/deps.py`."""
    khach.headers["Authorization"] = f"Bearer {_dang_ky(khach, NGUOI_LA)}"
    r = khach.post(
        "/api/chat/ask", json={"question": "gì đó", "notebook_id": notebook_id}
    )
    err = next(e for e in _events(r) if e["type"] == "error")
    assert err["code"] == "NOT_FOUND"

    assert khach.get(f"/api/sessions?notebook_id={notebook_id}").status_code == 404


def test_trich_dan_cua_nguoi_khac_khong_doc_duoc(
    client: TestClient, khach: TestClient, notebook_id: str
) -> None:
    """Đoạn trích dẫn mang nguyên văn nội dung tài liệu.

    Đọc được `chunk_id` của người khác là đọc được tài liệu của họ từng mẩu một,
    kể cả khi không mở được cả tệp.
    """
    r = client.post(
        "/api/chat/ask",
        json={"question": "thời gian đào tạo trình độ đại học", "notebook_id": notebook_id},
    )
    chunk_id = next(e for e in _events(r) if e["type"] == "citation")["chunk_id"]
    assert client.get(f"/api/citations/{chunk_id}").status_code == 200

    khach.headers["Authorization"] = f"Bearer {_dang_ky(khach, NGUOI_LA)}"
    assert khach.get(f"/api/citations/{chunk_id}").status_code == 404


# ══════════════════════════════════════════════════════
# Hợp đồng SSE
# ══════════════════════════════════════════════════════


def test_hoi_dap_phat_su_kien_dung_thu_tu(client: TestClient, notebook_id: str) -> None:
    r = client.post(
        "/api/chat/ask",
        json={"question": "thời gian đào tạo đại học bao lâu", "notebook_id": notebook_id},
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]

    events = _events(r)
    kinds = [e["type"] for e in events]

    assert "session" in kinds, "lượt đầu phải tạo phiên mới"
    assert kinds.index("meta") < kinds.index("token")
    assert "saved" in kinds, "câu trả lời phải được lưu"
    assert kinds.index("done") < kinds.index("saved")


def test_su_kien_khong_chua_doi_tuong_khong_tuan_tu_hoa_duoc(
    client: TestClient, notebook_id: str
) -> None:
    """`AnswerResult` bị lược khỏi payload — nếu lọt qua, JSON sẽ vỡ."""
    r = client.post(
        "/api/chat/ask",
        json={"question": "chương trình đào tạo", "notebook_id": notebook_id},
    )
    done = next(e for e in _events(r) if e["type"] == "done")
    assert "result" not in done
    assert "answer_kind" in done
    assert "latency_ms" in done


def test_tra_loi_co_trich_dan_bam_duoc(client: TestClient, notebook_id: str) -> None:
    r = client.post(
        "/api/chat/ask",
        json={"question": "thời gian đào tạo trình độ đại học", "notebook_id": notebook_id},
    )
    cites = [e for e in _events(r) if e["type"] == "citation"]
    assert cites

    c = cites[0]
    for key in ("marker", "chunk_id", "source_id", "char_start", "char_end", "snippet"):
        assert key in c, f"thiếu trường {key} trong sự kiện citation"

    detail = client.get(f"/api/citations/{c['chunk_id']}")
    assert detail.status_code == 200
    assert detail.json()["content"]


def test_notebook_khong_ton_tai(client: TestClient) -> None:
    r = client.post(
        "/api/chat/ask",
        json={"question": "gì đó", "notebook_id": "00000000-0000-0000-0000-000000000000"},
    )
    err = next(e for e in _events(r) if e["type"] == "error")
    assert err["code"] == "NOT_FOUND"


def test_trich_dan_khong_ton_tai_tra_404(client: TestClient) -> None:
    assert client.get("/api/citations/999999999").status_code == 404


def test_cau_hoi_rong_bi_tu_choi(client: TestClient, notebook_id: str) -> None:
    r = client.post("/api/chat/ask", json={"question": "", "notebook_id": notebook_id})
    assert r.status_code == 422


# ══════════════════════════════════════════════════════
# Lịch sử hội thoại — US-018
# ══════════════════════════════════════════════════════


def test_luu_va_doc_lai_duoc_hoi_thoai(client: TestClient, notebook_id: str) -> None:
    """US-018 AC-3 — chip trích dẫn hiển thị lại đầy đủ khi mở phiên cũ."""
    first = client.post(
        "/api/chat/ask",
        json={"question": "thời gian đào tạo đại học", "notebook_id": notebook_id},
    )
    session_id = next(e for e in _events(first) if e["type"] == "session")["session_id"]

    sessions = client.get("/api/sessions", params={"notebook_id": notebook_id}).json()
    assert any(s["id"] == session_id for s in sessions)

    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"

    answer = messages[1]
    assert answer["role"] == "assistant"
    assert answer["answer_kind"] in {"grounded", "no_answer"}
    if answer["answer_kind"] == "grounded":
        assert answer["citations"]
        assert all(not c["deleted"] for c in answer["citations"])


def test_tiep_tuc_phien_cu(client: TestClient, notebook_id: str) -> None:
    first = client.post(
        "/api/chat/ask",
        json={"question": "thời gian đào tạo đại học", "notebook_id": notebook_id},
    )
    session_id = next(e for e in _events(first) if e["type"] == "session")["session_id"]

    second = client.post(
        "/api/chat/ask",
        json={
            "question": "còn chương trình đào tạo thì sao",
            "notebook_id": notebook_id,
            "session_id": session_id,
        },
    )
    kinds = [e["type"] for e in _events(second)]
    assert "session" not in kinds, "không được tạo phiên mới khi đã có session_id"

    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    assert len(messages) == 4


def test_phien_khong_ton_tai(client: TestClient, notebook_id: str) -> None:
    r = client.post(
        "/api/chat/ask",
        json={
            "question": "gì đó",
            "notebook_id": notebook_id,
            "session_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    err = next(e for e in _events(r) if e["type"] == "error")
    assert err["code"] == "SESSION_NOT_FOUND"


# ══════════════════════════════════════════════════════
# Hỏi ra ngoài — US-032
# ══════════════════════════════════════════════════════


def test_privacy_mode_doi_xac_nhan_them_mot_lan(
    client: TestClient, notebook_id: str, monkeypatch
) -> None:
    """US-032 AC-4 — thao tác này gửi câu hỏi ra dịch vụ bên ngoài."""
    monkeypatch.setattr(settings, "default_mode", "privacy")
    r = client.post(
        "/api/chat/ask-external",
        json={"question": "giá vàng hôm nay", "notebook_id": notebook_id, "confirmed": False},
    )
    events = _events(r)
    assert events[0]["type"] == "confirm_required"
    assert not any(e["type"] == "token" for e in events), "chưa xác nhận mà đã gọi ra ngoài"


def test_hoi_ra_ngoai_khi_da_xac_nhan(client: TestClient, notebook_id: str) -> None:
    r = client.post(
        "/api/chat/ask-external",
        json={"question": "thủ đô nước Pháp", "notebook_id": notebook_id, "confirmed": True},
    )
    events = _events(r)
    assert any(e["type"] == "warning" for e in events), "thiếu nhãn cảnh báo US-033 AC-2"
    assert not any(e["type"] == "citation" for e in events), "US-033 AC-3"
