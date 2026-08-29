"""Số liệu vận hành — US-041.

Hai thứ đáng test ở đây, và cả hai đều là loại lỗi âm thầm:

- **Phạm vi.** Trang thống kê đếm nhầm dữ liệu của người khác thì không có gì
  đỏ lên, chỉ là con số hơi lớn hơn sự thật (INV-4).
- **Quy ước đặt tên adapter.** Việc tách Privacy Mode với Fast Mode dựa vào tiền
  tố `local:` trong `model_used`. Một adapter mới đặt tên khác đi sẽ bị xếp nhầm
  chế độ, và bảng độ trễ trong báo cáo sai mà không ai biết.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete

from app.adapters.llm.fake import FakeLLMProvider
from app.adapters.llm.gemini import GeminiLLMProvider
from app.adapters.llm.local import LocalLLMProvider
from app.adapters.llm.ollama_cloud import OllamaCloudLLMProvider
from app.models.base import session_scope
from app.models.chat import ChatMessage, ChatSession, ExternalCallLog
from app.models.knowledge import User
from app.repositories import knowledge as repo
from app.services.stats import TIEN_TO_CUC_BO, tinh_thong_ke

pytestmark = pytest.mark.db

TOI = "stats-toi@documind.local"
NGUOI_KHAC = "stats-khac@documind.local"


@pytest.fixture(autouse=True)
def clean_db():
    def wipe() -> None:
        with session_scope() as s:
            s.execute(delete(User).where(User.email.in_([TOI, NGUOI_KHAC])))

    wipe()
    yield
    wipe()


def _du_lieu(s, email: str, *, luot: list[tuple[str, str, int]]) -> uuid.UUID:
    """Dựng một người dùng có notebook và một phiên chat.

    `luot` là danh sách `(model_used, answer_kind, latency_ms)`.
    """
    user = repo.get_or_create_user(s, email)
    nb = repo.get_or_create_notebook(s, user, "so-tay")
    phien = ChatSession(notebook_id=nb.id, user_id=user.id, title="phiên thử")
    s.add(phien)
    s.flush()

    for model, kind, ms in luot:
        s.add(ChatMessage(session_id=phien.id, role="user", content="câu hỏi"))
        s.add(
            ChatMessage(
                session_id=phien.id,
                role="assistant",
                content="câu trả lời",
                answer_kind=kind,
                model_used=model,
                latency_ms=ms,
            )
        )
    s.flush()
    return user.id


# ═══════════════════════════════════════════════════════
# Quy ước đặt tên adapter
# ═══════════════════════════════════════════════════════


def test_adapter_cuc_bo_deu_mang_tien_to_local():
    """Nếu test này đỏ, bảng độ trễ ở US-041 đang xếp nhầm chế độ."""
    assert LocalLLMProvider(model="m", base_url="http://x/v1").name.startswith(
        TIEN_TO_CUC_BO
    )


def test_adapter_ngoai_khong_mang_tien_to_local():
    ngoai = [
        OllamaCloudLLMProvider(model="m", api_key="k").name,
        GeminiLLMProvider(api_key="k", model="m").name,
    ]
    for ten in ngoai:
        assert not ten.startswith(TIEN_TO_CUC_BO), ten


def test_moi_adapter_gui_du_lieu_ra_ngoai_deu_bi_xep_vao_fast():
    """Cùng một sự thật ghi ở hai chỗ — hai chỗ đó phải nói giống nhau.

    `is_local` quyết định nhãn quyền riêng tư trên giao diện; tiền tố `local:`
    quyết định cột nào trong bảng độ trễ. Lệch nhau thì một trong hai đang nói
    dối, và không có test nào khác bắt được.
    """
    for provider in (
        OllamaCloudLLMProvider(model="m", api_key="k"),
        GeminiLLMProvider(api_key="k", model="m"),
    ):
        assert provider.is_local is False
        assert not provider.name.startswith(TIEN_TO_CUC_BO)

    for provider in (LocalLLMProvider(model="m", base_url="http://x/v1"),):
        assert provider.is_local is True
        assert provider.name.startswith(TIEN_TO_CUC_BO)

    # `fake-echo` chạy trong tiến trình nên nó là cục bộ, nhưng nó không bao giờ
    # xuất hiện trong `model_used` của dữ liệu thật, nên không cần tiền tố.
    assert FakeLLMProvider().is_local is True


# ═══════════════════════════════════════════════════════
# Số liệu
# ═══════════════════════════════════════════════════════


def test_do_tre_tach_dung_hai_che_do():
    with session_scope() as s:
        uid = _du_lieu(
            s,
            TOI,
            luot=[
                ("local:qwen3-8b-q4", "grounded", 4000),
                ("local:qwen3-8b-q4", "grounded", 6000),
                ("ollama-cloud:gemma4:31b", "grounded", 1000),
            ],
        )
        tk = tinh_thong_ke(s, uid)

    assert tk.do_tre_privacy.so_luot == 2
    assert tk.do_tre_privacy.trung_binh == pytest.approx(5000.0)
    assert tk.do_tre_fast.so_luot == 1
    assert tk.do_tre_fast.trung_binh == pytest.approx(1000.0)


def test_cau_tu_choi_khong_lam_lech_do_tre():
    """Đường từ chối KHÔNG gọi mô hình nào — `model_used` rỗng.

    Đưa nó vào trung bình sẽ nói sai về chi phí sinh một câu trả lời, và đó
    chính là con số đi vào báo cáo.
    """
    with session_scope() as s:
        uid = _du_lieu(
            s,
            TOI,
            luot=[("local:qwen3-8b-q4", "grounded", 5000), ("", "no_answer", 20)],
        )
        tk = tinh_thong_ke(s, uid)

    assert tk.do_tre_privacy.so_luot == 1
    assert tk.do_tre_privacy.trung_binh == pytest.approx(5000.0)
    # Nhưng vẫn được đếm trong phân bố loại câu trả lời.
    assert tk.phan_bo_answer_kind["no_answer"] == 1


def test_phan_bo_answer_kind():
    with session_scope() as s:
        uid = _du_lieu(
            s,
            TOI,
            luot=[
                ("local:m", "grounded", 100),
                ("local:m", "grounded", 100),
                ("gemini:m", "external", 100),
                ("", "no_answer", 10),
            ],
        )
        tk = tinh_thong_ke(s, uid)

    assert tk.phan_bo_answer_kind == {"grounded": 2, "external": 1, "no_answer": 1}
    assert tk.tong_cau_tra_loi == 4


def test_ty_le_cache_hit():
    with session_scope() as s:
        uid = _du_lieu(s, TOI, luot=[])
        for tu_cache in (True, True, True, False):
            s.add(ExternalCallLog(user_id=uid, from_cache=tu_cache))
        s.flush()
        tk = tinh_thong_ke(s, uid)

    assert tk.so_luot_goi_ngoai == 1
    assert tk.so_luot_tu_cache == 3
    assert tk.ty_le_cache_hit == pytest.approx(0.75)


def test_khong_co_du_lieu_thi_khong_chia_cho_khong():
    with session_scope() as s:
        uid = _du_lieu(s, TOI, luot=[])
        tk = tinh_thong_ke(s, uid)

    assert tk.ty_le_cache_hit == 0.0
    assert tk.do_tre_privacy.p95 == 0.0
    assert tk.phan_bo_answer_kind == {}


def test_khong_dem_du_lieu_cua_nguoi_khac():
    """INV-4 — đây là loại lỗi không có triệu chứng nào ngoài con số hơi to."""
    with session_scope() as s:
        cua_toi = _du_lieu(s, TOI, luot=[("local:m", "grounded", 100)])
        _du_lieu(
            s,
            NGUOI_KHAC,
            luot=[("local:m", "grounded", 100), ("local:m", "grounded", 100)],
        )
        tk = tinh_thong_ke(s, cua_toi)

    assert tk.so_notebook == 1
    assert tk.phan_bo_answer_kind == {"grounded": 1}
    assert tk.do_tre_privacy.so_luot == 1


def test_api_doi_dang_nhap():
    """Số liệu vận hành không phải thông tin công khai."""
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).get("/api/stats").status_code == 401
