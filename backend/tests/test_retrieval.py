"""Truy xuất lai và RRF — US-010.

Chia làm hai phần: RRF là hàm thuần nên test không cần cơ sở dữ liệu; hai
nhánh truy xuất thì cần, và được đánh dấu `db`.

Hai bất biến được bảo vệ ở đây:

* **INV-3** — đường truy vấn tài liệu không bao giờ chạm `external_answer_cache`.
* **INV-4** — lọc theo chủ sở hữu ngay ở tầng SQL.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select

from app.adapters.embedding.fake import FakeEmbeddingProvider
from app.models.base import session_scope
from app.models.knowledge import Notebook, Source, User
from app.repositories import retrieval as repo
from app.repositories.retrieval import Candidate
from app.services.ingest import ingest_file_sync
from app.services.retrieval import reciprocal_rank_fusion, retrieve
from app.settings import settings
from app.text.segment import build_tsquery_parts

# ══════════════════════════════════════════════════════
# RRF — hàm thuần, không cần cơ sở dữ liệu
# ══════════════════════════════════════════════════════


def _cand(chunk_id: int) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        source_id=uuid.uuid4(),
        content=f"đoạn {chunk_id}",
        page_no=1,
        heading_path=None,
        char_start=0,
        char_end=10,
        score=0.0,
    )


def test_rrf_dung_cong_thuc() -> None:
    """score(d) = Σ 1/(k + rank). Kiểm bằng số cụ thể, không kiểm bằng thứ tự."""
    fused = reciprocal_rank_fusion({"a": [_cand(1), _cand(2)]}, k=60)
    assert fused[0].rrf_score == pytest.approx(1 / 61)
    assert fused[1].rrf_score == pytest.approx(1 / 62)


def test_rrf_cong_don_khi_xuat_hien_o_nhieu_nhanh() -> None:
    """Đồng thuận giữa hai tín hiệu độc lập được thưởng — lý do dùng RRF."""
    fused = reciprocal_rank_fusion(
        {"vector": [_cand(1), _cand(2)], "fulltext": [_cand(2), _cand(1)]}, k=60
    )
    assert len(fused) == 2, "phải khử trùng lặp theo chunk_id"
    for s in fused:
        assert s.rrf_score == pytest.approx(1 / 61 + 1 / 62)


def test_rrf_dong_thuan_thang_diem_cao_o_mot_nhanh() -> None:
    """Chunk hạng 2 ở CẢ HAI nhánh thắng chunk hạng 1 ở một nhánh duy nhất."""
    fused = reciprocal_rank_fusion(
        {
            "vector": [_cand(9), _cand(5)],
            "fulltext": [_cand(7), _cand(5)],
        },
        k=60,
    )
    assert fused[0].chunk_id == 5


def test_rrf_ghi_lai_thu_hang_tung_nhanh() -> None:
    fused = reciprocal_rank_fusion(
        {"vector": [_cand(1), _cand(2)], "fulltext": [_cand(2)]}, k=60
    )
    by_id = {s.chunk_id: s for s in fused}
    assert by_id[2].ranks == {"vector": 2, "fulltext": 1}
    assert by_id[1].ranks == {"vector": 1}


def test_rrf_pha_hoa_tat_dinh() -> None:
    """Thứ hạng nhấp nháy làm kết quả đánh giá không tái lập được."""
    ranking = {"a": [_cand(3), _cand(1), _cand(2)], "b": [_cand(1), _cand(3), _cand(2)]}
    first = [s.chunk_id for s in reciprocal_rank_fusion(ranking, k=60)]
    for _ in range(5):
        assert [s.chunk_id for s in reciprocal_rank_fusion(ranking, k=60)] == first


def test_rrf_k_lon_lam_phang_chenh_lech() -> None:
    nho = reciprocal_rank_fusion({"a": [_cand(1), _cand(2)]}, k=1)
    lon = reciprocal_rank_fusion({"a": [_cand(1), _cand(2)]}, k=1000)
    assert (nho[0].rrf_score - nho[1].rrf_score) > (lon[0].rrf_score - lon[1].rrf_score)


def test_rrf_danh_sach_rong() -> None:
    assert reciprocal_rank_fusion({}) == []
    assert reciprocal_rank_fusion({"a": []}) == []


# ══════════════════════════════════════════════════════
# Dựng tsquery
# ══════════════════════════════════════════════════════


def test_loai_tu_dung_khoi_truy_van() -> None:
    """Giữ "được", "theo", "nào" thì gần như mọi chunk đều khớp khi nối bằng OR."""
    parts = build_tsquery_parts("chương trình đào tạo được xây dựng theo cái gì")
    contents = [c for _, c in parts]
    assert not any(c in {"được", "theo", "gì", "cái"} for c in contents), contents
    assert contents, "không được lọc sạch mọi thứ"


def test_cau_hoi_toan_tu_dung_van_con_truy_van() -> None:
    """Thà tìm bằng từ dừng còn hơn không tìm gì — nhánh vector gánh phần còn lại."""
    assert build_tsquery_parts("cái này là gì")


def test_ma_hieu_van_ban_khong_bi_loai() -> None:
    """US-010 AC-3 — ca mà vector search thuần thường thất bại."""
    contents = " ".join(c for _, c in build_tsquery_parts("TCVN 5945:2005 quy định gì"))
    assert "5945" in contents


# ══════════════════════════════════════════════════════
# INV-3 — cache không bao giờ nằm trên đường truy xuất
# ══════════════════════════════════════════════════════


def test_INV3_truy_van_khong_cham_bang_cache() -> None:
    """Kiểm tra **cấu trúc** câu SQL, không kiểm tra kết quả.

    Vi phạm bất biến này không làm test nào đỏ theo cách thông thường: hệ thống
    vẫn chạy, chỉ là dần dần nó trích dẫn chính nội dung nó tự bịa ra, và toàn
    bộ giá trị của tính năng trích dẫn sụp đổ (SPEC.md §J.6).
    """
    from sqlalchemy import and_, func, select

    from app.models.knowledge import SourceChunk

    nb, owner = uuid.uuid4(), uuid.uuid4()

    vector_stmt = repo._owned(
        select(*repo._COLUMNS)
        .where(and_(*repo._base(nb, owner, None)))
        .order_by(SourceChunk.embedding.cosine_distance([0.0] * 1024)),
        owner,
    )
    ts = func.plainto_tsquery("vi", "thử")
    fulltext_stmt = repo._owned(
        select(*repo._COLUMNS)
        .where(and_(*repo._base(nb, owner, None)))
        .where(SourceChunk.tsv.op("@@")(ts)),
        owner,
    )

    for stmt in (vector_stmt, fulltext_stmt):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
        assert "external_answer_cache" not in sql
        assert "external_call_log" not in sql


# ══════════════════════════════════════════════════════
# Hai nhánh — cần cơ sở dữ liệu
# ══════════════════════════════════════════════════════

# Fixture `clean` chạm Postgres cho mọi test trong module.
pytestmark = pytest.mark.db

OWNER_A = "retrieval-a@documind.local"
OWNER_B = "retrieval-b@documind.local"
NOTEBOOK = "retrieval-test"

DOC_A = """Chương I. Quy định chung

