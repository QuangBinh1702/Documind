"""Hai adapter mô hình ngôn ngữ thật — US-029, US-030.

Không gọi mạng. Mọi phép thử ở đây dựng phản hồi HTTP giả bằng transport của
`httpx`, nên chúng chạy được ở mọi nơi và không phụ thuộc hạn mức API.

Thứ được kiểm là phần **dễ hỏng im lặng**: khuôn dạng payload, cách tách sự
kiện SSE, và những thông báo lỗi mà US-029 AC-5 / US-030 AC-5 yêu cầu phải nói
được cho người dùng thay vì ném ra một mã HTTP.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.llm import gemini as G
from app.adapters.llm.gemini import GeminiLLMProvider
from app.adapters.llm.local import LocalLLMProvider


def _sse(*events: dict) -> bytes:
    return b"".join(
        b"data: " + json.dumps(e, ensure_ascii=False).encode() + b"\n\n" for e in events
    )


def _chunk(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _mount(monkeypatch, handler) -> list[httpx.Request]:
    """Thay `httpx.AsyncClient` bằng bản chạy trên transport giả."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request, len(seen))

    real = httpx.AsyncClient

    def fake(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(record)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake)
    return seen


async def _collect(provider, **kw) -> str:
    return "".join(
        [p async for p in provider.stream("chỉ dẫn", [{"role": "user", "content": "hỏi"}], **kw)]
    )


# ══════════════════════════════════════════════════════
# Gemini — US-030
# ══════════════════════════════════════════════════════


async def test_ghep_cac_manh_sse(monkeypatch) -> None:
    _mount(monkeypatch, lambda r, n: httpx.Response(
        200, content=_sse(_chunk("Học phí "), _chunk("nộp trong 30 ngày [2].")),
    ))
    out = await _collect(GeminiLLMProvider(api_key="k"))
    assert out == "Học phí nộp trong 30 ngày [2]."


async def test_bo_qua_part_khong_phai_van_ban(monkeypatch) -> None:
    """Mô hình biết suy luận trả về `thoughtSignature` xen giữa các part.

    Đó là chi tiết nội bộ của mô hình. Để nó lọt vào câu trả lời thì người dùng
    nhìn thấy một chuỗi base64 giữa câu; ném lỗi vì gặp nó thì còn tệ hơn.
    """
    event = {"candidates": [{"content": {"parts": [
        {"thoughtSignature": "ErwCCrwCARFN"},
        {"text": "Câu trả lời."},
    ]}}]}
    _mount(monkeypatch, lambda r, n: httpx.Response(200, content=_sse(event)))
    assert await _collect(GeminiLLMProvider(api_key="k")) == "Câu trả lời."


async def test_chi_dan_he_thong_di_o_truong_rieng(monkeypatch) -> None:
    """US-061 dựa vào ranh giới này: chỉ dẫn nằm ngoài, tài liệu nằm trong.

    Trộn chỉ dẫn vào lượt hội thoại làm nó thành một tin nhắn người dùng như
    mọi tin nhắn khác, và tài liệu tiêm chỉ thị vào sẽ đứng ngang hàng với nó.
    """
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(200, content=_sse(_chunk("x"))))
    await _collect(GeminiLLMProvider(api_key="k"))

    body = json.loads(seen[0].content)
    assert body["systemInstruction"]["parts"][0]["text"] == "chỉ dẫn"
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hỏi"}]}]


async def test_yeu_cau_stream_that_su(monkeypatch) -> None:
    """Thiếu `alt=sse` thì Gemini gom cả câu trả lời vào một mảng JSON và không
    phát ra gì cho tới khi sinh xong — mốc 'token đầu tiên dưới 3 giây' của
    US-012 AC-2 mất ý nghĩa mà không có gì báo lỗi."""
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(200, content=_sse(_chunk("x"))))
    await _collect(GeminiLLMProvider(api_key="k"))
    assert "alt=sse" in str(seen[0].url)
    assert ":streamGenerateContent" in str(seen[0].url)


async def test_gui_khoa_qua_header_khong_qua_url(monkeypatch) -> None:
    """Khoá trong query string bị ghi vào log của mọi proxy trên đường đi."""
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(200, content=_sse(_chunk("x"))))
    await _collect(GeminiLLMProvider(api_key="bi-mat"))
    assert seen[0].headers["x-goog-api-key"] == "bi-mat"
    assert "bi-mat" not in str(seen[0].url)


async def test_tra_ve_rong_thi_bao_loi_chu_khong_im_lang(monkeypatch) -> None:
    """Ca hỏng tệ nhất: cổng ngưỡng cho qua, giao diện hiện bong bóng trống,
    và không có gì trong log nói vì sao.

    Đã gặp thật: các mô hình Gemini đời mới suy nghĩ trước khi trả lời, và phần
    suy nghĩ ăn vào CÙNG hạn mức token với câu trả lời. Với prompt RAG mang 8
    đoạn tài liệu, suy nghĩ dùng hết hạn mức và phần trả lời còn lại rỗng.
    """
    event = {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}
    _mount(monkeypatch, lambda r, n: httpx.Response(200, content=_sse(event)))

    with pytest.raises(RuntimeError, match=r"THINKING_BUDGET|hạn mức token"):
        await _collect(GeminiLLMProvider(api_key="k"))


