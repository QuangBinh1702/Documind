"""Nạp tài liệu đầu-cuối — tệp trên đĩa tới chunk trong cơ sở dữ liệu.

Cần hạ tầng đang chạy:

    docker compose up -d postgres redis minio minio-init
    pytest tests/test_ingest.py -v

Test quan trọng nhất là `test_INV1_dung_tren_du_lieu_da_ghi`: nó kiểm bất biến
ở **tầng lưu trữ**, bằng SQL, trên hàng đã nằm trong bảng. `test_chunker.py`
kiểm ở mức hàm; hai chỗ đó bắt được những loại lỗi khác nhau.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, text

from app.adapters.embedding.fake import FakeEmbeddingProvider
from app.adapters.extract import ExtractionError
from app.models.base import session_scope
from app.models.knowledge import Notebook, Source, SourceChunk, SourceText, User
from app.repositories import knowledge as repo
from app.services.ingest import ingest_file_sync

pytestmark = pytest.mark.db

OWNER = "pytest@documind.local"
NOTEBOOK = "pytest-notebook"

LEGAL_TEXT = """Chương I. Quy định chung

Điều 1. Phạm vi điều chỉnh
Quy chế này quy định về tổ chức và quản lý đào tạo trình độ đại học tại
Trường. Quy chế áp dụng cho các đơn vị trực thuộc và toàn thể người học.

Điều 2. Đối tượng áp dụng
Quy chế áp dụng đối với người học, giảng viên và cán bộ quản lý đào tạo.
Các đơn vị có trách nhiệm phổ biến nội dung quy chế đến toàn thể người học.

Chương II. Tổ chức đào tạo

