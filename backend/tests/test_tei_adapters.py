"""Adapter nhúng và xếp hạng lại qua dịch vụ TEI.

Không gọi mạng. Mọi phép thử ở đây dựng phản hồi HTTP giả bằng transport của
`httpx`, nên chúng chạy được ở mọi nơi và không phụ thuộc hạn mức của dịch vụ.

Thứ được kiểm là phần **dễ hỏng im lặng**, không phải đường chạy thuận lợi:

* phản hồi `/rerank` đã sắp xếp sẵn phải được đưa về đúng thứ tự đầu vào —
  nhầm chỗ này thì trích dẫn trỏ sai đoạn mà không có gì báo lỗi;
* điểm phải nằm trong [0, 1], vì ngưỡng τ so sánh trực tiếp với con số đó;
* vector phải đủ số chiều và đã chuẩn hoá L2, vì pgvector vẫn tính ra điểm với
  vector sai chuẩn;
* lô lớn hơn trần của dịch vụ phải được tự chia, không được để rơi vào 413.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest

from app.adapters import tei as T
from app.adapters.embedding.tei import TeiEmbeddingProvider
from app.adapters.rerank.tei import TeiRerankProvider
from app.adapters.tei import TeiClient, TeiError
from app.ports.embedding import EmbeddingProvider
from app.ports.rerank import RerankProvider

DIM = 1024


def _mount(monkeypatch, handler) -> list[httpx.Request]:
    """Thay `httpx.Client` bằng bản chạy trên transport giả."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request, len(seen))

    real = httpx.Client

    def fake(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(record)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", fake)
    return seen


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


def _unit(seed: float = 1.0) -> list[float]:
    """Một vector 1024 chiều đã chuẩn hoá L2."""
    v = [0.0] * DIM
    v[0] = 1.0 if seed >= 0 else -1.0
    return v


@pytest.fixture
def client() -> TeiClient:
    return TeiClient(base_url="https://tei.example/", api_key="k", timeout=5.0)


@pytest.fixture(autouse=True)
def _khong_ngu_that(monkeypatch) -> None:
    """Test thử lại không được ngủ thật — nó chỉ làm bộ test chậm đi."""
    monkeypatch.setattr(T.time, "sleep", lambda _s: None)


# ══════════════════════════════════════════════════════
# Hợp đồng cổng
# ══════════════════════════════════════════════════════


def test_thoa_man_hop_dong_cong(client: TeiClient) -> None:
    emb = TeiEmbeddingProvider(client=client)
    rr = TeiRerankProvider(client=client)
    assert isinstance(emb, EmbeddingProvider)
    assert isinstance(rr, RerankProvider)
    assert emb.dim == DIM


def test_ten_ghi_ca_ten_mien(client: TeiClient) -> None:
    """Số đo từ máy chủ khác là số đo khác — metadata phải phân biệt được."""
    assert TeiEmbeddingProvider(client=client).name == "tei:BAAI/bge-m3@tei.example"
    assert "tei.example" in TeiRerankProvider(client=client).name


def test_luon_san_sang_va_khong_phai_tai_gi(client: TeiClient) -> None:
    """Trọng số không nằm trên máy này, nên `warm()` chỉ là một lượt hỏi."""
    assert TeiEmbeddingProvider(client=client).da_san_sang is True


# ══════════════════════════════════════════════════════
# Nhúng
# ══════════════════════════════════════════════════════


def test_gui_dung_khuon_dang_va_header(monkeypatch, client: TeiClient) -> None:
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[_unit()]))
    TeiEmbeddingProvider(client=client).embed_query("Học phí nộp khi nào?")

    (req,) = seen
    assert str(req.url) == "https://tei.example/embed"
    assert req.headers["authorization"] == "Bearer k"
    body = _body(req)
    assert body["inputs"] == ["Học phí nộp khi nào?"]
    # Chuẩn hoá là phần của hợp đồng cổng, không phải tuỳ chọn.
    assert body["normalize"] is True
    assert body["truncate"] is True


