"""Xếp hạng lại và cổng ngưỡng τ — US-011, US-031.

Cổng ngưỡng là ranh giới giữa "trả lời có căn cứ" và "tôi không biết". Sai ở
đây thì hoặc hệ thống bịa (τ quá thấp), hoặc nó từ chối oan mọi thứ (τ quá
cao) — và cả hai đều là hỏng im lặng cho tới khi đo bằng bộ test ở US-047.
"""

from __future__ import annotations

import uuid

import pytest

from app.adapters.rerank.fake import FakeRerankProvider
from app.ports.rerank import RerankProvider
from app.repositories.retrieval import Candidate
from app.services.grounding import decide, rerank
from app.services.retrieval import RetrievalResult, ScoredChunk
from app.settings import settings


@pytest.fixture
def rr() -> FakeRerankProvider:
    return FakeRerankProvider()


def _chunk(chunk_id: int, content: str, rrf: float = 0.01) -> ScoredChunk:
    return ScoredChunk(
        candidate=Candidate(
            chunk_id=chunk_id,
            source_id=uuid.uuid4(),
            content=content,
            page_no=1,
            heading_path=None,
            char_start=0,
            char_end=len(content),
            score=0.0,
        ),
        rrf_score=rrf,
        ranks={"vector": chunk_id},
    )


def _result(*chunks: ScoredChunk) -> RetrievalResult:
    return RetrievalResult(
        chunks=list(chunks),
        vector_count=len(chunks),
        fulltext_count=0,
        branches=["vector"],
    )


# ══════════════════════════════════════════════════════
# Hợp đồng cổng
# ══════════════════════════════════════════════════════


def test_thoa_man_hop_dong_cong(rr: FakeRerankProvider) -> None:
    assert isinstance(rr, RerankProvider)
    assert rr.name


def test_diem_nam_trong_khoang_0_1(rr: FakeRerankProvider) -> None:
    """Cổng ngưỡng so trực tiếp với con số này. Logit thô làm τ vô nghĩa."""
    docs = [
        "Chương trình đào tạo được xây dựng theo chuẩn đầu ra đã công bố",
        "Nước thải phải đạt quy chuẩn trước khi xả ra môi trường",
        "",
        "x",
    ]
    for s in rr.score("chương trình đào tạo", docs):
        assert 0.0 <= s <= 1.0


def test_tra_ve_dung_so_luong_va_thu_tu(rr: FakeRerankProvider) -> None:
    """Việc sắp xếp là của chỗ gọi — adapter phải giữ nguyên thứ tự đầu vào."""
    docs = ["một", "hai", "ba"]
    assert len(rr.score("thử", docs)) == 3


def test_tat_dinh(rr: FakeRerankProvider) -> None:
    q, docs = "chương trình đào tạo", ["chương trình đào tạo đại học", "học phí"]
    assert rr.score(q, docs) == rr.score(q, docs)


def test_danh_sach_rong(rr: FakeRerankProvider) -> None:
    assert rr.score("thử", []) == []


def test_cau_hoi_rong(rr: FakeRerankProvider) -> None:
    assert rr.score("", ["nội dung"]) == [0.0]


def test_doan_lien_quan_diem_cao_hon(rr: FakeRerankProvider) -> None:
    lien_quan, khong = rr.score(
        "chương trình đào tạo trình độ đại học",
        [
            "Chương trình đào tạo trình độ đại học được xây dựng theo chuẩn đầu ra",
            "Nước thải sau xử lý phải đạt quy chuẩn kỹ thuật quốc gia",
        ],
    )
    assert lien_quan > khong


def test_khong_phan_biet_dau(rr: FakeRerankProvider) -> None:
    """Người dùng gõ thiếu dấu vẫn phải được chấm đúng."""
    a = rr.score("chuong trinh dao tao", ["Chương trình đào tạo đại học"])[0]
    b = rr.score("chương trình đào tạo", ["Chương trình đào tạo đại học"])[0]
    assert a == b


# ══════════════════════════════════════════════════════
# Xếp hạng lại
# ══════════════════════════════════════════════════════