Điều 3. Chương trình đào tạo
Chương trình đào tạo được xây dựng theo chuẩn đầu ra đã công bố công khai.
Việc điều chỉnh chương trình phải được hội đồng khoa học thông qua.
"""


@pytest.fixture(autouse=True)
def clean_db():
    """Xoá dữ liệu của tài khoản test trước và sau mỗi test.

    Xoá theo `users` là đủ vì lược đồ khai báo ON DELETE CASCADE suốt chuỗi
    notebook → source → chunk.
    """

    def wipe() -> None:
        with session_scope() as s:
            s.execute(delete(User).where(User.email == OWNER))

    wipe()
    yield
    wipe()


@pytest.fixture
def emb() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dim=1024)


@pytest.fixture
def legal_file(tmp_path: Path) -> Path:
    p = tmp_path / "quy-che.txt"
    p.write_text(LEGAL_TEXT, encoding="utf-8")
    return p


def _ingest(path: Path, emb: FakeEmbeddingProvider):
    with session_scope() as s:
        return ingest_file_sync(s, path, notebook_title=NOTEBOOK, embedder=emb, owner_email=OWNER)


# Mọi phép đếm phải giới hạn trong phạm vi tài khoản test. Đếm toàn bảng làm
# test phụ thuộc vào database rỗng — nó sẽ đỏ trên bất kỳ máy nào đã có dữ
# liệu sẵn, kể cả dữ liệu do chính CLI nạp lúc phát triển.
_OWNED_CHUNKS = (
    select(func.count())
    .select_from(SourceChunk)
    .join(Notebook, Notebook.id == SourceChunk.notebook_id)
    .join(User, User.id == Notebook.user_id)
    .where(User.email == OWNER)
)


def _own_source(s):
    """Nguồn của tài khoản test. Dùng thay cho `select(Source).limit(1)`."""
    return s.scalar(select(Source).join(Notebook).join(User).where(User.email == OWNER))


# ══════════════════════════════════════════════════════
# Bất biến
# ══════════════════════════════════════════════════════


def test_INV1_dung_tren_du_lieu_da_ghi(legal_file: Path, emb) -> None:
    """Cắt lại `full_text` bằng offset, kiểm ngay trong SQL.

    Bắt được cả lỗi phát sinh SAU bước chunking: cắt cụt khi ghi, đối chiếu
    nhầm bản ghi văn bản, hoặc một tầng nào đó lỡ chuẩn hoá lại.

    Lưu ý `substring` của SQL đánh chỉ số từ 1 còn Python từ 0 — thiếu `+ 1`
    thì lệch một ký tự mà kết quả vẫn "gần đúng".
    """
    result = _ingest(legal_file, emb)
    assert result.invariant_holds
    assert result.offsets_total == result.chunk_count

    with session_scope() as s:
        row = s.execute(
            text("""
                SELECT count(*) AS tong,
                       count(*) FILTER (
                         WHERE substring(t.full_text FROM c.char_start + 1
                                         FOR c.char_end - c.char_start) = c.content
                       ) AS khop
                FROM source_chunks c
                JOIN source_texts t ON t.source_id = c.source_id
            """)
        ).one()
    assert row.tong > 0
    assert row.khop == row.tong


def test_INV2_van_ban_luu_o_dang_NFC(legal_file: Path, emb) -> None:
    """Postgres tự có `normalize()` từ bản 13, dùng để kiểm chứng độc lập."""
    _ingest(legal_file, emb)
    with session_scope() as s:
        bad = s.execute(
            text("SELECT count(*) FROM source_texts WHERE full_text <> normalize(full_text, NFC)")
        ).scalar()
    assert bad == 0


# ══════════════════════════════════════════════════════
# Nội dung ghi ra
# ══════════════════════════════════════════════════════


def test_sinh_chunk_va_dat_trang_thai_ready(legal_file: Path, emb) -> None:
    result = _ingest(legal_file, emb)
    assert result.chunk_count > 1
    assert result.quality.score > 0.8

    with session_scope() as s:
        src = s.scalar(select(Source).join(Notebook).join(User).where(User.email == OWNER))
        assert src is not None
        assert src.status == "ready"
        assert src.progress == 100
        assert src.ready_at is not None
        assert src.text_quality is not None


def test_vector_dung_chieu_va_da_chuan_hoa(legal_file: Path, emb) -> None:
    _ingest(legal_file, emb)
    with session_scope() as s:
        rows = s.execute(
            text("SELECT vector_dims(embedding) AS d, vector_norm(embedding) AS n "
                 "FROM source_chunks")
        ).all()
    assert rows
    for r in rows:
        assert r.d == 1024
        assert abs(r.n - 1.0) < 1e-5


def test_tsv_sinh_tu_van_ban_goc(legal_file: Path, emb) -> None:
    """Quyết định 0001 — không tách từ ở đường lập chỉ mục."""
    _ingest(legal_file, emb)
    with session_scope() as s:
        missing = s.scalar(
            select(func.count()).select_from(SourceChunk).where(SourceChunk.tsv.is_(None))
        )
        matched = s.execute(
            text("SELECT count(*) FROM source_chunks "
                 "WHERE tsv @@ phraseto_tsquery('vi','chương trình đào tạo')")
        ).scalar()
    assert missing == 0
    assert matched >= 1


def test_truy_van_khong_dau_khop_tai_lieu_co_dau(legal_file: Path, emb) -> None:
    """US-010 AC-2c — nhờ `unaccent` trong cấu hình text search `vi`."""
    _ingest(legal_file, emb)
    with session_scope() as s:
        n = s.execute(
            text("SELECT count(*) FROM source_chunks "
                 "WHERE tsv @@ phraseto_tsquery('vi','chuong trinh dao tao')")
        ).scalar()
    assert n >= 1


def test_heading_path_theo_cau_truc_phap_quy(legal_file: Path, emb) -> None:
    _ingest(legal_file, emb)
    with session_scope() as s:
        paths = [
            p for (p,) in s.execute(select(SourceChunk.heading_path)).all() if p
        ]
    assert any("Chương I" in p and "Điều 1" in p for p in paths), paths


# ══════════════════════════════════════════════════════
# Nạp lại và xử lý lỗi
# ══════════════════════════════════════════════════════


def test_nap_lai_khong_sinh_chunk_trung(legal_file: Path, emb) -> None:
    """US-008 AC-8 ở mức toàn hệ thống, không chỉ ở mức hàm chunking."""
    first = _ingest(legal_file, emb)
    second = _ingest(legal_file, emb)

    assert first.chunk_count == second.chunk_count
    with session_scope() as s:
        sources = s.scalar(
            select(func.count()).select_from(Source).join(Notebook).join(User)
            .where(User.email == OWNER)
        )
        chunks = s.scalar(_OWNED_CHUNKS)
    assert sources == 1, "nạp lại tạo thêm nguồn thay vì cập nhật"
    assert chunks == second.chunk_count


def test_dinh_dang_khong_ho_tro_bao_loi(tmp_path: Path, emb) -> None:
    p = tmp_path / "a.xyz"
    p.write_text("nội dung", encoding="utf-8")
    with session_scope() as s, pytest.raises(ExtractionError) as exc:
        ingest_file_sync(s, p, notebook_title=NOTEBOOK, embedder=emb, owner_email=OWNER)
    assert exc.value.code == "KIND_UNSUPPORTED"


def test_van_ban_bang_ma_cu_bi_chan(tmp_path: Path, emb) -> None:
    """Cổng chất lượng US-056 chặn TRƯỚC khi tốn công nhúng.

    Đây là ca nguy hiểm nhất: tệp có đủ ký tự nên phép đếm ký tự cho qua,
    nhưng nội dung là rác hoàn toàn.
    """
    tcvn3 = (
        "§iÒu 5. Ph¹m vi ¸p dông cña quy chÕ nµy bao gåm toµn bé ho¹t ®éng "
        "®µo t¹o tr×nh ®é ®¹i häc t¹i c¸c c¬ së gi¸o dôc. Ng­êi häc ®­îc cÊp "
        "b»ng khi hoµn thµnh ch­¬ng tr×nh vµ ®¹t chuÈn ®Çu ra theo quy ®Þnh."
    )
    p = tmp_path / "legacy.txt"
    p.write_text(tcvn3, encoding="utf-8")

    with session_scope() as s, pytest.raises(ExtractionError) as exc:
        ingest_file_sync(s, p, notebook_title=NOTEBOOK, embedder=emb, owner_email=OWNER)
    assert "LEGACY_ENCODING" in exc.value.code

    # Nguồn phải được ghi lại ở trạng thái failed kèm lý do đọc được, không
    # biến mất im lặng (US-028 AC-1).
    with session_scope() as s:
        src = _own_source(s)
        assert src is not None
        assert src.status == "failed"
        assert src.error_message
        assert s.scalar(_OWNED_CHUNKS) == 0


def test_ban_scan_bi_chan_voi_chan_doan_dung(scanned_pdf: Path, emb) -> None:
    """US-023 — bản scan phải nhận đúng tên gọi của nó.

    Bản scan cũng rớt cổng chất lượng vì không có ký tự nào, nhưng lý do ghi ra
    khi đó là *"chỉ 0% ký tự là chữ cái, có thể là bảng biểu hoặc mục lục"* —
    sai, và không cho người dùng biết phải làm gì. Mã lỗi cũng là thứ định
    tuyến sang đường OCR ở US-024, nên nó phải phân biệt được.
    """
    with session_scope() as s, pytest.raises(ExtractionError) as exc:
        ingest_file_sync(s, scanned_pdf, notebook_title=NOTEBOOK, embedder=emb, owner_email=OWNER)
    assert exc.value.code == "SCAN_NO_TEXT_LAYER"
    assert "OCR" in exc.value.message_vi

    with session_scope() as s:
        src = _own_source(s)
        assert src is not None
        assert src.status == "failed"
        assert src.is_scanned is True
        assert s.scalar(_OWNED_CHUNKS) == 0


def test_pdf_co_text_khong_bi_danh_dau_la_scan(make_pdf, emb) -> None:
    from tests.conftest import VI_PARAGRAPHS

    _ingest(make_pdf([VI_PARAGRAPHS, VI_PARAGRAPHS]), emb)
    with session_scope() as s:
        assert _own_source(s).is_scanned is False


def test_txt_ngan_khong_bi_nham_la_scan(tmp_path: Path, emb) -> None:
    """Chỉ PDF mới xét tỉ lệ trang thiếu text.

    TXT và DOCX không có khái niệm trang; `TextBuilder` gom chúng thành đúng
    một "trang". Áp cùng luật vào đó thì mọi tệp văn bản ngắn đều bị coi là bản
    scan — một kết luận vô nghĩa với định dạng vốn không thể là ảnh.
    """
    p = tmp_path / "ngan.txt"
    p.write_text(
        "Điều 1. Phạm vi. Quy định này áp dụng cho toàn bộ người học của nhà trường "
        "trong các chương trình đào tạo được cấp phép.",
        encoding="utf-8",
    )
    result = _ingest(p, emb)
    assert result.chunk_count > 0

    with session_scope() as s:
        assert _own_source(s).is_scanned is None, "TXT không nên bị chấm là scan hay không"


def test_pdf_that_di_het_duong_ong(make_pdf, emb) -> None:
    """Đường đi thật: PDF → trích xuất kèm bbox → chunk → nhúng → DB."""
    from tests.conftest import VI_PARAGRAPHS

    path = make_pdf([VI_PARAGRAPHS, VI_PARAGRAPHS])
    result = _ingest(path, emb)

    assert result.invariant_holds
    assert result.page_count == 2

    with session_scope() as s:
        src = _own_source(s)
        with_bbox = s.scalar(
            select(func.count())
            .select_from(SourceChunk)
            .where(SourceChunk.source_id == src.id, SourceChunk.bbox.isnot(None))
        )
        pages = {
            p
            for (p,) in s.execute(
                select(SourceChunk.page_no).where(SourceChunk.source_id == src.id)
            ).all()
        }
    assert with_bbox > 0, "không chunk nào mang toạ độ — hỏng cầu nối tới US-015"
    assert pages == {1, 2}


# ══════════════════════════════════════════════════════
# Repository
# ══════════════════════════════════════════════════════


def test_verify_offsets_bat_duoc_offset_sai(legal_file: Path, emb) -> None:
    """Chứng minh chiều ngược lại: cố ý làm lệch một chunk thì hàm phải phát hiện."""
    _ingest(legal_file, emb)

    with session_scope() as s:
        src = _own_source(s)
        assert src is not None
        ok, total = repo.verify_offsets(s, src.id)
        assert ok == total

        # Phải lấy chunk CỦA NGUỒN NÀY. `select(SourceChunk).limit(1)` có thể
        # trúng chunk của nguồn khác trong database, và khi đó phép làm lệch
        # không ảnh hưởng gì tới kết quả kiểm chứng.
        chunk = s.scalars(
            select(SourceChunk).where(SourceChunk.source_id == src.id).limit(1)
        ).one()
        chunk.char_end = chunk.char_end - 1
        s.flush()

        ok_after, total_after = repo.verify_offsets(s, src.id)
        assert total_after == total
        assert ok_after == total - 1, "lệch một ký tự mà không bị phát hiện"


def test_so_chunk_khac_so_vector_bi_tu_choi(legal_file: Path, emb) -> None:
    with session_scope() as s:
        user = repo.get_or_create_user(s, OWNER)
        nb = repo.get_or_create_notebook(s, user, NOTEBOOK)
        src = repo.upsert_source(
            s, nb, title="t", original_name="t.txt", storage_key="k",
            kind="txt", mime_type="text/plain", size_bytes=1,
        )
        with pytest.raises(ValueError, match="khác số vector"):
            repo.insert_chunks(s, src, [], [[0.0] * 1024])


def test_xoa_notebook_xoa_day_chuyen(legal_file: Path, emb) -> None:
    """US-005 AC-4 — xoá người dùng phải dọn sạch nguồn, văn bản và chunk."""
    result = _ingest(legal_file, emb)

    with session_scope() as s:
        assert s.scalar(_OWNED_CHUNKS) == result.chunk_count
        s.execute(delete(User).where(User.email == OWNER))

    with session_scope() as s:
        assert s.scalar(_OWNED_CHUNKS) == 0
        # Không còn bản ghi văn bản nào mồ côi của nguồn vừa xoá.
        assert s.get(SourceText, uuid.UUID(result.source_id)) is None