def test_tu_chia_lo_va_giu_nguyen_thu_tu(monkeypatch, client: TeiClient) -> None:
    """Lô lớn hơn trần của dịch vụ phải được chia, và ghép lại đúng thứ tự.

    Ghép sai thứ tự thì vector bị gán cho nhầm đoạn — cơ sở dữ liệu vẫn nhận,
    truy xuất vẫn chạy, chỉ là mọi kết quả đều sai.
    """
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        lo = _body(request)["inputs"]
        # Đánh dấu mỗi vector bằng chính vị trí toàn cục của nó.
        return httpx.Response(200, json=[_unit(1.0 if t.startswith("a") else -1.0) for t in lo])

    seen = _mount(monkeypatch, handler)
    emb = TeiEmbeddingProvider(client=client, batch_size=2)
    texts = ["a0", "a1", "b2", "b3", "a4"]
    vectors = emb.embed_documents(texts)

    assert [_body(r)["inputs"] for r in seen] == [["a0", "a1"], ["b2", "b3"], ["a4"]]
    assert len(vectors) == 5
    assert [v[0] for v in vectors] == [1.0, 1.0, -1.0, -1.0, 1.0]


def test_tran_cua_dich_vu_thang_the_batch_size(monkeypatch, client: TeiClient) -> None:
    """`EMBEDDING_BATCH_SIZE` lớn hơn `TEI_MAX_BATCH` thì lấy con số nhỏ hơn.

    Không lấy nhỏ hơn thì mọi lượt nạp tài liệu chết vì 413, và thông báo lỗi
    lại nói về một tham số mà người vận hành không nghĩ là mình đã đặt.
    """
    from app.settings import settings as st

    monkeypatch.setattr(st, "tei_max_batch", 8)
    assert TeiEmbeddingProvider(client=client, batch_size=128).batch_size == 8
    # Và chiều ngược lại: trần rộng thì không được nới lô do người dùng chọn.
    assert TeiEmbeddingProvider(client=client, batch_size=2).batch_size == 2


def test_danh_sach_rong_khong_goi_mang(monkeypatch, client: TeiClient) -> None:
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(500))
    assert TeiEmbeddingProvider(client=client).embed_documents([]) == []
    assert seen == []


def test_lech_so_luong_bi_chan(monkeypatch, client: TeiClient) -> None:
    _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[_unit()]))
    with pytest.raises(TeiError, match="1 vector cho 2 đoạn"):
        TeiEmbeddingProvider(client=client).embed_documents(["một", "hai"])


def test_lech_so_chieu_bi_chan(monkeypatch, client: TeiClient) -> None:
    """Postgres cũng từ chối, nhưng bằng một thông báo khó lần ra nguyên nhân."""
    _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[[0.0, 1.0, 0.0]]))
    with pytest.raises(TeiError, match="EMBEDDING_DIM"):
        TeiEmbeddingProvider(client=client).embed_query("thử")


def test_vector_chua_chuan_hoa_bi_chan(monkeypatch, client: TeiClient) -> None:
    """Vector sai chuẩn vẫn ghi được và vẫn tính ra điểm cosine — chỉ là sai."""
    _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[[1.0] * DIM]))
    with pytest.raises(TeiError, match="chưa chuẩn hoá"):
        TeiEmbeddingProvider(client=client).embed_query("thử")


def test_vector_hop_le_di_qua_nguyen_ven(monkeypatch, client: TeiClient) -> None:
    v = _unit()
    _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[v]))
    ra = TeiEmbeddingProvider(client=client).embed_query("thử")
    assert math.isclose(math.sqrt(sum(x * x for x in ra)), 1.0, rel_tol=1e-9)
    assert ra == v


