"""Ngân sách ngữ cảnh và vệ sinh lịch sử trước khi gọi mô hình.

Hai lỗi im lặng mà không test nào trước đây bắt được:

* Prompt tràn cửa sổ ngữ cảnh — Ollama cắt từ đầu, mất system prompt, và mô
  hình trích dẫn marker cho đoạn nó chưa từng thấy.
* Marker `[n]` của lượt trước lọt vào lịch sử — "hợp lệ" về số nhưng trỏ sang
  một đoạn khác ở lượt này.
"""

from __future__ import annotations

import uuid

from app.repositories.retrieval import Candidate
from app.services import prompt as P
from app.services.answer import _lam_sach_lich_su, _vua_ngan_sach
from app.services.retrieval import ScoredChunk
from app.settings import settings


def _chunk(i: int, chars: int) -> ScoredChunk:
    c = Candidate(
        chunk_id=i, source_id=uuid.uuid4(), content="x" * chars, page_no=1,
        heading_path=None, char_start=0, char_end=chars, score=1.0 - i * 0.01,
    )
    return ScoredChunk(candidate=c, rrf_score=1.0 - i * 0.01)


def test_cat_duoi_khi_vuot_ngan_sach(monkeypatch):
    monkeypatch.setattr(settings, "llm_context_tokens", 2048)
    monkeypatch.setattr(settings, "llm_max_tokens", 512)
    monkeypatch.setattr(settings, "llm_chars_per_token", 2.0)
    # Mỗi đoạn ~1000 token + 32; ngân sách 1536 trừ phần cố định → chỉ vừa 1.
    chunks = [_chunk(i, 2000) for i in range(8)]

    giu, bo = _vua_ngan_sach(chunks, system="s" * 100, question="q", history=None)

    assert [c.candidate.chunk_id for c in giu] == [0]
    assert bo == 7


def test_luon_giu_it_nhat_mot_doan(monkeypatch):
    monkeypatch.setattr(settings, "llm_context_tokens", 2048)
    monkeypatch.setattr(settings, "llm_max_tokens", 1024)
    chunks = [_chunk(0, 50_000)]

    giu, bo = _vua_ngan_sach(chunks, system="", question="q", history=None)

    assert len(giu) == 1 and bo == 0


def test_khong_cat_khi_vua(monkeypatch):
    monkeypatch.setattr(settings, "llm_context_tokens", 8192)
    monkeypatch.setattr(settings, "llm_max_tokens", 1024)
    # 8 × (600 + 32) + system 1000 + 64 ≈ 6100 < 8192 − 1024.
    chunks = [_chunk(i, 1200) for i in range(8)]

    giu, bo = _vua_ngan_sach(chunks, system="s" * 2000, question="q", history=None)

    assert len(giu) == 8 and bo == 0


def test_lich_su_tinh_vao_ngan_sach(monkeypatch):
    monkeypatch.setattr(settings, "llm_context_tokens", 4096)
    monkeypatch.setattr(settings, "llm_max_tokens", 512)
    chunks = [_chunk(i, 1500) for i in range(6)]
    history = [{"role": "user", "content": "h" * 4000}]

    _, khong_lich_su = _vua_ngan_sach(chunks, "", "q", None)
    _, co_lich_su = _vua_ngan_sach(chunks, "", "q", history)

    assert co_lich_su > khong_lich_su


def test_xoa_marker_cau_tra_loi_cu():
    history = [
        {"role": "user", "content": "Học phí bao nhiêu? [1]"},
        {"role": "assistant", "content": "Mức thu 12 triệu [1], nộp trong 30 ngày [2]."},
    ]

    sach = _lam_sach_lich_su(history)

    assert sach[0]["content"] == "Học phí bao nhiêu? [1]", "câu người dùng giữ nguyên"
    assert sach[1]["content"] == "Mức thu 12 triệu, nộp trong 30 ngày."
    assert P.used_markers(sach[1]["content"]) == []


def test_lich_su_rong_giu_nguyen():
    assert _lam_sach_lich_su(None) is None
    assert _lam_sach_lich_su([]) == []