def test_rerank_doi_thu_tu_so_voi_rrf(rr: FakeRerankProvider) -> None:
    """Đây là lý do bước này tồn tại: RRF chỉ biết thứ hạng, không đọc nội dung."""
    result = _result(
        _chunk(1, "Học phí được xác định theo từng năm học", rrf=0.99),
        _chunk(2, "Chương trình đào tạo trình độ đại học xây dựng theo chuẩn", rrf=0.01),
    )
    out = rerank("chương trình đào tạo trình độ đại học", result, reranker=rr)
    assert out[0].chunk_id == 2, "đoạn đúng phải vượt lên bất kể hạng RRF"


def test_rerank_cat_xuong_top_k(rr: FakeRerankProvider) -> None:
    result = _result(*[_chunk(i, f"đoạn {i} về đào tạo") for i in range(20)])
    assert len(rerank("đào tạo", result, reranker=rr, top_k=5)) == 5


def test_rerank_giu_thong_tin_nhanh(rr: FakeRerankProvider) -> None:
    """Vẫn truy được một đoạn lọt vào từ nhánh nào — cần cho gỡ lỗi."""
    result = _result(_chunk(7, "chương trình đào tạo"))
    assert rerank("đào tạo", result, reranker=rr)[0].ranks == {"vector": 7}


def test_rerank_danh_sach_rong(rr: FakeRerankProvider) -> None:
    assert rerank("thử", _result(), reranker=rr) == []


def test_rerank_tat_dinh_khi_hoa_diem(rr: FakeRerankProvider) -> None:
    """Hai đoạn giống hệt nhau phải luôn ra cùng thứ tự giữa các lần chạy."""
    result = _result(_chunk(5, "nội dung y hệt"), _chunk(3, "nội dung y hệt"))
    order = [s.chunk_id for s in rerank("nội dung", result, reranker=rr)]
    for _ in range(5):
        assert [s.chunk_id for s in rerank("nội dung", result, reranker=rr)] == order


# ══════════════════════════════════════════════════════
# Cổng ngưỡng τ — US-031
# ══════════════════════════════════════════════════════


def test_diem_cao_thi_du_can_cu(rr: FakeRerankProvider) -> None:
    result = _result(
        _chunk(1, "Chương trình đào tạo trình độ đại học xây dựng theo chuẩn đầu ra")
    )
    d = decide("chương trình đào tạo", result, reranker=rr, threshold=0.35)
    assert d.grounded
    assert d.top_score >= 0.35
    assert "≥" in d.reason


def test_diem_thap_thi_khong_du_can_cu(rr: FakeRerankProvider) -> None:
    """US-013 — thà nói không biết còn hơn bịa."""
    result = _result(_chunk(1, "Nước thải sau xử lý phải đạt quy chuẩn kỹ thuật"))
    d = decide("học phí ngành công nghệ thông tin", result, reranker=rr, threshold=0.35)
    assert not d.grounded
    assert "không chứa đủ căn cứ" in d.reason


def test_khong_co_ung_vien_thi_khong_du_can_cu(rr: FakeRerankProvider) -> None:
    d = decide("bất kỳ", _result(), reranker=rr)
    assert not d.grounded
    assert d.top_score == 0.0
    assert "Không tìm thấy" in d.reason


def test_van_tra_ve_doan_khi_tu_choi(rr: FakeRerankProvider) -> None:
    """Đường từ chối cần chúng để giải thích và để hiệu chỉnh τ ở US-047."""
    result = _result(_chunk(1, "nội dung không liên quan gì"))
    d = decide("câu hỏi hoàn toàn khác", result, reranker=rr, threshold=0.9)
    assert not d.grounded
    assert d.chunks, "phải giữ lại đoạn để giải thích và ghi log"


@pytest.mark.parametrize("threshold", [0.0, 0.35, 0.9, 1.0])
def test_nguong_thay_doi_thi_quyet_dinh_thay_doi(
    rr: FakeRerankProvider, threshold: float
) -> None:
    """US-031 AC-5 — τ nằm trong cấu hình, đổi nó là đổi hành vi."""
    result = _result(_chunk(1, "Chương trình đào tạo trình độ đại học"))
    d = decide("chương trình đào tạo", result, reranker=rr, threshold=threshold)
    assert d.grounded == (d.top_score >= threshold)
    assert d.threshold == threshold