def test_warm_hoi_dung_endpoint_suc_khoe(monkeypatch, client: TeiClient) -> None:
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(200, json={"ok": True}))
    TeiEmbeddingProvider(client=client).warm()
    (req,) = seen
    assert req.method == "GET"
    assert str(req.url) == "https://tei.example/health/embedding"


def test_warm_nem_loi_thay_vi_di_tiep(monkeypatch, client: TeiClient) -> None:
    """Sai khoá phải nổ lúc khởi động, không phải lúc thanh tiến trình ở 85%."""
    _mount(monkeypatch, lambda r, n: httpx.Response(401, text="unauthorized"))
    with pytest.raises(TeiError, match="TEI_API_KEY"):
        TeiEmbeddingProvider(client=client).warm()


# ══════════════════════════════════════════════════════
# Xếp hạng lại
# ══════════════════════════════════════════════════════


def test_phan_hoi_da_sap_xep_duoc_dua_ve_dung_thu_tu(monkeypatch, client: TeiClient) -> None:
    """Đây là phép thử quan trọng nhất của cả tệp.

    `/rerank` trả về danh sách xếp theo điểm giảm dần. Nhận thẳng nó làm kết
    quả thì điểm bị gán cho nhầm đoạn: cổng ngưỡng τ chấm một đoạn nhưng ngữ
    cảnh đưa vào mô hình lại là đoạn khác, và trích dẫn trỏ sai chỗ — không có
    gì báo lỗi.
    """
    _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[
        {"index": 1, "score": 0.9982},
        {"index": 2, "score": 0.0014},
        {"index": 0, "score": 0.0004},
    ]))
    scores = TeiRerankProvider(client=client).score("thủ đô?", ["đà nẵng", "hà nội", "sài gòn"])
    assert scores == [0.0004, 0.9982, 0.0014]


def test_gui_dung_khuon_dang_rerank(monkeypatch, client: TeiClient) -> None:
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[{"index": 0, "score": 0.5}]))
    TeiRerankProvider(client=client).score("hỏi", ["một đoạn"])

    (req,) = seen
    assert str(req.url) == "https://tei.example/rerank"
    body = _body(req)
    assert body["query"] == "hỏi"
    assert body["texts"] == ["một đoạn"]
    # Chỗ gọi đã có sẵn văn bản; xin lại chỉ nhân đôi kích thước phản hồi.
    assert body["return_text"] is False


def test_chia_lo_rerank_giu_thu_tu_toan_cuc(monkeypatch, client: TeiClient) -> None:
    """`RERANK_CANDIDATES=50` lớn hơn trần 32 của dịch vụ, nên phải chia lô.

    Điểm của mỗi cặp (câu hỏi, đoạn) độc lập với các đoạn còn lại, nên chia lô
    không đổi kết quả — miễn là ghép lại đúng chỗ.
    """
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        lo = _body(request)["texts"]
        # Trả về ĐẢO NGƯỢC để phép thử thật sự chạm vào bước sắp lại.
        items = [{"index": i, "score": float(t) / 10} for i, t in enumerate(lo)]
        return httpx.Response(200, json=list(reversed(items)))

    seen = _mount(monkeypatch, handler)
    rr = TeiRerankProvider(client=client, max_batch=2)
    scores = rr.score("hỏi", ["1", "2", "3", "4", "5"])

    assert [_body(r)["texts"] for r in seen] == [["1", "2"], ["3", "4"], ["5"]]
    assert scores == [0.1, 0.2, 0.3, 0.4, 0.5]


def test_diem_ngoai_khoang_bi_chan(monkeypatch, client: TeiClient) -> None:
    """Logit thô làm τ = 0.35 nhận mọi thứ là "đủ căn cứ" mà không báo lỗi gì."""
    _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[{"index": 0, "score": 7.4}]))
    with pytest.raises(TeiError, match="sigmoid"):
        TeiRerankProvider(client=client).score("hỏi", ["đoạn"])


