"""Adapter nhúng — hợp đồng cổng và hành vi của bản giả.

Bản giả là thứ cho phép test toàn bộ logic truy xuất trên laptop trong vài
giây. Nếu nó sai thì mọi test dựa vào nó đều vô nghĩa, nên nó xứng đáng có
test riêng.
"""

from __future__ import annotations

import math

import pytest

from app.adapters.embedding.fake import FakeEmbeddingProvider
from app.ports.embedding import EmbeddingProvider


@pytest.fixture
def emb() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dim=1024)


def test_thoa_man_hop_dong_cong(emb: FakeEmbeddingProvider) -> None:
    assert isinstance(emb, EmbeddingProvider)
    assert emb.dim == 1024
    assert emb.name


def test_tat_dinh(emb: FakeEmbeddingProvider) -> None:
    """Cùng đầu vào phải cho cùng vector, kể cả qua nhiều thực thể khác nhau.

    Không tất định thì mỗi lần chạy lại cho kết quả truy xuất khác, và test
    nào dựa vào thứ hạng đều nhấp nháy.
    """
    text = "Chương trình đào tạo được xây dựng theo chuẩn đầu ra"
    a = emb.embed_query(text)
    b = emb.embed_query(text)
    c = FakeEmbeddingProvider(dim=1024).embed_query(text)
    assert a == b == c


def test_da_chuan_hoa_L2(emb: FakeEmbeddingProvider) -> None:
    """Chuẩn hoá là phần của hợp đồng cổng, không phải chi tiết cài đặt.

    Truy vấn dùng toán tử cosine của pgvector; vector chưa chuẩn hoá vẫn tính
    ra điểm nhưng sai lệch, và không có gì báo lỗi.
    """
    for text in ["ngắn", "Điều 5. Phạm vi áp dụng của quy chế", "a b c d e f g"]:
        v = emb.embed_query(text)
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-9)


def test_dung_so_chieu(emb: FakeEmbeddingProvider) -> None:
    assert len(emb.embed_query("thử")) == 1024
    vectors = emb.embed_documents(["một", "hai", "ba"])
    assert len(vectors) == 3
    assert all(len(v) == 1024 for v in vectors)


def test_van_ban_rong_khong_sinh_vector_khong(emb: FakeEmbeddingProvider) -> None:
    """pgvector tính cosine với vector 0 sẽ ra NaN, làm hỏng thứ hạng im lặng."""
    for text in ["", "   ", "!!!", "\n\n"]:
        v = emb.embed_query(text)
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-9)


def test_danh_sach_rong(emb: FakeEmbeddingProvider) -> None:
    assert emb.embed_documents([]) == []


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_trung_lap_tu_vung_cho_cosine_cao_hon(emb: FakeEmbeddingProvider) -> None:
    """Đây là lý do dùng thủ thuật băm thay vì sinh ngẫu nhiên.

    Vector ngẫu nhiên thuần làm mọi test truy xuất trở nên vô nghĩa. Có tín
    hiệu từ vựng thật thì một test kiểu "chunk đúng phải xếp trên chunk sai"
    mới khẳng định được điều gì.
    """
    query = emb.embed_query("chương trình đào tạo trình độ đại học")
    gan = emb.embed_query("chương trình đào tạo được xây dựng theo chuẩn đầu ra")
    xa = emb.embed_query("nước thải công nghiệp phải xử lý trước khi xả")

    assert _cosine(query, gan) > _cosine(query, xa)


def test_cosine_voi_chinh_no_bang_mot(emb: FakeEmbeddingProvider) -> None:
    v = emb.embed_query("Điều 3. Chương trình đào tạo")
    assert math.isclose(_cosine(v, v), 1.0, rel_tol=1e-9)


def test_khong_phan_biet_hoa_thuong(emb: FakeEmbeddingProvider) -> None:
    a = emb.embed_query("Quy Chế Đào Tạo")
    b = emb.embed_query("quy chế đào tạo")
    assert a == b


def test_dim_qua_nho_bi_tu_choi() -> None:
    with pytest.raises(ValueError, match="dim"):
        FakeEmbeddingProvider(dim=4)