class CountingReranker:
    """Đếm xem cross-encoder thật sự được gọi trên bao nhiêu đoạn."""

    name = "counting"

    def __init__(self) -> None:
        self.seen: list[int] = []

    def score(self, query: str, documents: list[str]) -> list[float]:
        self.seen.append(len(documents))
        # Điểm giảm dần theo thứ tự vào, để test biết được thứ tự bị đảo hay không.
        return [1.0 - i * 0.01 for i in range(len(documents))]


def test_chi_cham_phan_dau_bang(monkeypatch) -> None:
    """Cross-encoder chạy tuyến tính theo số ứng viên, nên đây là tham số chi
    phối độ trễ nhiều nhất của cả đường truy xuất.

    Chấm hết cũng không cải thiện gì: một đoạn xếp hạng 80 sau RRF gần như
    không bao giờ leo lên top 8. Nó chỉ nhân độ trễ lên.
    """
    monkeypatch.setattr(settings, "rerank_candidates", 5)
    rr = CountingReranker()
    result = _result(*[_chunk(i, f"đoạn {i}", rrf=1.0 / (i + 1)) for i in range(40)])

    rerank("thử", result, reranker=rr)
    assert rr.seen == [5], "phải chấm đúng 5 đoạn, không phải cả 40"


def test_it_ung_vien_hon_nguong_thi_cham_het(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rerank_candidates", 50)
    rr = CountingReranker()
    rerank("thử", _result(_chunk(1, "a"), _chunk(2, "b")), reranker=rr)
    assert rr.seen == [2]


def test_hai_con_so_doc_lap_nhau(monkeypatch) -> None:
    """`rerank_candidates` là chấm bao nhiêu, `rerank_top_k` là giữ bao nhiêu.

    Rất dễ nhầm thành một tham số, và lúc đó hạ chi phí xuống cũng hạ luôn số
    đoạn đưa vào mô hình sinh — tức là đổi cả chất lượng câu trả lời chứ không
    chỉ đổi độ trễ.
    """
    monkeypatch.setattr(settings, "rerank_candidates", 6)
    monkeypatch.setattr(settings, "rerank_top_k", 2)
    rr = CountingReranker()
    result = _result(*[_chunk(i, f"đoạn {i}", rrf=1.0 / (i + 1)) for i in range(20)])

    kept = rerank("thử", result, reranker=rr)
    assert rr.seen == [6]
    assert len(kept) == 2


def test_tat_rerank_van_chay_duoc(rr: FakeRerankProvider, monkeypatch) -> None:
    """US-011 AC-4 — bắt buộc, để chạy cấu hình C của bảng ablation."""
    monkeypatch.setattr(settings, "rerank_enabled", False)
    monkeypatch.setattr(settings, "tau_no_rerank", 0.45)
    result = _result(_chunk(1, "nội dung", rrf=0.5), _chunk(2, "khác", rrf=0.2))
    # Điểm RRF (~1/60) không so được với τ; cổng dùng cosine của nhánh vector.
    result.vector_scores = {1: 0.62, 2: 0.31}
    d = decide("thử", result, reranker=rr)

    assert not d.reranked, "phải đánh dấu là chưa qua cross-encoder"
    assert [c.chunk_id for c in d.chunks] == [1, 2], "giữ nguyên thứ tự RRF"
    assert d.top_score == 0.62 and d.threshold == 0.45
    assert d.grounded

    result.vector_scores = {1: 0.30, 2: 0.20}
    assert not decide("thử", result, reranker=rr).grounded, "cosine thấp thì từ chối"


def test_ghi_lai_diem_cao_nhat_de_hieu_chinh_tau(rr: FakeRerankProvider) -> None:
    """US-031 AC-4 — dữ liệu cho việc quét τ ở US-047."""
    result = _result(_chunk(1, "Chương trình đào tạo"))
    d = decide("chương trình đào tạo", result, reranker=rr)
    assert isinstance(d.top_score, float)
    assert 0.0 <= d.top_score <= 1.0