Điều 1. Phạm vi điều chỉnh
Quy chế này quy định về tổ chức và quản lý đào tạo trình độ đại học.

Điều 2. Tiêu chuẩn nước thải
Nước thải sau xử lý phải đạt quy chuẩn TCVN 5945:2005 loại B trước khi
xả ra môi trường tiếp nhận.

Điều 3. Chương trình đào tạo
Chương trình đào tạo được xây dựng theo chuẩn đầu ra đã công bố công khai.
"""

DOC_B = """Điều 1. Học phí
Mức thu học phí được xác định theo từng năm học và công bố trước kỳ tuyển sinh.
"""


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        with session_scope() as s:
            s.execute(delete(User).where(User.email.in_([OWNER_A, OWNER_B])))

    wipe()
    yield
    wipe()


@pytest.fixture
def emb() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dim=1024)


@pytest.fixture
def seeded(tmp_path, emb):
    """Nạp DOC_A cho người dùng A và DOC_B cho người dùng B."""
    out = {}
    for owner, body, name in ((OWNER_A, DOC_A, "a.txt"), (OWNER_B, DOC_B, "b.txt")):
        p = tmp_path / name
        p.write_text(body, encoding="utf-8")
        with session_scope() as s:
            ingest_file_sync(s, p, notebook_title=NOTEBOOK, embedder=emb, owner_email=owner)
    with session_scope() as s:
        for owner in (OWNER_A, OWNER_B):
            user = s.scalar(select(User).where(User.email == owner))
            nb = s.scalar(select(Notebook).where(Notebook.user_id == user.id))
            out[owner] = (user.id, nb.id)
    return out


@pytest.mark.db
def test_hai_nhanh_cung_chay_va_hop_nhat(seeded, emb) -> None:
    user_id, nb_id = seeded[OWNER_A]
    with session_scope() as s:
        r = retrieve(
            s, "chương trình đào tạo", notebook_id=nb_id, embedder=emb, owner_id=user_id
        )
    assert r.branches == ["fulltext", "vector"]
    assert r.vector_count > 0
    assert r.fulltext_count > 0
    assert len(r) > 0


@pytest.mark.db
def test_doan_dung_len_dau(seeded, emb) -> None:
    user_id, nb_id = seeded[OWNER_A]
    with session_scope() as s:
        r = retrieve(
            s,
            "chương trình đào tạo xây dựng theo chuẩn đầu ra",
            notebook_id=nb_id,
            embedder=emb,
            owner_id=user_id,
        )
    assert "Chương trình đào tạo" in r.chunks[0].candidate.content


@pytest.mark.db
def test_ma_hieu_hiem_tim_duoc_bang_nhanh_tu_khoa(seeded, emb) -> None:
    """US-010 AC-3 — trường hợp vector search thuần thường thất bại."""
    user_id, nb_id = seeded[OWNER_A]
    with session_scope() as s:
        hits = repo.search_fulltext(
            s, "TCVN 5945:2005", notebook_id=nb_id, owner_id=user_id
        )
    assert hits
    assert "5945" in hits[0].content


@pytest.mark.db
def test_INV4_khong_lay_duoc_du_lieu_cua_nguoi_khac(seeded, emb) -> None:
    """Lọc theo chủ sở hữu ở tầng SQL, không lọc sau khi đã lấy ra.

    Truyền notebook của B nhưng danh tính của A: phải trả về rỗng, không được
    trả về dữ liệu của B.
    """
    user_a, _ = seeded[OWNER_A]
    _, nb_b = seeded[OWNER_B]

    with session_scope() as s:
        r = retrieve(s, "học phí", notebook_id=nb_b, embedder=emb, owner_id=user_a)
        assert len(r) == 0

        # Cùng notebook đó, đúng chủ sở hữu thì có dữ liệu — chứng minh phép
        # thử trên thất bại vì quyền, không phải vì notebook rỗng.
        user_b, _ = seeded[OWNER_B]
        r2 = retrieve(s, "học phí", notebook_id=nb_b, embedder=emb, owner_id=user_b)
        assert len(r2) > 0


@pytest.mark.db
def test_loc_pham_vi_nguon_o_tang_sql(seeded, emb, tmp_path) -> None:
    """US-038 AC-2 — lọc bằng source_id ngay trong truy vấn."""
    user_id, nb_id = seeded[OWNER_A]
    extra = tmp_path / "them.txt"
    extra.write_text(DOC_B, encoding="utf-8")
    with session_scope() as s:
        ingest_file_sync(s, extra, notebook_title=NOTEBOOK, embedder=emb, owner_email=OWNER_A)

    with session_scope() as s:
        sources = s.scalars(select(Source).where(Source.notebook_id == nb_id)).all()
        assert len(sources) == 2
        only = [sources[0].id]

        r = retrieve(
            s,
            "quy định",
            notebook_id=nb_id,
            embedder=emb,
            owner_id=user_id,
            source_ids=only,
        )
        assert all(sc.candidate.source_id == only[0] for sc in r.chunks)


@pytest.mark.db
def test_nguon_tat_in_scope_khong_duoc_truy_xuat(seeded, emb, tmp_path) -> None:
    """US-038 AC-1 — công tắc `in_scope` ở cột nguồn phải đổi câu trả lời.

    Không truyền `source_ids` (đường mà giao diện đang dùng) thì phạm vi mặc
    định là *các nguồn còn bật*, không phải *mọi nguồn*.
    """
    user_id, nb_id = seeded[OWNER_A]
    extra = tmp_path / "them.txt"
    extra.write_text(DOC_B, encoding="utf-8")
    with session_scope() as s:
        ingest_file_sync(s, extra, notebook_title=NOTEBOOK, embedder=emb, owner_email=OWNER_A)

    with session_scope() as s:
        sources = s.scalars(select(Source).where(Source.notebook_id == nb_id)).all()
        tat = sources[0]
        bat = sources[1]
        tat.in_scope = False
        s.flush()

        r = retrieve(s, "quy định học phí", notebook_id=nb_id, embedder=emb, owner_id=user_id)
        assert r.chunks, "vẫn phải tìm được trong nguồn còn bật"
        assert all(sc.candidate.source_id == bat.id for sc in r.chunks)

        # Chỉ định tường minh thì vẫn đọc được nguồn đã tắt — đó là quyền của
        # chỗ gọi, không phải của công tắc.
        r2 = retrieve(
            s, "quy định", notebook_id=nb_id, embedder=emb, owner_id=user_id,
            source_ids=[tat.id],
        )
        assert all(sc.candidate.source_id == tat.id for sc in r2.chunks)


# ══════════════════════════════════════════════════════
# Cờ cấu hình = ba dòng đầu bảng ablation US-046
# ══════════════════════════════════════════════════════


@pytest.mark.db
@pytest.mark.parametrize(
    ("vector_on", "bm25_on", "expected"),
    [
        (True, False, ["vector"]),      # cấu hình A
        (False, True, ["fulltext"]),    # cấu hình B
        (True, True, ["fulltext", "vector"]),  # cấu hình C
    ],
)
def test_bat_tat_nhanh_bang_cau_hinh(
    seeded, emb, monkeypatch, vector_on, bm25_on, expected
) -> None:
    """US-046 AC-1 — đổi cấu hình phải đổi hành vi mà không sửa dòng mã nào."""
    monkeypatch.setattr(settings, "retrieval_vector_enabled", vector_on)
    monkeypatch.setattr(settings, "retrieval_bm25_enabled", bm25_on)

    user_id, nb_id = seeded[OWNER_A]
    with session_scope() as s:
        r = retrieve(s, "đào tạo", notebook_id=nb_id, embedder=emb, owner_id=user_id)
    assert r.branches == expected


@pytest.mark.db
def test_tat_ca_hai_nhanh_thi_bao_loi(seeded, emb, monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_vector_enabled", False)
    monkeypatch.setattr(settings, "retrieval_bm25_enabled", False)

    user_id, nb_id = seeded[OWNER_A]
    with session_scope() as s, pytest.raises(RuntimeError, match="đều tắt"):
        retrieve(s, "đào tạo", notebook_id=nb_id, embedder=emb, owner_id=user_id)