@pytest.mark.parametrize(
    ("finish", "phai_co"),
    [("SAFETY", "bộ lọc nội dung"), ("RECITATION", "bản quyền"), ("OTHER", "OTHER")],
)
async def test_giai_thich_tung_ly_do_dung_lai(monkeypatch, finish, phai_co) -> None:
    event = {"candidates": [{"content": {"parts": []}, "finishReason": finish}]}
    _mount(monkeypatch, lambda r, n: httpx.Response(200, content=_sse(event)))
    with pytest.raises(RuntimeError, match=phai_co):
        await _collect(GeminiLLMProvider(api_key="k"))


async def test_tat_suy_nghi_theo_mac_dinh(monkeypatch) -> None:
    """Câu trả lời ở đây phải rút ra từ các đoạn đã cho, không phải suy luận ra.

    Nên hạn mức token nên dành cả cho câu trả lời — đó cũng là thứ giữ cho ca
    "trả về rỗng" ở trên không xảy ra ngay từ đầu.
    """
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(200, content=_sse(_chunk("x"))))
    await _collect(GeminiLLMProvider(api_key="k"), max_tokens=500)

    cfg = json.loads(seen[0].content)["generationConfig"]
    assert cfg["thinkingConfig"]["thinkingBudget"] == 0
    assert cfg["maxOutputTokens"] == 500


async def test_thu_lai_khi_qua_tai_roi_thanh_cong(monkeypatch) -> None:
    """503 là trạng thái tạm thời và rất hay gặp ở hạn mức miễn phí.

    Để nó nổi lên thành lỗi thì một câu trả lời hỏng vì lý do không liên quan
    gì tới chất lượng hệ thống — và giữa một lượt chạy đánh giá thì nó làm hỏng
    cả phép đo.
    """
    monkeypatch.setattr(G, "BACKOFF_S", 0.0)
    seen = _mount(monkeypatch, lambda r, n: (
        httpx.Response(503, text="high demand") if n == 1
        else httpx.Response(200, content=_sse(_chunk("xong")))
    ))
    assert await _collect(GeminiLLMProvider(api_key="k")) == "xong"
    assert len(seen) == 2


async def test_qua_tai_keo_dai_thi_bao_loi_doc_duoc(monkeypatch) -> None:
    monkeypatch.setattr(G, "BACKOFF_S", 0.0)
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(503, text="high demand"))

    with pytest.raises(RuntimeError, match="quá tải"):
        await _collect(GeminiLLMProvider(api_key="k"))
    assert len(seen) == G.RETRIES + 1, "phải dừng đúng số lần cấu hình, không thử mãi"


@pytest.mark.parametrize(
    ("status", "phai_co"),
    [
        (403, "khoá API"),
        (404, "GEMINI_MODEL"),
        (400, "400"),
    ],
)
async def test_loi_khong_tam_thoi_noi_duoc_thanh_cau(monkeypatch, status, phai_co) -> None:
    """US-030 AC-5 — hướng dẫn cấu hình, không ném ra một mã HTTP trần."""
    _mount(monkeypatch, lambda r, n: httpx.Response(status, text="chi tiết"))
    with pytest.raises(RuntimeError, match=phai_co):
        await _collect(GeminiLLMProvider(api_key="k"))


async def test_thieu_khoa_thi_khong_goi_mang(monkeypatch) -> None:
    """Không có khoá thì phải dừng TRƯỚC khi mở kết nối.

    `api_key=None` rơi về giá trị trong cấu hình, nên phải xoá cả ở đó — nếu
    không thì phép thử này lại đi gọi thật bằng khoá của máy đang chạy test.
    """
    from app.settings import settings

    monkeypatch.setattr(settings, "gemini_api_key", None)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        await _collect(GeminiLLMProvider(api_key=None))


async def test_khong_phai_mo_hinh_cuc_bo() -> None:
    """Cờ này là thứ US-032 AC-2 dựa vào để biết một lượt gọi sẽ rời khỏi máy."""
    assert GeminiLLMProvider(api_key="k").is_local is False
    assert LocalLLMProvider().is_local is True


# ══════════════════════════════════════════════════════
# Mô hình cục bộ — US-029
# ══════════════════════════════════════════════════════


def _openai_sse(*texts: str) -> bytes:
    events = [
        b"data: " + json.dumps({"choices": [{"delta": {"content": t}}]}).encode() + b"\n\n"
        for t in texts
    ]
    return b"".join(events) + b"data: [DONE]\n\n"


async def test_cuc_bo_ghep_manh_theo_giao_thuc_openai(monkeypatch) -> None:
    _mount(monkeypatch, lambda r, n: httpx.Response(200, content=_openai_sse("Học ", "phí.")))
    assert await _collect(LocalLLMProvider()) == "Học phí."


async def test_cuc_bo_dua_chi_dan_vao_tin_nhan_system(monkeypatch) -> None:
    seen = _mount(monkeypatch, lambda r, n: httpx.Response(200, content=_openai_sse("x")))
    await _collect(LocalLLMProvider())

    body = json.loads(seen[0].content)
    assert body["messages"][0] == {"role": "system", "content": "chỉ dẫn"}
    assert body["stream"] is True


async def test_cuc_bo_khong_chay_thi_chi_duong(monkeypatch) -> None:
    """US-029 AC-5 — người dùng cần biết phải bật cái gì, không phải đọc
    `ConnectError` của tầng socket."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("từ chối kết nối", request=request)

    _mount(monkeypatch, lambda r, n: refuse(r))
    with pytest.raises(RuntimeError, match="Ollama"):
        await _collect(LocalLLMProvider())