def test_index_trung_bi_chan(monkeypatch, client: TeiClient) -> None:
    _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[
        {"index": 0, "score": 0.9},
        {"index": 0, "score": 0.1},
    ]))
    with pytest.raises(TeiError, match="hai lần"):
        TeiRerankProvider(client=client).score("hỏi", ["a", "b"])


def test_index_ngoai_pham_vi_bi_chan(monkeypatch, client: TeiClient) -> None:
    _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[{"index": 5, "score": 0.9}]))
    with pytest.raises(TeiError, match="ngoài phạm vi"):
        TeiRerankProvider(client=client).score("hỏi", ["a"])


def test_thieu_diem_bi_chan(monkeypatch, client: TeiClient) -> None:
    _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[{"index": 0}]))
    with pytest.raises(TeiError, match=r"thiếu 'index' hoặc 'score'"):
        TeiRerankProvider(client=client).score("hỏi", ["a"])


def test_rerank_danh_sach_rong(monkeypatch, client: TeiClient) -> None:
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(500))
    assert TeiRerankProvider(client=client).score("hỏi", []) == []
    assert seen == []


# ══════════════════════════════════════════════════════
# Máy khách — thử lại và thông báo lỗi
# ══════════════════════════════════════════════════════


def test_thu_lai_khi_qua_tai_roi_thanh_cong(monkeypatch, client: TeiClient) -> None:
    """502/504 là trạng thái tạm thời; để nó nổi lên thành lỗi thì một lượt nạp
    tài liệu hỏng vì lý do không liên quan gì tới chất lượng hệ thống."""
    seen = _mount(monkeypatch, lambda r, n: (
        httpx.Response(502) if n == 1 else httpx.Response(200, json=[_unit()])
    ))
    TeiEmbeddingProvider(client=client).embed_query("thử")
    assert len(seen) == 2


def test_qua_tai_keo_dai_thi_bao_ro(monkeypatch, client: TeiClient) -> None:
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(503))
    with pytest.raises(TeiError, match="quá tải"):
        TeiEmbeddingProvider(client=client).embed_query("thử")
    assert len(seen) == T.RETRIES + 1


def test_413_chi_ro_tham_so_phai_sua(monkeypatch, client: TeiClient) -> None:
    _mount(monkeypatch, lambda r, n: httpx.Response(413, text="payload too large"))
    with pytest.raises(TeiError, match="TEI_MAX_BATCH"):
        TeiEmbeddingProvider(client=client).embed_query("thử")


def test_404_goi_y_kiem_tra_base_url(monkeypatch, client: TeiClient) -> None:
    _mount(monkeypatch, lambda r, n: httpx.Response(404, text="not found"))
    with pytest.raises(TeiError, match="TEI_BASE_URL"):
        TeiEmbeddingProvider(client=client).embed_query("thử")


def test_thieu_khoa_thi_khong_goi_mang(monkeypatch) -> None:
    """Nói ngay phải đặt gì, thay vì để dịch vụ trả về 401.

    Phải xoá khoá ở `settings`, không chỉ truyền `api_key=None`: hàm dựng rơi
    về `settings.tei_api_key` đúng như mọi adapter khác, nên trên máy đã cấu
    hình `tei` thật thì phép thử này lặng lẽ đo nhầm đường chạy có khoá.
    """
    from app.settings import settings as st

    monkeypatch.setattr(st, "tei_api_key", None)
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(200, json=[_unit()]))
    emb = TeiEmbeddingProvider(client=TeiClient(base_url="https://tei.example"))
    with pytest.raises(TeiError, match="TEI_API_KEY"):
        emb.embed_query("thử")
    assert seen == []


def test_khong_ket_noi_duoc_thi_goi_y_mo_hinh_cuc_bo(monkeypatch, client: TeiClient) -> None:
    def no(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("mất mạng", request=request)

    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(no)}),
    )
    with pytest.raises(TeiError, match="mô hình cục bộ"):
        TeiEmbeddingProvider(client=client).embed_query("thử")
